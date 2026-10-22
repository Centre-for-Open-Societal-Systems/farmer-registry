"""HTTP-level regression when Postman's managed CLI is unavailable.

Runs real urllib requests against an isolated Keycloak fixture; never logs
passwords or touches a live identity service. Database behavior is also checked
separately with rollback-only PostgreSQL fixtures in the delivery evidence.
"""
import importlib.util
import json
import os
from pathlib import Path
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from urllib.parse import parse_qs, unquote, urlsplit

spec = importlib.util.spec_from_file_location('staff_access', Path(__file__).parents[1] / 'docker/db-seed/staff_access.py')
seed = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seed)


class Handler(BaseHTTPRequestHandler):
    users = {}
    roles = {'portal': [], 'dashboard': [{'id': 'viewer', 'name': 'Dashboard Viewer'}]}
    writes = []
    fail = False

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.respond('GET')

    def do_POST(self):
        self.respond('POST')

    def do_PUT(self):
        self.respond('PUT')

    def respond(self, method):
        path = urlsplit(self.path)
        params = parse_qs(path.query)
        data = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        body = json.loads(data) if data and self.headers.get('Content-Type') == 'application/json' else None
        result = None
        if self.fail:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'secret-body-must-not-leak')
            return
        if path.path.endswith('/token'):
            result = {'access_token': 'fixture-token'}
        else:
            p = path.path.split('/admin/realms/staff/')[-1].split('/')
            if method != 'GET':
                self.writes.append((method, path.path))
            if p == ['clients']:
                result = [{'id': 'dashboard' if 'dashboard' in params['clientId'][0] else 'portal'}]
            elif p[0] == 'clients' and p[2] == 'roles':
                if method == 'POST':
                    self.roles[p[1]].append({'id': body['name'], 'name': body['name']})
                else:
                    result = self.roles[p[1]] if len(p) == 3 else next(r for r in self.roles[p[1]] if r['name'] == unquote(p[3]))
            elif p == ['users']:
                if method == 'POST':
                    self.users[body['username']] = {**body, 'id': body['username'], 'grants': {}}
                else:
                    result = [u for u in self.users.values() if u['username'] == params['username'][0]]
            elif p[0] == 'users':
                user = self.users[p[1]]
                if len(p) == 2 and method == 'PUT':
                    user.update(body)
                elif len(p) == 3:
                    result = {'clientMappings': {k: {'client': 'farmer-registry-staff-portal' if k == 'portal' else 'farmer-registry-dashboard', 'mappings': v} for k, v in user['grants'].items()}}
                else:
                    user['grants'][p[-1]] = body
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(result).encode() if result is not None else b'')


class StaffSeedTests(unittest.TestCase):
    def setUp(self):
        Handler.users = {}
        Handler.roles = {'portal': [], 'dashboard': [{'id': 'viewer', 'name': 'Dashboard Viewer'}]}
        Handler.writes = []
        Handler.fail = False
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        env = {'STAFF_SEED_ENABLED': 'true', 'STAFF_SEED_REGISTRY': 'farmer',
            'STAFF_SEED_KEYCLOAK_URL': f'http://127.0.0.1:{self.server.server_port}',
            'STAFF_SEED_ADMIN_PASSWORD': 'fixture-admin',
            'STAFF_SEED_CLIENT_ID': 'farmer-registry-staff-portal',
            'STAFF_SEED_DASHBOARD_CLIENT_ID': 'farmer-registry-dashboard',
            'STAFF_SEED_TWO_STAGES': 'true',
            'STAFF_SEED_POLICY_KEYS': '["registry.intake_form.farmer"]',
            'STAFF_SEED_PASSWORD_INTAKE': 'fixture-intake-password',
            'STAFF_SEED_PASSWORD_L1': 'fixture-l1-password',
            'STAFF_SEED_PASSWORD_L2': 'fixture-l2-password'}
        self.environ = patch.dict(os.environ, env)
        self.environ.start()
        self.sql = patch.object(seed, 'execute_sql')
        self.sql.start()

    def tearDown(self):
        self.sql.stop()
        self.environ.stop()
        self.server.shutdown()
        self.server.server_close()

    def test_rerun_preserves_ids_passwords_and_only_l2_dashboard(self):
        seed.main()
        before = {n: (u['id'], u['credentials']) for n, u in Handler.users.items()}
        os.environ['STAFF_SEED_PASSWORD_L1'] = 'changed-input-not-reset'
        seed.main()
        self.assertEqual(before, {n: (u['id'], u['credentials']) for n, u in Handler.users.items()})
        self.assertEqual(len(Handler.users), 3)
        self.assertFalse(any('reset-password' in path for _, path in Handler.writes))
        for name, user in Handler.users.items():
            self.assertEqual('dashboard' in user['grants'], name.endswith('.l2'))

    def test_existing_unexpected_grants_are_not_silently_removed(self):
        seed.main()
        Handler.users['farmer.intake']['grants']['dashboard'] = Handler.roles['dashboard']
        with self.assertRaisesRegex(ValueError, 'Unexpected existing grants'):
            seed.main()
        self.assertIn('dashboard', Handler.users['farmer.intake']['grants'])

    def test_keycloak_error_does_not_expose_response(self):
        Handler.fail = True
        with self.assertRaisesRegex(RuntimeError, 'HTTP 500') as error:
            seed.main()
        self.assertNotIn('secret-body', str(error.exception))

    def test_disabled_seed_makes_no_http_writes(self):
        os.environ['STAFF_SEED_ENABLED'] = 'false'
        seed.main()
        self.assertEqual(Handler.writes, [])

    def test_missing_required_password_creates_no_accounts(self):
        os.environ['STAFF_SEED_PASSWORD_L1'] = 'short'
        with self.assertRaises(ValueError):
            seed.main()
        self.assertEqual(Handler.users, {})


if __name__ == '__main__':
    unittest.main()
