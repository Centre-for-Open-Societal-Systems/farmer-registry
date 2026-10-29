# The registry platform's db-seed image with the Farmer extension's seed, as
# OpenG2P's registry repositories build theirs. The platform image brings the
# entrypoint and the generic machinery (load_geo_data.py, sync_geo_widgets.py,
# upload_templates.py); this image adds the extension's metadata, approval
# policy, templates and reporting views. It carries no sample loader yet, and
# no environment enables one (ci/deploy/deployment.py).
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
