#!/usr/bin/env python3
"""Master Data reads for seed scripts, through MDS's API — never its database.

A registry's seed jobs write only the registry's own database. When a loader
needs Master Data (the geography, the country pack's sample people, a code
list), it reads it here, the same way the registry's services do at runtime:
MDS's ``/catalogue`` and ``/samples`` endpoints, authenticated with a Keycloak
client-credentials token as the registry's own confidential client.

Standard library only, so any seed image (and a laptop) can use it:

    from mds_client import MdsClient

    mds = MdsClient.from_env()            # None when MDS_API_URL is not set
    levels = mds.geo_levels()             # top level first
    chain = mds.geo_chain("ET041203")     # the unit and its ancestors, top first
    people = mds.sample_individuals()     # all pages

Environment (set by the registry chart's db-seed Job):

    MDS_API_URL        MDS base URL, e.g. http://commons-services-master-data-api
    MDS_TOKEN_URL      Keycloak token endpoint (the PUBLIC issuer's, as for the
                       services). Empty: no token is sent (a local stand-in).
    MDS_CLIENT_ID      the registry's confidential client
    MDS_CLIENT_SECRET  its secret
    MDS_RELEASE        optional catalogue release to pin geography reads to
    MDS_PAGE_SIZE      page size for paged reads (default 500)
    MDS_TIMEOUT        seconds per HTTP call (default 30)

From a shell (also used by Jobs to wait for a country pack):

    python3 mds_client.py levels          # print the hierarchy
    python3 mds_client.py wait-geo [--timeout 300]
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional


class MdsError(Exception):
    """MDS refused the request (a bad request, a permission, a token refused)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


class MdsUnavailable(MdsError):
    """MDS (or Keycloak) could not be reached, or failed (5xx)."""


class MdsNotFound(MdsError):
    """The list, unit or version does not exist (G2P-CAT-404)."""


# (method, url, headers, body bytes) -> (status, body bytes). Replaceable in tests.
Transport = Callable[[str, str, dict, Optional[bytes]], "tuple[int, bytes]"]


def _urllib_transport(timeout: float) -> Transport:
    def send(method: str, url: str, headers: dict, body: Optional[bytes]) -> tuple[int, bytes]:
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 (URL from config)
                return resp.status, resp.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()
        except (urllib.error.URLError, OSError) as error:
            raise MdsUnavailable("HTTP", f"{url}: {error}") from error

    return send


