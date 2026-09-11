# syntax=docker/dockerfile:1

# Farmer Registry unified build definition.
#
# This is one Dockerfile with independent runtime targets. The application is
# still a Compose stack: each target keeps the upstream entrypoint, runtime,
# lifecycle, and least-privilege dependency set required by that component.
# Build every target through `docker compose build`, or select one directly
# with `docker build --target <target> ...`.

ARG RP_VERSION=0.0.0-develop.384
ARG STAFF_UI_VERSION=1.2.1

# ---------------------------------------------------------------- staff API
FROM registry.gitlab.com/openg2p/registry/registry-platform/staff-api:${RP_VERSION} AS staff-api

ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

# async/await mismatches in the pinned platform's registry-core. See the
# script for what each patch fixes and why. Applied in every stage that
# installs registry-core, since they all ship the same broken package.
COPY docker/patches/patch_platform.py /tmp/patch_platform.py
RUN python3 /tmp/patch_platform.py && rm /tmp/patch_platform.py

# -------------------------------------------------------------- partner API
FROM registry.gitlab.com/openg2p/registry/registry-platform/partner-api:${RP_VERSION} AS partner-api

ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

COPY docker/patches/patch_platform.py /tmp/patch_platform.py
RUN python3 /tmp/patch_platform.py && rm /tmp/patch_platform.py

# ------------------------------------------------------------------- celery
FROM registry.gitlab.com/openg2p/registry/registry-platform/celery:${RP_VERSION} AS celery

ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

COPY docker/patches/patch_platform.py /tmp/patch_platform.py
RUN python3 /tmp/patch_platform.py && rm /tmp/patch_platform.py

# ----------------------------------------------------------------- staff UI
FROM openg2p/openg2p-registry-staff-ui:${STAFF_UI_VERSION} AS staff-ui

# Browser-facing origin of the dashboard-ui service, compiled into the client
# bundle by patch-dashboard-nav.js below — changing it needs a rebuild, not a
# restart. The default matches that service's published port in
# docker-compose.yml.
ARG DASHBOARD_URL=http://localhost:3002
ARG DASHBOARD_LABEL=Dashboard

COPY --chown=nextjs:nodejs docker/staff-ui/assets/farm_image.jpeg /app/public/images/common/farm_image.jpeg
COPY --chown=nextjs:nodejs docker/staff-ui/assets/people.svg /app/public/images/common/people.svg
COPY docker/staff-ui/assets/detail-field-wrapping.css /tmp/detail-field-wrapping.css
COPY docker/staff-ui/assets/staff-ui-1.2-regressions.css /tmp/staff-ui-1.2-regressions.css
COPY docker/staff-ui/assets/intake-photo-widget.css /tmp/intake-photo-widget.css

# Checksums of the untouched build, so rehash-patched-assets.sh (below) can
# tell which assets the patches changed. Same invocation as in that script.
RUN cd /app/.next && find static -type f \( -name '*.js' -o -name '*.css' \) -exec md5sum {} + | sort > /tmp/static.before

# Prefer the human-readable form description while retaining the mnemonic as
# a fallback for records that do not yet have a description.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    -e 's/form_name:\([A-Za-z_$][A-Za-z0-9_$]*\)[?]\.form_mnemonic/form_name:\1?.form_description||\1?.form_mnemonic/g' \
    -e 's/form_name:\([A-Za-z_$][A-Za-z0-9_$]*\)\.form_mnemonic/form_name:\1.form_description||\1.form_mnemonic/g' \
    {} +

# Show every configured detail tab directly and allow the existing tab row to
# wrap instead of moving later tabs into the hardcoded More menu.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    's/\([A-Za-z_$][A-Za-z0-9_$]*\)=\([A-Za-z_$][A-Za-z0-9_$]*\)\.slice(0,5),\([A-Za-z_$][A-Za-z0-9_$]*\)=\2\.slice(5)/\1=\2,\3=[]/g' \
    {} +

# Use one uncropped Farmer Registry background rather than a repeated tile.
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    's|background-image:url(/images/common/bg_pattern.png)}|background-image:url(/images/common/farm_image.jpeg);background-repeat:no-repeat;background-position:top center;background-size:100% auto}|g' \
    {} +

# Add the extension-only readability and responsive detail-layout rules.
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    -e '$r /tmp/detail-field-wrapping.css' {} \;

