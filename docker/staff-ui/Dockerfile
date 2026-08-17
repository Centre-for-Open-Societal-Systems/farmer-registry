# Farmer Registry — Staff Portal UI image.
#
# The registry-platform publishes the whole portal and this repo carried no
# staff-ui image at all, because the portal needs no farmer code: the register
# it renders is described by the metadata farmer-extension seeds, not by a
# frontend build.
#
# It exists now for one reason — the portal has to offer a way into the
# dashboard. The dashboard runs as its own service on its own origin, so it
# cannot be added as a portal route; the portal is a prebuilt Next.js bundle, so
# it cannot be extended with a component either. What is left is patching the
# compiled bundle, which is what patch-dashboard-nav.js does.
#
# RP_VERSION pins the base image tag. Keep it in lockstep with the other images
# and the openg2p-registry chart dependency in
# helm/openg2p-farmer-registry/Chart.yaml — test/test_rp_pin_lockstep.py fails
# the build if they drift.
#
# Build context = repo root.
ARG RP_VERSION=0.0.0-develop.383
FROM registry.gitlab.com/openg2p/registry/registry-platform/staff-ui:${RP_VERSION}

# Browser-facing origin of the dashboard service. It is compiled into the client
# bundle by patch-dashboard-nav.js below, so changing it needs a rebuild.
ARG DASHBOARD_URL=http://dashboard.localtest.me:3001
ARG DASHBOARD_LABEL=Dashboard

# ── Add the Dashboard header button ─────────────────────────────────────────
# Puts a Dashboard control immediately left of Configuration, pointing at the
# dashboard-ui service, and passes the page it left behind as ?returnUrl= for
# the dashboard's own Back button to read.
COPY docker/staff-ui/assets/patch-dashboard-nav.js /tmp/patch-dashboard-nav.js
RUN DASHBOARD_URL="${DASHBOARD_URL}" DASHBOARD_LABEL="${DASHBOARD_LABEL}" \
    node /tmp/patch-dashboard-nav.js
