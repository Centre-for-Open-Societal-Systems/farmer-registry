# Narrow COSS intake compatibility overlay on the approved upstream RC.
ARG RP_VERSION=1.2.2-rc.544
FROM openg2p/openg2p-registry-staff-ui:${RP_VERSION}
COPY --chown=nextjs:nodejs docker/staff-ui/assets/coss-intake.js /app/public/coss-intake.js
COPY docker/staff-ui/assets/install-overlay.js /tmp/install-overlay.js
COPY docker/staff-ui/assets/patch-widgets.js /tmp/patch-widgets.js
COPY docker/staff-ui/assets/patch-intake-uploads.js /tmp/patch-intake-uploads.js
COPY docker/staff-ui/rehash-patched-assets.sh /tmp/rehash-patched-assets.sh
RUN cd /app/.next && find static -type f \( -name '*.js' -o -name '*.css' \) -exec md5sum {} + | sort > /tmp/static.before \
    && node /tmp/install-overlay.js && node /tmp/patch-widgets.js && node /tmp/patch-intake-uploads.js \
    && sh /tmp/rehash-patched-assets.sh
