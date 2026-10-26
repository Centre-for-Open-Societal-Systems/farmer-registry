"""Offline native launcher contract: registered OAN services in worker and beat."""
import importlib
import json
import os
import sys

mode = sys.argv[1]
if mode not in {'worker', 'beat'}:
    raise ValueError('Expected worker or beat')
os.environ.setdefault('REGISTRY_CELERY_WORKERS_WORKER_QUEUE', 'owned-oan-worker-probe')
os.environ.setdefault('REGISTRY_CELERY_BEAT_WORKER_QUEUE', 'owned-oan-worker-probe')
module = 'openg2p_registry_celery_worker' if mode == 'worker' else 'openg2p_registry_celery_beat'
app = importlib.import_module(module+'.main').celery_app
before = dict(app.conf.beat_schedule or {})
extra = [x.strip() for x in os.environ.get('CELERY_IMPORTS', '').split(',') if x.strip()]
assert extra == ['openg2p_registry_extensions.worker'], extra
app.conf.update(include=list(app.conf.include or [])+extra)
app.loader.import_default_modules()

from openg2p_fastapi_common.context import component_registry
from openg2p_registry_core.services import G2PIngestService
from openg2p_registry_core.services.intake_form_data_service import G2PIntakeFormDataService
from openg2p_registry_core.services.g2p_register_change_request_service import G2PRegisterChangeRequestService
from openg2p_registry_oan_extension.odk.ingest import OANIngestService
from openg2p_registry_oan_extension.register_domain.services.household_intake import OANIntakeFormDataService
from openg2p_registry_oan_extension.register_domain.services.outgest_json import OANOutgestChangeRequestService

mapping = {}
for base, extension in (
    (G2PIntakeFormDataService, OANIntakeFormDataService),
    (G2PIngestService, OANIngestService),
    (G2PRegisterChangeRequestService, OANOutgestChangeRequestService),
):
    assert isinstance(base.get_component(), extension), base.__name__
    assert sum(isinstance(item, extension) for item in component_registry) == 1, extension.__name__
    mapping[base.__name__] = type(base.get_component()).__name__
assert all(app.conf.beat_schedule.get(key) == value for key, value in before.items())
assert importlib.import_module(extra[0]) is importlib.import_module(extra[0])
print(json.dumps({'mode': mode, 'registered_services': mapping,
                  'native_schedules_preserved': True, 'network_accessed': False}))