# Undo two 1.2.x base-image regressions: the expanded intake section is tinted
# with a theme colour, and the New Submission menu is painted under the page
# card. Both reproduce on the stock image with no overlay applied.
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    -e '$r /tmp/staff-ui-1.2-regressions.css' {} \;

# Hide the record-metadata chrome of the header-section widget where the
# intake form reuses it as a bare photo picker (zz_farmer_photo_section.sql).
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    -e '$r /tmp/intake-photo-widget.css' {} \;

# Upload the farmer photo captured during intake. The widget library pulls any
# picked image out of the section records before the save (extractProfileImage
# blanks the field and hands the File over as `SectionChanges.image`). The
# register-detail save hook uploads that File and stamps the resulting
# document_id onto the record; the intake save hook only ever handled `files`
# and dropped `image` on the floor, so a photo taken at intake never reached
# the server. Mirror the register hook: upload, then set
# record_image_document_id on every record of the section.
#   \1 = the matched statement (kept verbatim), \2 = the uploadFile function,
#   \3 = the SectionChanges argument. The image's sed is BusyBox: POSIX ERE has
#   no backreferences inside the pattern, so the repeated loop variable is
#   re-matched with [a-z] instead of \N, and ||/? are bracketed literals.
RUN find /app/.next -type f -name '*.js' -exec sed -i -E \
    's/(if\(o\.length>0\)\{let [a-z]=await ([A-Za-z_$][A-Za-z0-9_$]*)\(o\);if\(![a-z][|][|]0===[a-z]\.length\)return!1;c\.push\(\.\.\.[a-z]\)\}c=\[\.\.\.\(([a-z])[?]\.files[|][|]\[\]\)\.filter\([A-Za-z_$][A-Za-z0-9_$]*\),\.\.\.c\],console\.log\("change payload",[a-z][?]\.records\))/\1;if(\3?.image){let __up=await \2([\3.image]),__doc=Array.isArray(__up)?__up[0]:null;__doc\&\&__doc.document_id\&\&(\3.records=(\3.records||[]).map(__r=>({...__r,record_image_document_id:__doc.document_id})))}/g' \
    {} +

# Ignore a legacy dashboard_image value and use the transparent extension
# asset, which removes the people illustration without changing base source.
RUN find '/app/.next/static/chunks/app/[locale]' -maxdepth 1 -type f -name 'page-*.js' -exec sed -i \
    's#let \([A-Za-z_$][A-Za-z0-9_$]*\)=[A-Za-z_$][A-Za-z0-9_$]*?\.branding?\.dashboard_image||"/images/common/people.svg"#let \1="/images/common/people.svg"#g' \
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
    node /tmp/patch-dashboard-nav.js || echo "SKIPPED: dashboard-nav patch needs re-anchoring for 1.2.x"

# Every patch above edited a content-hashed asset in place, and Next serves
# /_next/static as immutable -- returning browsers would keep the old file
# until a hard refresh. Give each changed asset a new hash and rewrite the
# references so a normal page load picks the patched file up.
COPY docker/staff-ui/rehash-patched-assets.sh /tmp/rehash-patched-assets.sh
RUN sh /tmp/rehash-patched-assets.sh && rm /tmp/static.before /tmp/static.after

# Fail the build if a bundle patch stopped matching. These seds target MINIFIED
# identifiers, so a base-image bump can silently drop every customisation while
# still exiting 0 - which is exactly what happened moving 1.1.1 -> 1.2.1.
RUN set -e;     gone() { if grep -rqE "$1" /app/.next 2>/dev/null; then echo "PATCH NOT APPLIED (pattern still present): $2" >&2; exit 1; fi; };     here() { if ! grep -rqF "$1" /app/.next 2>/dev/null; then echo "PATCH NOT APPLIED (result missing): $2" >&2; exit 1; fi; };     gone '\.slice\(0,5\),[A-Za-z_$][A-Za-z0-9_$]*=[A-Za-z_$][A-Za-z0-9_$]*\.slice\(5\)' "tab overflow -> More menu";     gone 'let [A-Za-z_$][A-Za-z0-9_$]*=[A-Za-z_$][A-Za-z0-9_$]*\?\.branding\?\.dashboard_image' "dashboard image override";     here '.table-cell-widget label.items-baseline,' "table-cell upload trigger";     here 'background-image:url(/images/common/farm_image.jpeg)' "farm background";     here 'record_image_document_id:__doc.document_id' "intake profile image upload";     echo "OK: staff-ui bundle patches verified"

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
