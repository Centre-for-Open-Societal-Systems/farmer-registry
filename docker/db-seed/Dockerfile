# The registry platform's db-seed image with the Farmer extension's seed, as
# OpenG2P's registry repositories build theirs. The platform image brings the
# generic machinery (load_geo_data.py, sync_geo_widgets.py, upload_templates.py);
# this image adds the extension's metadata and templates, OpenG2P's Farmer seed
# scripts (docker/db-seed/openg2p/, unchanged) and OAN's steps around them.
# Build from the repository root:  docker build -f docker/db-seed/Dockerfile .
ARG BASE_IMAGE_VERSION=1.2.2-rc.557
FROM openg2p/openg2p-registry-db-seed:${BASE_IMAGE_VERSION}

# The platform image ships the reference registry's seed; only Farmer's is applied.
RUN rm -rf /seed/meta_data/* /seed/awe_meta_data/* /seed/templates/* /seed/seed-data/*

# OpenG2P's Farmer metadata with OAN's layer in zz-oan/, applied after the whole
# Farmer tree. OAN replaces the Farmer approval policy (awe_meta_data/zz-oan/), so
# the extension carries only the Farmer callback registration besides it.
COPY farmer-extension/src/openg2p_registry_farmer_extension/meta_data/     /seed/meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data/ /seed/awe_meta_data/

# Templates are uploaded with LOAD_TEMPLATES=true under their file names
# (*.j2 directly in /seed/templates). The DCI response is the Farmer template
# plus OAN's block (templates/parts/), so it follows the Farmer template.
COPY farmer-extension/src/openg2p_registry_farmer_extension/templates/ /seed/templates/
COPY docker/db-seed/build_dci_template.py /oan/build_dci_template.py
RUN python3 /oan/build_dci_template.py /seed/templates/openg2p_farmer_to_dci.json.j2 \
        /seed/templates/parts/farmer_reference_block.j2 /seed/templates/farmer_dci_search_response.j2

COPY farmer-extension/reporting/ /seed/oan-reporting/
COPY farmer-extension/reporting/reporting_views.sql /seed/reporting_views.sql

# OpenG2P's Farmer seed scripts, unchanged: the entrypoint (AWE policies before
# sample data), the image uploader and the bulk sample generator the chart's
# analytics job runs. OpenG2P's sample loader is kept as the HTTP/AWE helper
# library OAN's loader imports; its Kamuntu seed-data is not shipped.
COPY --chmod=755 docker/db-seed/openg2p/entrypoint.sh /seed/entrypoint.sh
COPY --chmod=755 docker/db-seed/openg2p/load_sample_data.py /seed/openg2p_sample_loader.py
COPY --chmod=755 docker/db-seed/openg2p/upload_images.py docker/db-seed/openg2p/generate_fr_bulk_sample.py /seed/

# Sample data (LOAD_SAMPLE_DATA=true): the country pack's sample people, read
# from Master Data, registered as Farmers through intake and approval. Their
# farm facts are the same pack's samples/farms.json, from openg2p-data at a
# pinned commit.
ARG OPENG2P_DATA_REPO=https://raw.githubusercontent.com/Centre-for-Open-Societal-Systems/openg2p-data
ARG OPENG2P_DATA_REF=ba31247341e668a8d2d2c7d781d234a3ac988151
ARG FARM_SAMPLES_SHA256=a56c1bb7b72f97d42b1f1c62b005fe3c29facd5dcfdbf99616ac55bb6ce70554
ADD --chmod=644 ${OPENG2P_DATA_REPO}/${OPENG2P_DATA_REF}/packs/ETH-OAN/samples/farms.json /seed/samples/farms.json
RUN echo "${FARM_SAMPLES_SHA256}  /seed/samples/farms.json" | sha256sum -c -
COPY --chmod=755 docker/db-seed/load_sample_data.py /seed/load_sample_data.py

COPY --chmod=755 docker/db-seed/entrypoint.sh docker/db-seed/metadata_compat.sql /oan/
ENTRYPOINT ["/oan/entrypoint.sh"]
