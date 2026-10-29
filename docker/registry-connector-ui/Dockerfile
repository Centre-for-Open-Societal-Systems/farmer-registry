# Farmer Registry — connector admin UI image. OpenG2P's published connector UI, unmodified,
# behind an OpenG2P staff login (keycloak-js, as the AWE and Consent Manager consoles log in).
# oan-admin-login.js takes the page's entry script: it logs in, then adds the bearer token to
# the UI's same-origin API calls and loads the published bundle. The API side checks the role
# (docker/registry-connector, admin_auth). Build context = repo root.
ARG UPSTREAM_IMAGE=openg2p/registry-connector-ui:0.0.0-develop.11@sha256:4debf367c62869f96070b1f3fb1aa2df1065122424350b7346260f8dad11a6f4

FROM node:20-alpine AS keycloak-js
WORKDIR /pkg
RUN npm pack --silent keycloak-js@26.2.0 && tar -xzf keycloak-js-26.2.0.tgz

FROM ${UPSTREAM_IMAGE}
COPY --from=keycloak-js /pkg/package/lib/keycloak.js /usr/share/nginx/html/oan-admin/keycloak.js
COPY docker/registry-connector-ui/oan-admin-login.js /usr/share/nginx/html/oan-admin/login.js
RUN html=/usr/share/nginx/html/index.html \
    && entry=$(sed -n 's#.*<script type="module" crossorigin src="\([^"]*\)"></script>.*#\1#p' "$html") \
    && test -n "$entry" \
    && sed -i "s#<script type=\"module\" crossorigin src=\"$entry\"></script>#<meta name=\"oan-admin-entry\" content=\"$entry\" />\n    <script type=\"module\" src=\"/oan-admin/login.js\"></script>#" "$html" \
    && grep -q 'oan-admin-entry' "$html" && ! grep -q "src=\"$entry\"" "$html"
