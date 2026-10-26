"""Production widget/browser regression; fixture requests, real platform Redux/data paths.
Run: uv run --with playwright python run_browser.py --node-modules <assembled-ui/node_modules>
Chrome must be installed. No registry/provider server or credentials are used.
"""
import argparse
import functools
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('--node-modules', type=Path, required=True)
parser.add_argument('--output', type=Path)
parser.add_argument('--chromium', action='store_true', help='Use the pinned Playwright Chromium installed by CI')
args = parser.parse_args()
modules = args.node_modules.resolve()
here = Path(__file__).resolve().parent
checks = []
def check(name, condition):
    assert condition, name
    checks.append(name)
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args): pass

with tempfile.TemporaryDirectory(prefix='popup-flow-browser-') as temporary:
    output = Path(temporary)
    environment = dict(os.environ, NODE_PATH=str(modules))
    subprocess.run(['npx.cmd' if os.name == 'nt' else 'npx', '--yes', '--package=esbuild@0.28.2', 'esbuild', str(here/'harness.tsx'),
        '--bundle', '--jsx=automatic', '--platform=browser', '--outfile='+str(output/'harness.js'),
        # Prefix aliases keep React and all runtime subpaths on one dependency
        # graph even though this harness lives outside the assembled .app tree.
        '--alias:react='+str(modules/'react'),
        '--alias:react-dom='+str(modules/'react-dom'),
        '--alias:react-redux='+str(modules/'react-redux'),
        '--alias:@openg2p/registry-widgets='+str(here/'registry-context.ts'),
        '--alias:real-registry-widgets='+str(modules/'@openg2p/registry-widgets/dist/index.esm.js')],
        env=environment, check=True)
    (output/'index.html').write_text('<!doctype html><div id="root"></div><script src="harness.js"></script>')
    (output/'authorization.html').write_text('<!doctype html><title>Authorization fixture</title>Provider fixture')
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(output)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**({} if args.chromium else {'channel':'chrome'}), headless=True)
            page = browser.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            base = 'http://127.0.0.1:'+str(server.server_port)
            for mode in ['success', 'failure', 'throw', 'no-url', 'close']:
                page.goto(base, wait_until='networkidle')
                try:
                    page.get_by_role('button').first.wait_for(timeout=5000)
                except Exception as error:
                    raise AssertionError('Widget failed to render: '+json.dumps({'page_errors':errors, 'body':page.locator('body').inner_text()[:2000]})) from error
                page.evaluate('(mode)=>window.mode=mode', mode)
                check(mode+': parent has no FIN input', page.locator('input').count() == 0)
                with page.expect_popup() as event:
                    page.get_by_role('button', name='Verify with Fayda', exact=True).click()
                popup = event.value
                field = popup.get_by_label('Fayda ID (FIN)')
                field.wait_for()
                check(mode+': no request before FIN collection', page.evaluate('window.requests.length') == 0)
                if mode == 'close':
                    popup.close()
                    page.wait_for_function('!document.querySelector("button").disabled')
                    check('cancel: no FIN/proof captured', page.evaluate('window.store.getState().widget.values') == {})
                    continue
                # Dispatch the actual helper listener to cover invalid FIN independently of HTML validation.
                for bad in ['', '123', '0012345678901234', 'abcdefgh1234']:
                    field.evaluate("(input,value)=>input.value=value", bad)
                    popup.locator('form').evaluate("form=>form.dispatchEvent(new Event('submit',{cancelable:true}))")
                    check(mode+': invalid FIN rejected '+repr(bad), page.evaluate('window.requests.length') == 0)
                field.fill('001234567890')
                popup.get_by_role('button', name='Continue', exact=True).click()
                if mode in ['success', 'failure']:
                    popup.wait_for_url('**/authorization.html')
                    check(mode+': original popup navigated', not popup.is_closed())
                    page.wait_for_function('!document.querySelector("button").disabled', timeout=10000)
                else:
                    page.wait_for_function('!document.querySelector("button").disabled')
                check(mode+': popup settled', popup.is_closed())
                sent = page.evaluate('window.requests[0][3]')
                check(mode+': FIN preserves leading zeros', sent['foundational_id'] == '001234567890')
                values = page.evaluate('window.store.getState().widget.values.farmer')
                check(mode+': FIN retained', values['fin'] == '001234567890')
                if mode == 'success':
                    check('server success applies proof', values['status'] == 'SUCCESS' and values['proof'] == 'v-1')
                else:
                    check(mode+': remains unverified without proof', 'status' not in values and 'proof' not in values)
                    check(mode+': no approved reference', 'farmer_reference_status' not in values)
            # Failed re-verification must never replace an existing successful identity or its proof.
            for mode in ['throw', 'failure', 'no-url']:
                page.goto(base, wait_until='networkidle')
                saved = {'farmer': {'fin':'009876543210','status':'SUCCESS','proof':'saved-proof','date':'2026-01-01','expiry':'2027-01-01','farmer_reference_status':'APPROVED'}}
                page.evaluate('(value)=>window.seed(value)', saved)
                try:
                    page.get_by_role('button').first.wait_for(timeout=5000)
                except Exception as error:
                    raise AssertionError('Widget failed to render: '+json.dumps({'page_errors':errors, 'body':page.locator('body').inner_text()[:2000]})) from error
                page.evaluate('(mode)=>window.mode=mode', mode)
                with page.expect_popup() as event:
                    page.get_by_role('button', name='Verify again', exact=True).click()
                popup = event.value
                popup.get_by_label('Fayda ID (FIN)').fill('001234567890')
                popup.get_by_role('button', name='Continue', exact=True).click()
                page.wait_for_function('!document.querySelector("button").disabled', timeout=10000)
                check(mode+': existing verified FIN and all proof unchanged', page.evaluate('window.store.getState().widget.values') == saved)
            page.goto(base, wait_until='networkidle')
            with page.expect_popup() as event:
                page.evaluate('window.fixturePopup=window.open("about:blank");window.finResult="pending";window.collectFaydaFin(window.fixturePopup,"","<img src=x onerror=alert(1)>",300).then(value=>window.finResult=value)')
            popup = event.value
            check('prompt rendered safely as text', popup.locator('img').count() == 0)
            page.wait_for_function('window.finResult === null')
            check('timeout settles collection', page.evaluate('window.finResult') is None)
            popup.close()
            check('no browser JavaScript errors', not errors)
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
result = {'passed':len(checks),'checks':checks,'scope':'Production React widget/helper and platform Redux/data paths; deterministic request fixtures, not live eSignet.'}
if args.output:
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
print('PASS', len(checks), 'production popup browser assertions')
