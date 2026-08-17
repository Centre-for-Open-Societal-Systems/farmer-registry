# syntax=docker/dockerfile:1

# Farmer Registry unified build definition.
#
# This is one Dockerfile with independent runtime targets. The application is
# still a Compose stack: each target keeps the upstream entrypoint, runtime,
# lifecycle, and least-privilege dependency set required by that component.
# Build every target through `docker compose build`, or select one directly
# with `docker build --target <target> ...`.

ARG RP_VERSION=0.0.0-develop.384
ARG STAFF_UI_VERSION=1.1.1

# ---------------------------------------------------------------- staff API
FROM registry.gitlab.com/openg2p/registry/registry-platform/staff-api:${RP_VERSION} AS staff-api

ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

# The pinned platform declares this awaited method as a plain def. Keep the
# existing farmer overlay fix until the corresponding upstream image is used.
RUN python3 -c "\
import pathlib; \
p = pathlib.Path('/usr/local/lib/python3.12/site-packages/openg2p_registry_core/services/intake_form_data_service.py'); \
s = p.read_text(); \
old = '    def _build_intake_policy_condition('; \
new = '    async def _build_intake_policy_condition('; \
assert s.count(old) == 1, f'expected exactly one match, found {s.count(old)}'; \
p.write_text(s.replace(old, new))"

# -------------------------------------------------------------- partner API
FROM registry.gitlab.com/openg2p/registry/registry-platform/partner-api:${RP_VERSION} AS partner-api

ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

# ------------------------------------------------------------------- celery
FROM registry.gitlab.com/openg2p/registry/registry-platform/celery:${RP_VERSION} AS celery

ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

# ----------------------------------------------------------------- staff UI
FROM openg2p/openg2p-registry-staff-portal-ui:${STAFF_UI_VERSION} AS staff-ui

# Browser-facing origin of the dashboard-ui service, compiled into the client
# bundle by patch-dashboard-nav.js below — changing it needs a rebuild, not a
# restart. The default matches that service's published port in
# docker-compose.yml.
ARG DASHBOARD_URL=http://localhost:3002
ARG DASHBOARD_LABEL=Dashboard

COPY --chown=nextjs:nodejs docker/staff-ui/assets/farm_image.jpeg /app/public/images/common/farm_image.jpeg
COPY --chown=nextjs:nodejs docker/staff-ui/assets/people.svg /app/public/images/common/people.svg
COPY docker/staff-ui/assets/detail-field-wrapping.css /tmp/detail-field-wrapping.css

# Prefer the human-readable form description while retaining the mnemonic as
# a fallback for records that do not yet have a description.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    -e 's/title:e\.form_mnemonic,children:e\.form_mnemonic/title:e.form_description||e.form_mnemonic,children:e.form_description||e.form_mnemonic/g' \
    -e 's/form_name:\([A-Za-z_$][A-Za-z0-9_$]*\)[?]\.form_mnemonic/form_name:\1?.form_description||\1?.form_mnemonic/g' \
    -e 's/form_name:\([A-Za-z_$][A-Za-z0-9_$]*\)\.form_mnemonic/form_name:\1.form_description||\1.form_mnemonic/g' \
    {} +

# Show every configured detail tab directly and allow the existing tab row to
# wrap instead of moving later tabs into the hardcoded More menu.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    's/k=S\.slice(0,5),A=S\.slice(5)/k=S,A=[]/g' \
    {} +

# Use one uncropped Farmer Registry background rather than a repeated tile.
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    's|background-image:url(/images/common/bg_pattern.png)}|background-image:url(/images/common/farm_image.jpeg);background-repeat:no-repeat;background-position:top center;background-size:100% auto}|g' \
    {} +

# Add the extension-only readability and responsive detail-layout rules.
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    -e '$r /tmp/detail-field-wrapping.css' {} \;

# Ignore a legacy dashboard_image value and use the transparent extension
# asset, which removes the people illustration without changing base source.
RUN find '/app/.next/static/chunks/app/[locale]' -maxdepth 1 -type f -name 'page-*.js' -exec sed -i \
    's#let ey=Y?.branding?.dashboard_image||"/images/common/people.svg"#let ey="/images/common/people.svg"#g' \
    {} +

# Preserve file-upload triggers inside editable table cells.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    's/\.table-cell-widget label,/.table-cell-widget label.items-baseline,/g' \
    {} +

# Add a Dashboard control to the header, immediately left of Configuration,
# pointing at the dashboard-ui service. The dashboard is a separate origin and
# the portal is a prebuilt bundle, so it can be neither a route nor a component.
COPY docker/staff-ui/assets/patch-dashboard-nav.js /tmp/patch-dashboard-nav.js
RUN DASHBOARD_URL="${DASHBOARD_URL}" DASHBOARD_LABEL="${DASHBOARD_LABEL}" \
    node /tmp/patch-dashboard-nav.js

# ------------------------------------------------------------------ DB seed
FROM registry.gitlab.com/openg2p/registry/registry-platform/db-seed:${RP_VERSION} AS db-seed

# Remove the reference registry seed before installing Farmer metadata.
RUN rm -rf /seed/meta_data/* /seed/awe_meta_data/* /seed/templates/* /seed/seed-data/*

COPY farmer-extension/src/openg2p_registry_farmer_extension/meta_data/     /seed/meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/awe_meta_data/ /seed/awe_meta_data/
COPY farmer-extension/src/openg2p_registry_farmer_extension/templates/     /seed/templates/
COPY docker/db-seed/seed-data/                                             /seed/seed-data/

COPY docker/db-seed/load_sample_data.py /seed/load_sample_data.py
COPY docker/db-seed/upload_images.py /seed/upload_images.py
COPY docker/db-seed/sync_catalogue_attributes.py /seed/sync_catalogue_attributes.py
COPY docker/db-seed/generate_fr_bulk_sample.py /seed/generate_fr_bulk_sample.py
COPY docker/db-seed/reporting_views.sql /seed/reporting_views.sql
COPY docker/db-seed/reporting.yaml /seed/reporting.yaml

# Overrides the base image's own load_geo_data.py, which loads a generic
# fictional sample pack. LOAD_GEO_DATA=true now loads the real Ethiopia
# hierarchy baked into seed-data/geo/ instead — see load_geo_data.py's
# module docstring for why this is a static snapshot rather than a live
# catalogue-service call at deploy time.
COPY docker/db-seed/load_geo_data.py /seed/load_geo_data.py

RUN chmod +x \
    /seed/load_sample_data.py \
    /seed/upload_images.py \
    /seed/sync_catalogue_attributes.py \
    /seed/generate_fr_bulk_sample.py \
    /seed/load_geo_data.py
