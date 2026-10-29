# The registry platform's db-seed image with the Farmer extension's seed, as
# OpenG2P's registry repositories build theirs. The platform image brings the
# entrypoint and the generic machinery (load_geo_data.py, sync_geo_widgets.py,
# upload_templates.py); this image adds the extension's metadata, approval
# policy, templates and reporting views, and the Farmer sample loader (run only
# with LOAD_SAMPLE_DATA=true, which no environment enables: ci/deploy/deployment.py).
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

# Templates are uploaded with LOAD_TEMPLATES=true under their file names.
COPY farmer-extension/src/openg2p_registry_farmer_extension/templates/ /seed/templates/

COPY farmer-extension/reporting/ /seed/oan-reporting/
COPY farmer-extension/reporting/reporting_views.sql /seed/reporting_views.sql

# Sample data (LOAD_SAMPLE_DATA=true). The platform image checks out openg2p-data
# at /openg2p-data; this one checks out our fork at a pinned commit in its place,
# the source of the ETH-OAN pack's farm facts (samples/farms.json). The sample
# people come from Master Data's API.
ARG OPENG2P_DATA_REPO=https://github.com/Centre-for-Open-Societal-Systems/openg2p-data.git
ARG OPENG2P_DATA_REF=dc7e7bf69087b4684a3608fdd4bf98100aab77a8
RUN rm -rf /openg2p-data && mkdir -p /openg2p-data && cd /openg2p-data \
    && git init -q && git remote add origin ${OPENG2P_DATA_REPO} \
    && git fetch -q --depth 1 origin ${OPENG2P_DATA_REF} && git checkout -q FETCH_HEAD \
    && rm -rf .git

# mds_client.py is the registry platform's Master Data client
# (OpenG2P/registry-platform docker/db-seed/mds_client.py at e7e6e269), unchanged.
# Platform images after rc.557 ship it as /seed/mds_client.py; drop this copy
# when the platform pin moves past it.
COPY --chmod=755 docker/db-seed/mds_client.py docker/db-seed/load_sample_data.py /seed/

# OAN theme: the staff-portal theme (palette and background image) is data in
# openg2p-data (themes/oan_theme). Render this registry's entry into the seed
# tree; it runs after the registry configuration and points it at oan_theme.
# The ref is a commit SHA; move the repository to the COSS copy once merged there.
ARG OAN_THEME_DATA_REPO=https://github.com/asmitonweb/openg2p-data.git
ARG OAN_THEME_DATA_REF=3c44950dac7d7752054057d1f3500784af596c10
RUN mkdir -p /tmp/oan-theme-data /seed/meta_data/zz-oan \
 && cd /tmp/oan-theme-data \
 && git init -q \
 && git fetch -q --depth 1 "${OAN_THEME_DATA_REPO}" "${OAN_THEME_DATA_REF}" \
 && git checkout -q FETCH_HEAD \
 && python3 scripts/themes/build_theme_sql.py farmer > /seed/meta_data/zz-oan/90_oan_theme.sql \
 && cd / && rm -rf /tmp/oan-theme-data
