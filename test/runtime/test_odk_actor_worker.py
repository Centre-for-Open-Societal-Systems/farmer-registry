"""Run with the built worker image; persistence/network boundaries are spies."""
import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

sys.modules["openg2p_registry_extensions"] = importlib.import_module("openg2p_registry_farmer_extension")
intake = importlib.import_module("openg2p_registry_celery_worker.tasks.ingest_data_worker")
change = importlib.import_module("openg2p_registry_celery_worker.tasks.change_request_ingest_worker")


class Session:
    def __init__(self, classified, enriched):
        self.classified, self.enriched = classified, enriched
        self.flush = AsyncMock()
        self.commit = AsyncMock()
        self.add = lambda row: None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def begin(self):
        return self

    async def get(self, model, identity):
        assert identity == "synthetic-ingest"
        return self.classified if model is intake.IncomingClassifiedData else self.enriched


def fixture(action, name):
    classified = SimpleNamespace(ingest_id="synthetic-ingest", intake_form_id="form", register_id="farmer",
                                 data_model_id="odk_to_farmer_intake", partner_id="farmer-partner",
                                 pipeline_action=action, ingestion_number_of_attempts=0)
    enriched = SimpleNamespace(enriched_data_json={"__system": {"submitterName": name}},
                               transformed_data_json={"personal": [{"first_name": "Synthetic"}]})
    return classified, enriched, Session(classified, enriched)


class ActorRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_intake_worker_persists_odk_name_on_submission_and_sections(self):
        service = SimpleNamespace(create_submission_with_session=AsyncMock(return_value=SimpleNamespace(submission_id="synthetic-submission")),
                                  save_intake_form_submission_with_session=AsyncMock())
        section = SimpleNamespace(section_id="personal", section_mnemonic="personal",
                                  section_register_id="farmer", is_list=False)
        for name in ("Field Officer A", "Field Officer B"):
            classified, enriched, session = fixture("ADD", name)
            with patch.object(intake, "_session_maker", return_value=session), \
                 patch.object(intake, "_get_ordered_form_sections", AsyncMock(return_value=[section])), \
                 patch.object(intake, "_prepare_submission_for_ingestion", AsyncMock(return_value=(None, False))), \
                 patch.object(intake.G2PIntakeFormDataService, "get_component", return_value=service), \
                 patch.object(intake, "_finalize_submission_async", AsyncMock()), \
                 patch.object(intake.NotificationHelper, "dispatch_intake_form_notification", AsyncMock()):
                await intake._process_ingestion_async("synthetic-ingest")
            assert service.create_submission_with_session.await_args.kwargs["created_by"] == name
            assert service.save_intake_form_submission_with_session.await_args.kwargs["created_by"] == name
            assert service.create_submission_with_session.await_args.kwargs["partner_id"] == "farmer-partner"
            assert classified.ingestion_status == "PROCESSED"

    async def test_actual_change_request_worker_persists_odk_name_and_partner(self):
        classified, enriched, session = fixture("UPDATE", "Change Collector")
        service = SimpleNamespace(create_change_request=AsyncMock(return_value=SimpleNamespace(change_request_id="synthetic-change")))
        with patch.object(change, "_session_maker", return_value=session), \
             patch.object(change, "_build_change_request_payload_async", AsyncMock(return_value=object())), \
             patch.object(change.G2PChangeRequestWorkerService, "get_component", return_value=service), \
             patch.object(change.NotificationHelper, "dispatch_change_request_notification", AsyncMock()):
            await change._process_change_request_ingest_async("synthetic-ingest")
        assert service.create_change_request.await_args.kwargs["created_by"] == "Change Collector"
        assert service.create_change_request.await_args.kwargs["source_partner_id"] == "farmer-partner"
        assert classified.change_request_id == "synthetic-change"

    def test_build_patches_rerun_on_the_actual_pinned_platform(self):
        spec = importlib.util.spec_from_file_location("patch_odk_actor", "/repo/docker/celery/assets/patch_odk_actor.py")
        patcher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(patcher)
        patcher.patch(Path(intake.__file__), patcher.INTAKE_REPLACEMENTS)
        patcher.patch(Path(change.__file__), patcher.CHANGE_REPLACEMENTS)


if __name__ == "__main__":
    unittest.main()