class MdsClient:
    def __init__(
        self,
        base_url: str,
        *,
        token_url: str = "",
        client_id: str = "",
        client_secret: str = "",
        release: str = "",
        page_size: int = 500,
        timeout: float = 30.0,
        transport: Optional[Transport] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token_url = token_url
        self.client_id = client_id
        self.client_secret = client_secret
        self.release = release
        self.page_size = max(1, int(page_size))
        self._send = transport or _urllib_transport(timeout)
        self._token: Optional[str] = None
        self._token_expires_at = 0.0
        self._levels: Optional[list[dict]] = None

    @classmethod
    def from_env(cls, *, required: bool = False) -> Optional["MdsClient"]:
        """A client configured from MDS_* env; None (or an error, if required) when unset."""
        base_url = os.environ.get("MDS_API_URL", "").strip()
        if not base_url:
            if required:
                raise MdsError("CONFIG", "MDS_API_URL is not set")
            return None
        return cls(
            base_url,
            token_url=os.environ.get("MDS_TOKEN_URL", "").strip(),
            client_id=os.environ.get("MDS_CLIENT_ID", ""),
            client_secret=os.environ.get("MDS_CLIENT_SECRET", ""),
            release=os.environ.get("MDS_RELEASE", "").strip(),
            page_size=int(os.environ.get("MDS_PAGE_SIZE") or 500),
            timeout=float(os.environ.get("MDS_TIMEOUT") or 30),
        )

    # ------------------------------------------------------------- transport

    def _access_token(self) -> Optional[str]:
        if not self.token_url:
            return None
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        form = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode()
        status, body = self._send(
            "POST", self.token_url, {"Content-Type": "application/x-www-form-urlencoded"}, form)
        if status >= 500:
            raise MdsUnavailable("TOKEN", f"token endpoint returned {status}")
        if status >= 400:
            raise MdsError("TOKEN", f"token request refused ({status}): {body[:200]!r}")
        data = json.loads(body or b"{}")
        token = data.get("access_token")
        if not token:
            raise MdsError("TOKEN", "token response has no access_token")
        try:
            lifetime = float(data.get("expires_in") or 300)
        except (TypeError, ValueError):
            lifetime = 300.0
        self._token = token
        self._token_expires_at = time.monotonic() + max(lifetime - min(30.0, lifetime / 10), 1.0)
        return token

    def post(self, path: str, payload: dict, *, page: Optional[tuple[int, int]] = None) -> tuple[Any, Any]:
        """POST an OpenG2P envelope; returns (response_payload, pagination_response)."""
        body: dict[str, Any] = {"request_payload": payload}
        if page:
            body["pagination_request"] = {"current_page": page[0], "page_size": page[1]}
        envelope = json.dumps({
            "request_header": {
                "sender_app_mnemonic": "registry-db-seed",
                "sender_app_url": "",
                "request_id": str(uuid.uuid4()),
                "request_timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            },
            "request_body": body,
        }).encode()
        url = self.base_url + path
        for attempt in (1, 2):
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            token = self._access_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
            status, raw = self._send("POST", url, headers, envelope)
            if status == 401 and attempt == 1 and self.token_url:
                self._token = None  # expired or revoked early: get a new one, once
                continue
            break
        if status >= 500:
            raise MdsUnavailable(str(status), f"{path}: {raw[:200]!r}")
        if status >= 400:
            raise MdsError(str(status), f"{path}: {raw[:200]!r}")
        data = json.loads(raw or b"{}")
        header = data.get("response_header") or {}
        if str(header.get("response_status") or "").upper() == "ERROR":
            code = header.get("response_error_code") or "ERROR"
            message = header.get("response_error_message") or ""
            if code.endswith("-404"):
                raise MdsNotFound(code, message)
            if code.endswith("-500") or code.endswith("-502"):
                raise MdsUnavailable(code, message)
            raise MdsError(code, message)
        response_body = data.get("response_body") or {}
        return response_body.get("response_payload"), response_body.get("pagination_response")

    def paged(self, path: str, payload: dict, items_key: str) -> list:
        """Every item of a paged read, all pages."""
        first, pagination = self.post(path, payload, page=(1, self.page_size))
        items = list((first or {}).get(items_key) or [])
        pages = int((pagination or {}).get("number_of_pages") or 1)
        for number in range(2, pages + 1):
            more, _ = self.post(path, payload, page=(number, self.page_size))
            items.extend((more or {}).get(items_key) or [])
        return items

    def _geo_selector(self) -> dict:
        return {"release": self.release} if self.release else {"version": "latest"}

    # ------------------------------------------------------------- geography

    def geo_levels(self) -> list[dict]:
        """The levels, top level first: level_id, level_mnemonic, parent_level_id, display.

        Ordered by walking parent -> child, not by level_id (ids are opaque). A
        level whose parent is not in the list (or empty) is the top. Empty when
        no geography is published.
        """
        if self._levels is None:
            try:
                payload, _ = self.post("/catalogue/get_geo_levels", self._geo_selector())
            except MdsNotFound:
                return []
            self._levels = order_levels(list((payload or {}).get("levels") or []))
        return self._levels

    def geo_units(self, *, level: Optional[str] = None, parent_unit_id: Optional[str] = None) -> list[dict]:
        """Active units (all pages), optionally at one level (id or mnemonic) or under one parent."""
        payload: dict[str, Any] = dict(self._geo_selector())
        if level is not None:
            payload["level"] = level
        if parent_unit_id is not None:
            payload["parent_unit_id"] = parent_unit_id
        try:
            return self.paged("/catalogue/get_geo_units", payload, "units")
        except MdsNotFound:
            return []

    def geo_chain(self, unit_id: str) -> Optional[list[dict]]:
        """The unit and its ancestors, top level first (the unit last); None if unknown.

        Each entry: unit_id, name, level_id, level_mnemonic, parent_unit_id, status.
        """
        if not unit_id:
            return None
        try:
            payload, _ = self.post("/catalogue/get_geo_unit", {"unit_id": unit_id, **self._geo_selector()})
        except MdsNotFound:
            return None
        mnemonic = {lv["level_id"]: lv.get("level_mnemonic") for lv in self.geo_levels()}
        units = [(payload or {}).get("unit") or {}] + list((payload or {}).get("ancestors") or [])
        return [
            {
                "unit_id": u.get("unit_id"),
                "name": u.get("name"),
                "level_id": u.get("level_id"),
                "level_mnemonic": mnemonic.get(u.get("level_id")),
                "parent_unit_id": u.get("parent_unit_id"),
                "status": u.get("status") or "ACTIVE",
            }
            for u in reversed(units)
        ]

    def geo_hierarchy_json(self, unit_id: str) -> Optional[dict]:
        """``geo_code_hierarchy_json`` for a record located at ``unit_id`` — the same
        shape the registry's G2PGeoHierarchyService stores. None if unknown."""
        chain = self.geo_chain(unit_id)
        if not chain:
            return None
        return {"hierarchy": [
            {"level_mnemonic": u["level_mnemonic"], "level_value_mnemonic": u["name"],
             "level_value_id": u["unit_id"]}
            for u in chain
        ]}

    def all_geo_units(self) -> list[dict]:
        """Every active unit of the published geography (all levels, all pages)."""
        return self.geo_units()

    def wait_for_geography(self, timeout: float = 300, interval: float = 5,
                           log: Callable[[str], None] = print) -> list[dict]:
        """Block until MDS serves a geography with units; its levels. Raises on timeout."""
        deadline = time.monotonic() + timeout
        last = ""
        while True:
            try:
                self._levels = None
                levels = self.geo_levels()
                if levels:
                    first, _ = self.post("/catalogue/get_geo_units", self._geo_selector(), page=(1, 1))
                    if (first or {}).get("units"):
                        return levels
                last = "no geography published yet"
            except MdsError as error:
                last = str(error)
            if time.monotonic() >= deadline:
                raise MdsUnavailable("TIMEOUT", f"Master Data has no geography after {timeout:.0f}s ({last})")
            log(f"[mds] waiting for Master Data geography ... ({last})")
            time.sleep(interval)

    # --------------------------------------------------------------- samples

    def sample_individuals(self, **filters) -> list[dict]:
        """The country pack's sample people (testing and demos only), all pages."""
        payload = {k: v for k, v in filters.items() if v is not None}
        return self.paged("/samples/get_individuals", payload, "individuals")

    def sample_households(self, **filters) -> list[dict]:
        """The country pack's sample households (testing and demos only), all pages."""
        payload = {k: v for k, v in filters.items() if v is not None}
        return self.paged("/samples/get_households", payload, "households")

    # ------------------------------------------------------------ code lists

    def list_values(self, list_code: str, *, include_retired: bool = False) -> list[dict]:
        """A code list's values at its latest published version (or the pinned release's)."""
        payload: dict[str, Any] = {"list_code": list_code, "include_retired": include_retired}
        payload.update({"release": self.release} if self.release else {"version": "latest"})
        try:
            return self.paged("/catalogue/get_list_values", payload, "values")
        except MdsNotFound:
            return []


def order_levels(levels: list[dict]) -> list[dict]:
    """Levels top-down, following parent_level_id from the top (the first child at each step)."""
    ids = {lv.get("level_id") for lv in levels}
    by_parent: dict[Any, list[dict]] = {}
    for lv in levels:
        parent = lv.get("parent_level_id")
        by_parent.setdefault(parent if parent in ids else None, []).append(lv)
    ordered, cursor, seen = [], None, set()
    while by_parent.get(cursor):
        level = by_parent[cursor][0]
        if level["level_id"] in seen:
            break
        seen.add(level["level_id"])
        ordered.append(level)
        cursor = level["level_id"]
    return ordered


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("levels", "wait-geo"):
        print(__doc__, file=sys.stderr)
        return 2
    client = MdsClient.from_env(required=True)
    if argv[0] == "levels":
        for i, level in enumerate(client.geo_levels(), 1):
            print(f"{i}\t{level['level_id']}\t{level.get('level_mnemonic')}")
        return 0
    timeout = 300.0
    if "--timeout" in argv:
        timeout = float(argv[argv.index("--timeout") + 1])
    try:
        levels = client.wait_for_geography(timeout=timeout)
    except MdsError as error:
        print(f"[mds] ERROR: {error}. Load a country pack into Master Data "
              "(the master-data chart's geoSeed.countryPack) before seeding the registry.",
              file=sys.stderr)
        return 1
    print("[mds] geography present: " + " > ".join(str(lv.get("level_mnemonic")) for lv in levels))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
