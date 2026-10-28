# The published farmer db-seed image with the OAN metadata layer. Its files sit
# under zz-oan/, so the seed applies them after the farmer's whole tree.
ARG FARMER_VERSION=1.2.1-rc.192
FROM openg2p/openg2p-farmer-registry-db-seed:${FARMER_VERSION}

COPY oan-extension/src/openg2p_registry_oan_extension/meta_data/ /seed/meta_data/zz-oan/

# Domain policy metadata is replaceable seed content. Keep native callback
# registration and machinery; retain old installed policy/task rows in the DB.
RUN rm -f /seed/awe_meta_data/10_approval_policy.sql \
    /seed/awe_meta_data/20_approval_stage.sql /seed/awe_meta_data/30_approver_rule.sql
COPY oan-extension/src/openg2p_registry_oan_extension/awe_meta_data/ /seed/awe_meta_data/zz-oan/

# OAN's templates (meta_data/50_outgestion.sql, 60_odk_ingestion.sql), uploaded
# with LOAD_TEMPLATES=true under their file names.
# The DCI response is the farmer extension's own template plus OAN's block, so
# it follows the farmer extension on every upgrade.
COPY oan-extension/templates/ /oan/templates/
RUN python3 /oan/templates/build_dci_template.py /seed/templates/openg2p_farmer_to_dci.json.j2 \
        /oan/templates/farmer_reference_block.j2 /seed/templates/farmer_dci_search_response.j2 \
    && cp /oan/templates/farmer_reference_changed_v1.j2 /seed/templates/ \
    && cp /oan/templates/odk_to_farmer_intake.j2 /seed/templates/

COPY oan-extension/reporting/ /seed/oan-reporting/
COPY oan-extension/reporting/reporting_views.sql /seed/reporting_views.sql

# Sample data (LOAD_SAMPLE_DATA=true): the country pack's sample people, read
# from Master Data, registered as Farmers through intake and approval. Their
# farm facts are the same pack's samples/farms.json, from openg2p-data at a
# pinned commit. OpenG2P's own loader stays, unchanged, as the HTTP/AWE helper
# library OAN's loader imports.
ARG OPENG2P_DATA_REPO=https://raw.githubusercontent.com/Centre-for-Open-Societal-Systems/openg2p-data
ARG OPENG2P_DATA_REF=ba31247341e668a8d2d2c7d781d234a3ac988151
ARG FARM_SAMPLES_SHA256=a56c1bb7b72f97d42b1f1c62b005fe3c29facd5dcfdbf99616ac55bb6ce70554
ADD --chmod=644 ${OPENG2P_DATA_REPO}/${OPENG2P_DATA_REF}/packs/ETH-OAN/samples/farms.json /seed/samples/farms.json
RUN echo "${FARM_SAMPLES_SHA256}  /seed/samples/farms.json" | sha256sum -c -     && mv /seed/load_sample_data.py /seed/openg2p_sample_loader.py
COPY --chmod=755 docker/db-seed/load_sample_data.py /seed/load_sample_data.py

COPY --chmod=755 docker/db-seed/entrypoint.sh docker/db-seed/metadata_compat.sql /oan/
ENTRYPOINT ["/oan/entrypoint.sh"]
