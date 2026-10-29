# The registry staff UI with the farmer overlay (ui/staff-ui/overrides/) on top:
# upstream's own build (registry-platform ui/staff-ui/Dockerfile), from the
# commit of the published image it replaces, so the overlay is the only
# difference. Build from the repository root:
#   docker build -f docker/staff-ui/Dockerfile .
# BASE_IMAGE_VERSION is the org.opencontainers.image.revision label of
# openg2p/openg2p-registry-staff-ui:1.2.2-rc.614.
FROM node:20-alpine AS base
WORKDIR /app

FROM base AS source
ARG BASE_IMAGE_VERSION=ca399ed3110f6f93d607bd406b22933554adcc5e
RUN apk add --no-cache git \
 && git init -q /src && cd /src \
 && git remote add origin https://github.com/OpenG2P/registry-platform.git \
 && git fetch -q --depth 1 --filter=blob:none origin "$BASE_IMAGE_VERSION" \
 && git sparse-checkout set ui/staff-ui \
 && git checkout -q FETCH_HEAD

FROM base AS builder
COPY --from=source /src/ui/staff-ui/package.json /src/ui/staff-ui/package-lock.json ./
RUN npm ci --no-audit --no-fund --loglevel=error
COPY --from=source /src/ui/staff-ui/ ./
COPY ui/staff-ui/overrides/ ./
RUN rm -f .gitkeep
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM base AS runner

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0
ENV NEXT_TELEMETRY_DISABLED=1

RUN addgroup --system --gid 1001 nodejs \
    && adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
