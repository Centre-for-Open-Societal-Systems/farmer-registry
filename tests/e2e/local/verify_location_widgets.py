"""Browser regression of the actual pinned UI widgets against local HTTP fixtures.

Set FARMER_QA_UI_ASSETS to the scratch directory populated by export_widget_assets.cjs.
Requires Python Playwright and its Firefox browser. No deployed service is called.
"""
import functools
import http.server
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[3]
ASSETS = Path(os.environ["FARMER_QA_UI_ASSETS"]).resolve()
spec = importlib.util.spec_from_file_location("metadata", ROOT / "tests/unit/extension/test_metadata_effective_layer.py")
metadata = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metadata)
SCHEMAS = {"location": metadata.effective_schema("farmer_farmer_location_section_03"),
           "livestock": metadata.effective_schema("farmer_livestock_livestock_details_section_01")}
LEVELS = [("region", None, "Oromia"), ("zone", "region", "East Shewa"),
          ("woreda", "zone", "Ada"), ("kebele", "woreda", "Dire 01")]


class FixtureServer(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/schemas.json":
            return self.json_response(SCHEMAS)
        if self.path == "/mount.js":
            self.send_response(200)
            self.send_header("Content-Type", "application/javascript")
            self.end_headers()
            self.wfile.write((Path(__file__).parent / "location_widget_fixture.js").read_bytes())
            return
        super().do_GET()

    def json_response(self, body):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        if self.path.endswith("get-all-g2p-geo-levels"):
            result = [{"level_id": level, "level_mnemonic": level.title(), "parent_level_id": parent}
                      for level, parent, _ in LEVELS]
        elif self.path.endswith("geo-level-values"):
            result = [{"level_value_id": level + "-test", "level_id": level,
                       "level_value_mnemonic": name, "display_name": name,
                       "parent_level_value_id": parent + "-test" if parent else None}
                      for level, parent, name in LEVELS if level == body["level_id"]]
        else:
            self.send_error(501)
            return
        self.json_response(result)


def run():
    static = ASSETS / "static/chunks"
    assert static.is_dir(), "Export public assets from the pinned UI image first"
    chunks = [p for p in static.glob("*.js") if not p.name.startswith(("webpack-", "polyfills-", "main-", "framework-"))]
    webpack = next(static.glob("webpack-*.js"))
    html = '<!DOCTYPE html><html><head>'
    html += ''.join(f'<link rel="stylesheet" href="/{p.relative_to(ASSETS).as_posix()}">' for p in (ASSETS / "static").rglob("*.css"))
    html += '</head><body><div id="root"></div>'
    html += ''.join(f'<script src="/{p.relative_to(ASSETS).as_posix()}"></script>' for p in [webpack, *chunks])
    html += """<script>
      self.webpackChunk_N_E.push([[999999],{},r=>window.req=r]);
      window.React=req(12115);window.widgets=req(97534);
      const id=Object.keys(req.m).find(id=>req.m[id].toString().includes('createRoot=function'));
      window.dom=req(Number(id));
      fetch('/schemas.json').then(r=>r.json()).then(s=>window.schemas=s);
    </script></body></html>"""
    # Only the generated test entrypoint is written; copied UI assets stay untouched.
    with tempfile.NamedTemporaryFile(dir=ASSETS, prefix="widget-qa-", suffix=".html", delete=False) as entry:
        entry.write(html.encode())
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(FixtureServer, directory=str(ASSETS)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.firefox.launch(headless=True)
            try:
                page = browser.new_page()
                page.set_default_timeout(5000)
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}/{Path(entry.name).name}")
                page.wait_for_function("window.schemas && window.widgets")
                page.add_script_tag(url="/mount.js")
                page.evaluate("mount('location',false,{})")
                expect(page.locator("select")).to_have_count(6)
                for index, (level, _, _) in enumerate(LEVELS):
                    page.locator("select").nth(index).select_option(level + "-test")
                page.locator("[data-widget-id=latitude] input").fill("0")
                page.locator("[data-widget-id=longitude] input").fill("38.7469")
                page.locator("[data-widget-id=language_spoken] select").select_option("AMHARIC")
                page.locator("[data-widget-id=local_language] select").select_option("AFAAN_OROMO")
                page.get_by_role("button", name="common.next", exact=True).click()
                page.wait_for_function("saved.length===1 && advanced")
                record = page.evaluate("saved[0].records[0]")
                assert record["latitude"] == 0 and record["longitude"] == 38.7469
                assert record["language_spoken"] == "AMHARIC" and record["local_language"] == "AFAAN_OROMO"
                assert record["geo_lowest_level_value_id"] == "kebele-test"
                assert len(record["geo_code_hierarchy_json"]["hierarchy"]) == 4
                assert page.evaluate("calls.some(c=>c.endpoint==='get-all-g2p-geo-levels')")

                page.evaluate("record=>mount('location',true,record)", record)
                expect(page.locator("body")).to_contain_text("Oromia")
                for field in ("farmer_geo_hierarchy", "latitude", "longitude", "language_spoken", "local_language"):
                    expect(page.locator(f"[data-widget-id={field}]")).to_be_visible()
                for label in ("Region:", "Zone:", "Woreda:", "Kebele:", "Geo Latitude:",
                              "Geo Longitude:", "primary_language:", "local_language:"):
                    expect(page.locator("body")).to_contain_text(label)
                for value in ("East Shewa", "0.0000000", "38.7469000", "Amharic", "Afaan Oromo"):
                    expect(page.locator("body")).to_contain_text(value)

                page.evaluate("mount('livestock',false,{})")
                page.get_by_role("button", name="table.addRecord", exact=True).click()
                page.get_by_role("button", name="common.save", exact=True).click()
                expect(page.get_by_text("This field is required", exact=True)).to_have_count(2)
                assert page.evaluate("saved.length") == 0
                page.locator("tbody select").first.select_option("CATTLE")
                page.get_by_role("button", name="common.save", exact=True).click()
                expect(page.get_by_text("This field is required", exact=True)).to_have_count(1)
                page.locator("tbody input").fill("0")
                page.get_by_role("button", name="common.save", exact=True).click()
                expect(page.get_by_role("button", name="common.save", exact=True)).to_have_count(0)
                page.get_by_role("button", name="common.next", exact=True).click()
                page.wait_for_function("saved.length===1 && advanced")
                assert page.evaluate("saved[0].records[0].head_count") == 0
                assert page.evaluate("saved[0].records[0].livestock_type") == "CATTLE"
                page.evaluate("mount('livestock',false,{})")
                page.get_by_role("button", name="table.addRecord", exact=True).click()
                page.get_by_role("button", name="common.cancel", exact=True).click()
                assert page.evaluate("saved.length") == 0
                assert not errors, errors
                print("PASS: pinned browser Location entry/Next/read-only view; livestock blank/missing-count/zero/cancel")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
        Path(entry.name).unlink()


if __name__ == "__main__":
    run()
