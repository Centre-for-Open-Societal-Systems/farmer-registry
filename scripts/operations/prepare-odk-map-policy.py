#!/usr/bin/env python3
"""Prepare an Enketo-only Nginx referrer fix; never connect to or alter a server."""

import argparse
import hashlib
import json
from pathlib import Path


COMMON = "/usr/share/odk/nginx/common-headers.conf"
ENKETO = "/usr/share/odk/nginx/enketo-headers.conf"
POLICY = "add_header Referrer-Policy same-origin;"


def prepare(template, headers):
    start_marker = "  location ~ ^/(?:-|enketo-passthrough)(?:/|$) {"
    end_marker = "  # End of Enketo Configuration."
    if template.count(start_marker) != 1 or template.count(end_marker) != 1:
        raise ValueError("Expected exactly one known Enketo proxy block; review live configuration")
    start, end = template.index(start_marker), template.index(end_marker)
    block = template[start:end]
    include = "include " + COMMON + ";"
    if end <= start or block.count(include) != 1:
        raise ValueError("Unexpected Enketo headers include; review live configuration")
    if headers.splitlines().count(POLICY) != 1 or sum(
        "Referrer-Policy" in line and not line.lstrip().startswith("#")
        for line in headers.splitlines()
    ) != 1:
        raise ValueError("Unexpected referrer policy; review live configuration")
    replacement = block.replace(include, "include " + ENKETO + ";")
    return (
        template[:start] + replacement + template[end:],
        headers.replace(POLICY, "add_header Referrer-Policy strict-origin-when-cross-origin;"),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--headers", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    original = args.template.read_text(encoding="utf-8")
    headers = args.headers.read_text(encoding="utf-8")
    template, enketo_headers = prepare(original, headers)
    # Never overwrite an existing review or write into either input directory.
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    files = {
        "odk.conf.template": template,
        "enketo-headers.conf": enketo_headers,
        # Relative bind paths resolve against the FIRST compose file, so use
        # absolute paths and run this helper on the destination host.
        "compose-map-policy.json": json.dumps({"services": {"nginx": {"volumes": [
            {"type": "bind", "source": str((args.output / "odk.conf.template").resolve()),
             "target": "/usr/share/odk/nginx/odk.conf.template", "read_only": True},
            {"type": "bind", "source": str((args.output / "enketo-headers.conf").resolve()),
             "target": ENKETO, "read_only": True},
        ]}}}, indent=2) + "\n",
    }
    checksums = {}
    for name, content in files.items():
        path = args.output / name
        path.write_bytes(content.encode("utf-8"))
        path.chmod(0o600)
        checksums[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = {"liveApplied": False, "scope": "Enketo proxy only", "sha256": checksums}
    path = args.output / "review.json"
    path.write_bytes((json.dumps(report, indent=2) + "\n").encode())
    path.chmod(0o600)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
