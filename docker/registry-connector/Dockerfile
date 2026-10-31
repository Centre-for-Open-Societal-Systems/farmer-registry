# Farmer Registry — connector image.
# OpenG2P registry connector, unmodified, plus the OAN extension (registry signature and
# WebSub content). The extension loads through a .pth file at interpreter start; the
# upstream entrypoint, roles (api, worker, beat, consumer) and files are unchanged.
ARG UPSTREAM_IMAGE=openg2p/registry-connector-api:0.0.0-develop.11@sha256:c018d7d39cdf8e7cf7c6b502aa8bc571acb7a56d8d9eca3654118ff0394087dc
FROM ${UPSTREAM_IMAGE}
USER root
COPY docker/registry-connector/src/ /tmp/registry-connector-extension/
RUN site=$(python -c "import sysconfig; print(sysconfig.get_paths()['purelib'])") \
    && cp -r /tmp/registry-connector-extension/openg2p_registry_connector_extension "$site/" \
    && cp /tmp/registry-connector-extension/openg2p_registry_connector_extension.pth "$site/" \
    && rm -rf /tmp/registry-connector-extension \
    && python -c "from openg2p_connector_service.services.ingestion_service import IngestionService as S; assert getattr(S._wrap_in_g2p_envelope, '_openg2p_registry_connector_extension', False)"
# Admin access settings (admin_auth). The published chart passes no extra environment, so
# they are baked; CONNECTOR_ADMIN_AUTH_* variables override them where a deployment can set them.
COPY docker/registry-connector/admin-auth.json /etc/openg2p-registry-connector-extension/admin-auth.json
USER connector
# Build context = repo root, like the other docker/<component> images.
