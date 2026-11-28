"""Identity enricher for "Import from file".

A file row is flat and the Jinja template (templates/farmer_file_import_intake.j2)
maps it to the intake sections alone, so nothing is enriched before the
transform runs. Livestock registers the same class under the same name.
"""
import logging

from openg2p_registry_core.interfaces import G2PPayloadEnricherInterface

_logger = logging.getLogger("g2p-payload-enricher-service")


class G2PPassThroughEnricherService(G2PPayloadEnricherInterface):
    def enrich(self, data, session):
        _logger.info("Processing G2PPassThroughEnricherService (identity pass-through)")
        return data
