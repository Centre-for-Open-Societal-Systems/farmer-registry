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
# docker-compose.yml. Pass it empty to build without the Dashboard button, for a
# deployment that runs no dashboard service.
ARG DASHBOARD_URL=http://localhost:3002
ARG DASHBOARD_LABEL=Dashboard

# Publish the Farmer Registry background under its real JPEG filename. The
# compiled CSS declaration is redirected to this asset below.
COPY --chown=nextjs:nodejs docker/staff-ui/assets/farm_image.jpeg /app/public/images/common/farm_image.jpeg
COPY --chown=nextjs:nodejs docker/staff-ui/assets/people.svg /app/public/images/common/people.svg
COPY docker/staff-ui/assets/detail-field-wrapping.css /tmp/detail-field-wrapping.css

# Checksums of the untouched build, so rehash-patched-assets.sh (at the end of
# this stage) can tell which assets the patches below actually changed. Must be
# the same `find ... md5sum | sort` invocation used there.
RUN cd /app/.next && find static -type f \( -name '*.js' -o -name '*.css' \) -exec md5sum {} + | sort > /tmp/static.before

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

# Upload the farmer photo captured during intake.
#
# The widget library pulls any picked image out of the section records before
# the save: it walks each record, and for a File (or a serialized File) it
# stashes the value and blanks the field, then hands the File to the save
# callback as `SectionChanges.image` (minified: `...C?{image:C}:{}`). The
# register-detail save hook uploads that File and stamps the returned
# document_id onto the record as record_image_document_id. The INTAKE save hook
# only ever handled `change.files` and dropped `change.image` on the floor, so a
# photo taken during intake was blanked out of the record and then discarded --
# it never reached the server at all.
#
# Mirror the register hook: upload the image, then stamp record_image_document_id
# onto every record of the section. Anchored on the statement that merges the
# already-uploaded documents back into the upload result, which sits between the
# upload and the save-payload build -- the one point where both the image and
# the records are in scope.
#
#   \1 = that merge statement, kept verbatim
#   \2 = the SectionChanges argument (`i`)
#   \3 = the records list
# `h` is the uploadFile hook and `N` the document array in this build; both are
# matched as single lowercase/uppercase identifiers rather than hardcoded, so an
# identical bundle with a different minifier pass still matches. BusyBox sed is
# POSIX ERE: no backreferences inside the pattern, and | must be bracketed.
RUN find /app/.next -type f -name '*.js' -exec sed -i -E \
    's/([A-Z]=\[\.\.\.\(([a-z])[?]\.files[|][|]\[\]\)\.filter\([a-z]=>[a-z]&&"object"==typeof [a-z]&&"document_id"in [a-z]\),\.\.\.[A-Z]\];)(let [a-z]=\{submission_id:)/\1if(\2?.image)try{let __u=await h([\2.image]),__d=Array.isArray(__u)?__u[0]:null;__d\&\&__d.document_id\&\&(\2.records=(\2.records||[]).map(__r=>__r\&\&"object"==typeof __r?{...__r,record_image_document_id:__d.document_id}:__r))}catch(__e){console.error("intake profile image upload failed",__e)}\3/g' \
    {} +

# ── Add the Dashboard header button ─────────────────────────────────────────
# Puts a Dashboard control immediately left of Configuration, pointing at the
# dashboard-ui service, and passes the page it left behind as ?returnUrl= for
# the dashboard's own Back button to read.
COPY docker/staff-ui/assets/patch-dashboard-nav.js /tmp/patch-dashboard-nav.js
RUN if [ -n "${DASHBOARD_URL}" ]; then \
        DASHBOARD_URL="${DASHBOARD_URL}" DASHBOARD_LABEL="${DASHBOARD_LABEL}" \
        node /tmp/patch-dashboard-nav.js; \
    else \
        echo "DASHBOARD_URL is empty -- building without the Dashboard button"; \
    fi

# Every patch above edited a content-hashed asset in place, and Next serves
# /_next/static as immutable -- a returning browser keeps the OLD file and never
# asks for it again, so a patch can be present on the server and absent from
# every existing tab until a hard refresh. Give each changed asset a new hash
# and rewrite the references to it.
#
# Runs after the dashboard patch above, so an asset that step rewrites is
# re-hashed too -- including when DASHBOARD_URL is empty and it changes nothing.
COPY docker/staff-ui/rehash-patched-assets.sh /tmp/rehash-patched-assets.sh
RUN sh /tmp/rehash-patched-assets.sh && rm -f /tmp/static.before /tmp/static.after

# Fail the build if a bundle patch stopped matching. These seds target MINIFIED
# identifiers, so a STAFF_UI_VERSION bump can silently drop a customisation
# while still exiting 0. Assert the results that must be present.
#
# The Dashboard button is deliberately NOT asserted: it is optional now, and
# absent by design when DASHBOARD_URL is empty.
RUN set -e; \
    here() { if ! grep -rqF "$1" /app/.next 2>/dev/null; then echo "PATCH NOT APPLIED (result missing): $2" >&2; exit 1; fi; }; \
    here 'record_image_document_id:__d.document_id' "intake profile image upload"; \
    here '.table-cell-widget label.items-baseline,' "table-cell upload trigger"; \
    here 'background-image:url(/images/common/farm_image.jpeg)' "farm background"; \
    echo "OK: staff-ui bundle patches verified"
