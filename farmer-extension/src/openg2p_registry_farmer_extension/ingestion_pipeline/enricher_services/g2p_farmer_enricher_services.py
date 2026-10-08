import logging
from typing import Dict

from openg2p_registry_core.interfaces import G2PPayloadEnricherInterface
from sqlalchemy.orm import Session

from ...ingest_log import log_event, summarize_files

_logger = logging.getLogger('g2p-payload-enricher-service')

def _log_received_submission(data) -> None:
    """Record what reached the registry from the connector: the ODK instance and
    which files came inline and which are only a file name. Never raises: this
    is a log, and the enrichment must not depend on it."""
    try:
        embedded, bare = summarize_files(data)
        instance_id = data.get("__id") if isinstance(data, dict) else None
        log_event(
            "enrich", "submission_received",
            "WARNING" if bare else "INFO",
            instance_id=instance_id,
            files_embedded=len(embedded),
            files_name_only=len(bare),
        )
        for entry in embedded:
            log_event("enrich", "file_received", instance_id=instance_id, **entry)
        for name in bare:
            log_event(
                "enrich", "file_missing", "WARNING", instance_id=instance_id,
                file_name=name,
                reason="only the file name arrived; the connector did not embed the file "
                       "(not uploaded in ODK, over the size limit, download failed, or embedding is off)",
                outcome="saved_without_this_file",
            )
    except Exception as error:  # pragma: no cover - logging must not break ingestion
        _logger.warning("Could not log the received submission: %s", error)


# DCI Payload Enrichers
class G2PDciFarmerCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciFarmerCreateEnricherService")
        _log_received_submission(data)
        return data

class G2PDciFarmerUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciFarmerUpdateEnricherService")
        return data

class G2PDciFarmerDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PDciFarmerDeleteEnricherService")
        return data

# SPDCI Payload Enrichers
class G2PSpdciFarmerCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciFarmerCreateEnricherService")
        return data

class G2PSpdciFarmerUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciFarmerUpdateEnricherService")
        return data

class G2PSpdciFarmerDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PSpdciFarmerDeleteEnricherService")
        return data

# UNDP Payload Enrichers
class G2PUndpFarmerCreateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpFarmerCreateEnricherService")
        return data

class G2PUndpFarmerUpdateEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpFarmerUpdateEnricherService")
        return data

class G2PUndpFarmerDeleteEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data: Dict, session: Session) -> Dict:
        _logger.info("Processing G2PUndpFarmerDeleteEnricherService")
        return data
