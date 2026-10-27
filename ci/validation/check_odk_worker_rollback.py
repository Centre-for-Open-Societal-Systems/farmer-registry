import os,sys,importlib,asyncio,json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
assert os.environ.get("OAN_ODK_ROLLBACK_CHECK") == "local", "Run only as an explicitly selected local rollback check"
sys.modules["openg2p_registry_extensions"]=importlib.import_module("openg2p_registry_oan_extension")
from openg2p_registry_celery_worker.config import Settings
Settings.get_config()
from openg2p_registry_extensions.app import Initializer
Initializer()
from openg2p_fastapi_common.context import get_async_session_maker
from openg2p_registry_celery_worker.tasks import ingest_data_worker as module
worker=importlib.import_module("openg2p_registry_celery_worker.tasks.ingest_data_worker")
from openg2p_registry_core.models import G2PRegistryDocument,G2PIntakeFormSectionDocuments
from openg2p_registry_extensions.register_domain.models import G2PIntakeFormFarmer,G2PIntakeFormLand,G2PIntakeFormCrop
from openg2p_registry_extensions.odk.transform import intake_sections
from sqlalchemy import select
async def main():
    async with get_async_session_maker()() as session:
        document_id=str(uuid4())
        session.add(G2PRegistryDocument(document_id=document_id,document_store_id="synthetic-never-published",bucket="documents",source_filename="synthetic.jpg",created_by="synthetic-odk",created_at=datetime.now()))
        await session.flush()
        d={"basic_info":{"personal_info":{"first_name_english":"Synthetic","father_name_english":"ODK","grandfather_name_english":"Check","gender":"male","date_of_birth":"1980-01-01"}},"household_questions":{"household_head":"yes"},"national_id_section":{"national_fin":"009900000123","identity_document_type":"FAYDA","identity_document":document_id},"land_info":{"land_info_repeat":[{"land_id":"PLOT-1","oan_land_id":str(uuid4()),"land_ownership":"owner","total_land_area":1.0}]},"crop_information":{"crop_repeat":[{"crop_name_rep":"wheat","crop_season":"meher"}]}}
        classified=SimpleNamespace(register_id="a1a4d25a-1cd4-4356-abac-985a0b3c6bcd",intake_form_id="a1a4d25a-1cd4-4356-abac-8782382649",partner_id=None)
        sections=await worker._get_ordered_form_sections(classified.intake_form_id,session)
        transformed=worker._validate_transformed_data_json(classified,SimpleNamespace(transformed_data_json=intake_sections(d)),sections)
        submission_id=await worker._create_submission_async(classified,session)
        await worker._save_sections_async(submission_id,classified,sections,transformed,session)
        farmer=(await session.execute(select(G2PIntakeFormFarmer).where(G2PIntakeFormFarmer.submission_id==submission_id))).scalar_one()
        land=(await session.execute(select(G2PIntakeFormLand).where(G2PIntakeFormLand.submission_id==submission_id))).scalar_one()
        crop=(await session.execute(select(G2PIntakeFormCrop).where(G2PIntakeFormCrop.submission_id==submission_id))).scalar_one()
        docs=(await session.execute(select(G2PIntakeFormSectionDocuments).where(G2PIntakeFormSectionDocuments.submission_id==submission_id))).scalars().all()
        assert farmer.foundational_id=="009900000123"
        assert crop.link_internal_record_id==land.internal_record_id
        assert len(docs)==1 and docs[0].label=="identity_document_1" and docs[0].section_id=="oan_farmer_documents"
        await session.rollback()
        assert await session.get(G2PRegistryDocument,document_id) is None
        print(json.dumps({"native_worker_save":"PASS","sections":len(sections),"land_link":True,"scoped_identity_document":True,"rolled_back":True,"finalized":False}))
asyncio.run(main())
