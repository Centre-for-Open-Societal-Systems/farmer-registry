# Farmer Registry — Staff Portal UI image.
#
# The staff portal publishes the whole application; this image changes only its
# background asset. The portal paints its page background with a Tailwind
# arbitrary value:
#
#     bg-primary-first bg-[url('/images/common/bg_pattern.png')]
#
# The CSS is compiled into the base image, so this overlay publishes the new
# image and redirects that compiled declaration to it. The theme colour beneath
# it still comes from registry_theme_values
# (primary_color_1), seeded by the extension.
#
# It also patches a Dashboard button into the header. The dashboard runs as its
# own service on its own origin, so it cannot be a portal route, and the portal
# ships as a prebuilt Next.js bundle, so it cannot be extended with a component
# either — what is left is patching the compiled bundle, which is what
# patch-dashboard-nav.js does.
#
# Build context = repo root.
ARG STAFF_UI_VERSION=1.1.1
FROM openg2p/openg2p-registry-staff-portal-ui:${STAFF_UI_VERSION}

# Browser-facing origin of the dashboard service. It is compiled into the client
# bundle by patch-dashboard-nav.js below, so changing it needs a rebuild. The
# default matches the dashboard-ui service's published port in
# docker-compose.yml.
ARG DASHBOARD_URL=http://localhost:3002
ARG DASHBOARD_LABEL=Dashboard

# Publish the Farmer Registry background under its real JPEG filename. The
# compiled CSS declaration is redirected to this asset below.
COPY --chown=nextjs:nodejs docker/staff-ui/assets/farm_image.jpeg /app/public/images/common/farm_image.jpeg
COPY --chown=nextjs:nodejs docker/staff-ui/assets/people.svg /app/public/images/common/people.svg
COPY docker/staff-ui/assets/detail-field-wrapping.css /tmp/detail-field-wrapping.css

# The upstream intake selector and submission heading render the machine-facing
# form_mnemonic verbatim. Keep the mnemonic stable for APIs/integrations and
# use the form's human-readable description for display, with the mnemonic as
# fallback. The form_name expressions cover optional and direct property access
# emitted by different Next.js chunks/minifier passes.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    -e 's/title:e\.form_mnemonic,children:e\.form_mnemonic/title:e.form_description||e.form_mnemonic,children:e.form_description||e.form_mnemonic/g' \
    -e 's/form_name:\([A-Za-z_$][A-Za-z0-9_$]*\)[?]\.form_mnemonic/form_name:\1?.form_description||\1?.form_mnemonic/g' \
    -e 's/form_name:\([A-Za-z_$][A-Za-z0-9_$]*\)\.form_mnemonic/form_name:\1.form_description||\1.form_mnemonic/g' \
    {} +

# The upstream detail shell shows only five tabs and moves the remainder into
# a hardcoded More menu. Its tab row already uses flex-wrap, so retain every
# configured tab in the direct list and let narrower screens wrap naturally.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    's/k=S\.slice(0,5),A=S\.slice(5)/k=S,A=[]/g' \
    {} +

# The upstream dashboard repeats the background tile by default. Keep the
# extension-provided image as one responsive backdrop instead. Size it by width
# rather than using `cover`, which crops and magnifies the image on tall pages.
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    's|background-image:url(/images/common/bg_pattern.png)}|background-image:url(/images/common/farm_image.jpeg);background-repeat:no-repeat;background-position:top center;background-size:100% auto}|g' \
    {} +

# Append the Farmer Registry's detail-card wrapping rules to each compiled
# stylesheet. The selectors are scoped to section panels and do not alter
# tables, whose wide layouts should continue to scroll horizontally.
RUN find /app/.next/static/css -type f -name '*.css' -exec sed -i \
    -e '$r /tmp/detail-field-wrapping.css' {} \;

# The dashboard prefers the theme's dashboard_image over people.svg. Ignore
# that legacy value here so the transparent extension asset removes the people
# illustration without changing upstream source code or deleting theme data.
RUN find '/app/.next/static/chunks/app/[locale]' -maxdepth 1 -type f -name 'page-*.js' -exec sed -i \
    's#let ey=Y?.branding?.dashboard_image||"/images/common/people.svg"#let ey="/images/common/people.svg"#g' \
    {} +

# TableWidget hides every <label> inside a table cell so field-name labels
# (e.g. "Phone Number:") don't repeat next to a column header that already
# says it. FileInputWidget's clickable "Upload File" trigger also happens to
# be a <label> wrapping a hidden <input type="file">, so the same blanket
# rule hides the upload button too — a file column in a table renders only
# its max-size hint text, with no way to actually pick a file. Narrow the
# selector to WidgetFieldLabel's stable class signature (flex items-baseline
# min-w-0 max-w-full) instead of a bare `label` tag, which FileInputWidget's
# trigger (inline-flex items-center ...) never matches.
RUN find /app/.next -type f -name '*.js' -exec sed -i \
    's/\.table-cell-widget label,/.table-cell-widget label.items-baseline,/g' \
    {} +

# ── Add the Dashboard header button ─────────────────────────────────────────
# Puts a Dashboard control immediately left of Configuration, pointing at the
# dashboard-ui service, and passes the page it left behind as ?returnUrl= for
# the dashboard's own Back button to read.
COPY docker/staff-ui/assets/patch-dashboard-nav.js /tmp/patch-dashboard-nav.js
RUN DASHBOARD_URL="${DASHBOARD_URL}" DASHBOARD_LABEL="${DASHBOARD_LABEL}" \
    node /tmp/patch-dashboard-nav.js
