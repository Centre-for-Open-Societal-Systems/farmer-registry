"""Exercise the real FastAPI upload handler with platform boundaries mocked.

These tests do not replace verification with the pinned platform middleware.
"""
import importlib
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from bulk_import_test_support import PREFIX

controller = importlib.import_module(PREFIX + '.bulk_import.controller')


class ControllerTests(unittest.TestCase):
    def setUp(self):
        def permissions(values):
            def decorate(fn): fn.permissions = set(values); return fn
            return decorate
        def auth(fn): fn.requires_auth = True; return fn
        class AppError(Exception): pass
        def module(name, **attributes):
            obj = types.ModuleType(name); obj.__dict__.update(attributes); return obj
        self.modules = {
            'iam_core.user_auth.decorators': module('decorators', get_required_permissions=lambda fn: getattr(fn, 'permissions', None), require_permissions=permissions, requires_auth=auth),
            'openg2p_fastapi_common.context': module('context', dbengine=types.SimpleNamespace(get=lambda: None)),
            'openg2p_fastapi_common.errors.base_exception': module('errors', BaseAppException=AppError),
            'openg2p_registry_core.models': module('models', G2PIntakeFormDefinition=object),
            'openg2p_registry_core.errors': module('registry_errors', G2PRegistryException=type('RegistryError', (Exception,), {})),
            'openg2p_registry_core.services': module('services', G2PIntakeFormDataService=types.SimpleNamespace(get_component=lambda: object())),
            'sqlalchemy': module('sqlalchemy', select=lambda x: x),
            'sqlalchemy.ext.asyncio': module('asyncio', async_sessionmaker=lambda *a, **k: object()),
        }
        self.app = FastAPI()
        @self.app.post('/intake-form-data/save_intake_form_submission')
        @permissions({'create'})
        async def save(): pass
        @self.app.post('/intake-form-data/finalize_intake_form_submission')
        @permissions({'submit'})
        async def finalize(): pass
        with patch.dict(sys.modules, self.modules):
            controller.register_bulk_import_routes(self.app)

    def client(self, authenticated=True):
        if authenticated:
            @self.app.middleware('http')
            async def identity(request, call_next):
                request.state.auth = types.SimpleNamespace(sub='staff-123', credentials='token')
                return await call_next(request)
        return TestClient(self.app)

    def test_permissions_inherit_both_operations(self):
        routes = []
        for route in self.app.routes:
            candidates = getattr(getattr(route, 'original_router', None), 'routes', [route])
            routes.extend(r for r in candidates if getattr(r, 'path', '').startswith('/farmer/bulk-import'))
        self.assertEqual(len(routes), 2)
        for route in routes:
            self.assertEqual(route.endpoint.permissions, {'create', 'submit'})
            self.assertTrue(route.endpoint.requires_auth)

    def test_requires_identity_even_if_middleware_disabled(self):
        with self.client(False) as client:
            response = client.post('/farmer/bulk-import', data={'form_id': 'form'}, files={'file': ('a.csv', b'first_name,father_first_name\nA,B')})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(client.get('/farmer/bulk-import/forms').status_code, 401)

    def test_upload_invokes_service_with_trusted_actor(self):
        handler = AsyncMock(return_value={'total': 1, 'successful': 1, 'failed': 0, 'results': []})
        with patch.object(controller, 'import_rows', handler), self.client() as client:
            response = client.post('/farmer/bulk-import', data={'form_id': 'form', 'created_by': 'forged'}, files={'file': ('a.csv', b'first_name,father_first_name\nA,B')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(handler.call_args.args[1:5], ('form', 'staff-123', 'staff-123', 'token'))
        self.assertEqual(response.json()['response_header']['response_status'], 'SUCCESS')

    def test_bad_file_never_reaches_persistence(self):
        handler = AsyncMock()
        with patch.object(controller, 'import_rows', handler), self.client() as client:
            response = client.post('/farmer/bulk-import', data={'form_id': 'form'}, files={'file': ('a.xlsx', b'broken')})
        self.assertEqual(response.status_code, 400)
        handler.assert_not_called()

    def test_does_not_register_in_partner_api(self):
        app = FastAPI()
        with patch.dict(sys.modules, self.modules): controller.register_bulk_import_routes(app)
        self.assertFalse(any(getattr(r, 'path', '').startswith('/farmer') for r in app.routes))

    def test_discovers_intake_handlers_in_included_router(self):
        from fastapi import APIRouter
        app = FastAPI()
        router = APIRouter()
        for route in self.app.routes:
            if getattr(route, 'path', '').startswith('/intake-form-data'):
                router.add_api_route(route.path, route.endpoint, methods=['POST'])
        app.include_router(router)
        with patch.dict(sys.modules, self.modules):
            controller.register_bulk_import_routes(app)
        with TestClient(app) as client:
            self.assertIn('/farmer/bulk-import', client.get('/openapi.json').json()['paths'])

    def test_missing_authorization_metadata_fails_closed(self):
        self.app.routes[4].endpoint.permissions = None
        with patch.dict(sys.modules, self.modules), self.assertRaises(RuntimeError):
            controller.register_bulk_import_routes(self.app)


if __name__ == '__main__': unittest.main()
