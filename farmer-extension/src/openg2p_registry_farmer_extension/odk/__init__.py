"""ODK submissions from the connector service, as Farmer intakes.

The connector polls ODK Central and posts each submission to the Partner API as
a signed envelope (data model mnemonic ODK_TO_FARMER_INTAKE, row id
odk_to_farmer_intake, meta_data/60_odk_ingestion.sql).
Everything here plugs into the platform through its component registry and
Celery's signals; no platform file is changed.

* ingest.py: the Partner API checks the envelope's signature against the
  partner's Partner Management key, and accepts each ODK event only once.
* actor.py: the intake records the ODK collector, not "system", as its creator.
* worker_token.py: the worker finalizes the intake with a client-credentials
  token, so it reaches approval (AWE) like a staff submission.
"""

# The data model row id. The connector names the model by its mnemonic,
# ODK_TO_FARMER_INTAKE; the platform resolves it to this id.
ODK_DATA_MODEL = "odk_to_farmer_intake"


def install() -> None:
    from .actor import install as install_actor
    from .ingest import install as install_ingest

    install_ingest()
    install_actor()
