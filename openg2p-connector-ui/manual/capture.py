#!/usr/bin/env python3
"""Capture annotated screenshots of the OpenG2P Connector Admin UI.

Annotations are anchored to the *real* DOM elements: we resolve each target
with a Playwright locator, read its true bounding box, and draw a highlight
box plus a numbered badge exactly on it. The textual explanation for each
number lives in the manual's figure caption (not painted on the image), so
nothing overlaps or drifts out of alignment.

Coordinates: Playwright bounding boxes are in CSS pixels; the screenshot is
rendered at ``device_scale_factor`` so we multiply by that factor when drawing.

Run:
    .venv/bin/python capture.py
Environment:
    CONNECTOR_BASE_URL   override the portal URL (default below)
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "screenshots"
ANN_DIR = HERE / "annotated"
RAW_DIR.mkdir(exist_ok=True)
ANN_DIR.mkdir(exist_ok=True)

BASE_URL = os.environ.get("CONNECTOR_BASE_URL", "https://connector.nsr.mowsa.gov.et").rstrip("/")
SCALE = 2  # device_scale_factor

RED = (220, 38, 38, 255)
RED_SOFT = (220, 38, 38, 90)
WHITE = (255, 255, 255, 255)


def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    candidates = (
        ["/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf"]
        if bold else
        ["/System/Library/Fonts/Supplemental/Arial.ttf"]
    ) + ["/System/Library/Fonts/Helvetica.ttc"]
    for c in candidates:
        if Path(c).exists():
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default()


# --- target DSL --------------------------------------------------------------
# A target tells the resolver how to find one element. The numbered badge is
# placed at a corner of that element; the box is drawn around it.

@dataclass
class Target:
    kind: str            # role | placeholder | text | css | label_input | label_select | label_textarea | button
    value: str
    name: str = ""       # accessible name for role
    nth: int = 0
    badge_corner: str = "tl"   # tl|tr|bl|br — where to put the number badge
    pad: int = 6         # extra padding around the element box (css px)


# Generic config payloads injected into the UI before capture, so screenshots
# never expose real hostnames (the page is never saved).
ODK_CFG = (
    '{\n  "base_url": "https://<odk-central-host>",\n  "project_id": 1,\n'
    '  "form_id": "<form-id>",\n  "page_size": 100,\n'
    '  "poll_interval_seconds": 300,\n  "strict_incremental": true\n}'
)
WEBSUB_CFG = (
    '{\n  "hub_url": "https://<websub-hub-host>/hub",\n'
    '  "partner_id": "<partner-id>",\n'
    '  "callback_url": "https://<connector-host>/webhook/by-slug/<your-slug>"\n}'
)


@dataclass
class Scrub:
    target: Target
    text: str


@dataclass
class Capture:
    name: str
    url_path: str
    ready: list[Target] = field(default_factory=list)   # wait until these exist (data loaded)
    targets: list[Target] = field(default_factory=list)
    full_page: bool = True
    settle_ms: int = 800
    # Some routes (/runs, /dlq) collide with API endpoints on the same host and
    # return JSON on a hard navigation. Reach them via client-side nav instead:
    # load url_path, then click the nav link with this accessible name.
    via_nav: str = ""
    # Replace on-screen values (e.g. source config) with generic placeholders.
    scrub: list[Scrub] = field(default_factory=list)


def build_locator(page: Page, t: Target):
    if t.kind == "role":
        loc = page.get_by_role(t.value, name=t.name, exact=False)
    elif t.kind == "button":
        loc = page.get_by_role("button", name=t.value, exact=False)
    elif t.kind == "placeholder":
        loc = page.get_by_placeholder(t.value)
    elif t.kind == "text":
        loc = page.get_by_text(t.value, exact=False)
    elif t.kind == "css":
        loc = page.locator(t.value)
    elif t.kind == "filter_pre":
        loc = page.locator("pre").filter(has_text=t.value)
    elif t.kind == "label_input":
        loc = page.locator("label").filter(has_text=t.value).locator("input")
    elif t.kind == "label_select":
        loc = page.locator("label").filter(has_text=t.value).locator("select")
    elif t.kind == "label_textarea":
        loc = page.locator("label").filter(has_text=t.value).locator("textarea")
    else:
        return None
    return loc.nth(t.nth)


def resolve_box(page: Page, t: Target):
    """Return (x, y, w, h) in *absolute document* CSS pixels, or None.

    We compute the box from getBoundingClientRect + scroll offset (without
    scrolling the page), so coordinates match a full-page screenshot whose
    origin is the document top-left — including elements below the fold.
    """
    try:
        loc = build_locator(page, t)
        if loc is None:
            return None
        handle = loc.element_handle(timeout=3000)
        if not handle:
            return None
        r = handle.evaluate(
            "el => { const b = el.getBoundingClientRect();"
            " return {x: b.left + window.scrollX, y: b.top + window.scrollY,"
            " w: b.width, h: b.height}; }"
        )
    except Exception:
        return None
    if not r or r["w"] <= 0 or r["h"] <= 0:
        return None
    return (r["x"], r["y"], r["w"], r["h"])


def apply_scrub(page: Page, s: Scrub) -> None:
    try:
        loc = build_locator(page, s.target)
        if loc is None:
            return
        handle = loc.element_handle(timeout=3000)
        if not handle:
            return
        handle.evaluate(
            "(el, v) => { const tag = el.tagName.toLowerCase();"
            " if (tag === 'textarea' || tag === 'input') { el.value = v; }"
            " else { el.textContent = v; } }",
            s.text,
        )
    except Exception as e:
        print(f"   · scrub failed ({s.target.kind}:{s.target.value}): {e}")


def _draw_badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, n: int,
                font: ImageFont.FreeTypeFont) -> None:
    r = 17 * SCALE
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=RED, outline=WHITE, width=3 * SCALE)
    txt = str(n)
    b = draw.textbbox((0, 0), txt, font=font)
    draw.text((cx - (b[2] - b[0]) / 2, cy - (b[3] - b[1]) / 2 - b[1]), txt, fill=WHITE, font=font)


def annotate(raw: Path, out: Path, boxes: list[tuple[int, tuple]]) -> None:
    img = Image.open(raw).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    badge_font = _font(20 * SCALE)
    for n, (x, y, w, h) in boxes:
        X, Y, W, H = (x * SCALE, y * SCALE, w * SCALE, h * SCALE)
        pad = 6 * SCALE
        bbox = (X - pad, Y - pad, X + W + pad, Y + H + pad)
        # soft halo then crisp box
        for o in range(4, 0, -1):
            draw.rounded_rectangle(
                (bbox[0] - o, bbox[1] - o, bbox[2] + o, bbox[3] + o),
                radius=10, outline=(220, 38, 38, max(0, 60 - o * 12)), width=2)
        draw.rounded_rectangle(bbox, radius=10, outline=RED, width=4 * SCALE // 2 or 2)
        _draw_badge(draw, bbox[0], bbox[1], n, badge_font)
    Image.alpha_composite(img, overlay).convert("RGB").save(out, "PNG", optimize=True)


def fetch_connector_ids() -> dict:
    """Pull live connector IDs so we can open detail/edit pages."""
    ids = {"poll": None, "websub": None}
    try:
        with urllib.request.urlopen(f"{BASE_URL}/connectors", timeout=15) as r:
            data = json.load(r)
        for c in data:
            if c.get("transport_type") == "websub" and not ids["websub"]:
                ids["websub"] = c["connector_id"]
            if c.get("transport_type") != "websub" and not ids["poll"]:
                ids["poll"] = c["connector_id"]
    except Exception as e:
        print(f"  (could not fetch connector ids: {e})")
    return ids


def build_plan(ids: dict) -> list[Capture]:
    poll = ids.get("poll") or ""
    websub = ids.get("websub") or ""
    plan: list[Capture] = []

    plan.append(Capture(
        name="01-pipeline-list",
        url_path="/",
        ready=[Target("text", "Integration Pipelines"), Target("css", "table")],
        targets=[
            Target("role", "link", "Pipelines"),
            Target("role", "link", "Runs"),
            Target("role", "link", "Dead Letter Queue"),
            Target("role", "link", "New Pipeline"),
            Target("button", "Refresh"),
        ],
    ))

    if poll:
        plan.append(Capture(
            name="02-pipeline-overview",
            url_path=f"/pipelines/{poll}",
            ready=[Target("text", "Total runs")],
            targets=[
                Target("css", "h1"),
                Target("button", "Poll now"),
                Target("button", "Clear idempotency keys"),
                Target("role", "link", "Edit"),
                Target("text", "Configuration"),
            ],
            scrub=[Scrub(Target("filter_pre", "base_url"), ODK_CFG)],
        ))
        plan.append(Capture(
            name="03-pipeline-runs",
            url_path=f"/pipelines/{poll}?tab=runs",
            ready=[Target("text", "Ingestion runs")],
            targets=[
                Target("placeholder", "event id, run id, correlation…"),
                Target("label_select", "Status"),
                Target("button", "Search"),
            ],
        ))
        plan.append(Capture(
            name="04-pipeline-dlq",
            url_path=f"/pipelines/{poll}?tab=dlq",
            ready=[Target("text", "Dead letter queue")],
            targets=[
                Target("placeholder", "dl id, event, error…"),
                Target("label_select", "Category"),
                Target("button", "Search"),
            ],
        ))
        plan.append(Capture(
            name="06-pipeline-edit",
            url_path=f"/edit/{poll}",
            ready=[Target("text", "Edit Pipeline")],
            targets=[
                Target("label_input", "Name"),
                Target("label_select", "Transport Type"),
                Target("label_textarea", "Source Config"),
                Target("button", "Save Changes"),
            ],
            scrub=[Scrub(Target("label_textarea", "Source Config"), ODK_CFG)],
        ))

    plan.append(Capture(
        name="05-pipeline-new",
        url_path="/new",
        ready=[Target("text", "New Pipeline")],
        targets=[
            Target("label_input", "Name"),
            Target("label_input", "Platform"),
            Target("label_select", "Transport Type"),
            Target("label_input", "Sender (Partner Mnemonic)"),
            Target("label_input", "Target Register"),
            Target("button", "Create Pipeline"),
        ],
    ))

    if websub:
        plan.append(Capture(
            name="07-pipeline-edit-websub",
            url_path=f"/edit/{websub}",
            ready=[Target("text", "Edit Pipeline")],
            targets=[
                Target("label_textarea", "Source Config"),
                Target("label_select", "Auth Type"),
                Target("label_input", "Path Slug"),
                Target("button", "Save Changes"),
            ],
            scrub=[Scrub(Target("label_textarea", "Source Config"), WEBSUB_CFG)],
        ))

    plan.append(Capture(
        name="08-global-runs",
        url_path="/",
        via_nav="Runs",
        ready=[Target("text", "Ingestion Runs")],
        settle_ms=5000,
        targets=[
            Target("role", "link", "Runs"),
            Target("button", "Refresh"),
        ],
    ))
    plan.append(Capture(
        name="09-global-dlq",
        url_path="/",
        via_nav="Dead Letter Queue",
        ready=[Target("text", "Dead Letter Queue")],
        settle_ms=5000,
        targets=[
            Target("role", "link", "Dead Letter Queue"),
            Target("button", "Refresh"),
        ],
    ))
    return plan


def capture_one(page: Page, c: Capture) -> bool:
    url = BASE_URL + c.url_path
    print(f"[{c.name}] → {url}" + (f" (nav: {c.via_nav})" if c.via_nav else ""))
    page.goto(url, wait_until="networkidle", timeout=60_000)
    if c.via_nav:
        try:
            page.get_by_role("link", name=c.via_nav, exact=False).first.click(timeout=15_000)
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception as e:
            print(f"   · nav click '{c.via_nav}' failed: {e}")
    for t in c.ready:
        try:
            resolve_loc_wait(page, t)
        except Exception:
            pass
    page.wait_for_timeout(c.settle_ms)
    for s in c.scrub:
        apply_scrub(page, s)
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(150)

    boxes = []
    for i, t in enumerate(c.targets, start=1):
        bb = resolve_box(page, t)
        if bb:
            boxes.append((i, bb))
        else:
            print(f"   · target {i} ({t.kind}:{t.value or t.name}) not found")
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(150)

    raw = RAW_DIR / f"{c.name}.png"
    page.screenshot(path=str(raw), full_page=c.full_page, animations="disabled")
    if boxes:
        annotate(raw, ANN_DIR / f"{c.name}.png", boxes)
        print(f"   ✓ {len(boxes)} markers")
    else:
        # still produce an annotated copy so the doc has a consistent path
        Image.open(raw).convert("RGB").save(ANN_DIR / f"{c.name}.png")
        print("   ✓ no markers (plain)")
    return True


def resolve_loc_wait(page: Page, t: Target) -> None:
    if t.kind == "text":
        page.get_by_text(t.value, exact=False).first.wait_for(timeout=20_000)
    elif t.kind == "css":
        page.locator(t.value).first.wait_for(timeout=20_000)


def _launch(p: Playwright) -> Browser:
    args = {"headless": True, "args": ["--disable-gpu", "--font-render-hinting=medium"]}
    for ch in ("chrome", "chromium"):
        try:
            return p.chromium.launch(channel=ch, **args)
        except Exception:
            continue
    return p.chromium.launch(**args)


def main() -> int:
    ids = fetch_connector_ids()
    print(f"Connector ids: {ids}")
    plan = build_plan(ids)
    print(f"Capturing {len(plan)} screens from {BASE_URL}")
    ok = 0
    with sync_playwright() as p:
        browser = _launch(p)
        ctx: BrowserContext = browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=SCALE,
            locale="en-US",
            color_scheme="light",
            ignore_https_errors=True,
        )
        page = ctx.new_page()
        page.set_default_timeout(30_000)
        for c in plan:
            try:
                capture_one(page, c)
                ok += 1
            except Exception as e:
                print(f"   FAILED {c.name}: {e}")
        browser.close()
    print(f"Done. {ok}/{len(plan)} captured.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
