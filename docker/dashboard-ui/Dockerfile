# Farmer Registry — dashboard UI image.
#
# The analytics dashboard is a self-contained Next.js app in dashboard-ui/. It is
# a separate service rather than part of the Staff Portal because the portal
# ships as a prebuilt image that cannot be extended with new routes — the portal
# only gains a header button that navigates here (docker/staff-ui/assets/
# patch-dashboard-nav.js).
#
# It reads the registry database this stack runs — the same one the Staff Portal's
# API writes to — plus master-data for the country pack behind the geography
# filters. Both connections are configured by the DB_*/MD_DB_* variables on the
# dashboard-ui service in docker-compose.yml and are only ever used for SELECTs.
#
# This is NOT the Superset bundle in docker/dashboards. That one ships charts for
# the G2P Insight deployment; this is the in-product dashboard the portal links
# to, and the two share no code.
#
# Node 24 rather than 20: the lockfile is resolved by npm 11, which older images
# ship too old a npm to read with `npm ci`, and one transitive dependency
# declares node >=22.
#
# Build context = repo root.
FROM node:24-slim AS builder
WORKDIR /build

# Copied on their own so the dependency layer survives source-only changes.
COPY dashboard-ui/package.json dashboard-ui/package-lock.json ./
# package-lock.json must be regenerated under Linux — the tree npm builds there
# hoists dependencies that a macOS-resolved lockfile does not list, and `npm ci`
# rejects the difference:
#
#     docker run --rm -v "$PWD":/w -w /w node:24-slim npm install --package-lock-only
#
# Optional dependencies have to stay: Tailwind's oxide compiler and lightningcss
# ship as platform-specific optional binaries, and the CSS build fails without
# them.
RUN npm ci

COPY dashboard-ui/ ./

# Baked into the client bundle, so the Back button knows where the portal is.
ARG NEXT_PUBLIC_PORTAL_URL=http://portal.localtest.me:3000
ENV NEXT_PUBLIC_PORTAL_URL=${NEXT_PUBLIC_PORTAL_URL}

ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build


FROM node:24-slim AS runner
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

# The standalone output carries its own minimal node_modules; static assets and
# public/ are not included in it and have to come across separately.
COPY --from=builder /build/.next/standalone ./
COPY --from=builder /build/.next/static ./.next/static
COPY --from=builder /build/public ./public

USER node
EXPOSE 3000
CMD ["node", "server.js"]
