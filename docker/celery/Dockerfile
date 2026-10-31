# The registry platform's celery image with the Farmer extension installed, as
# OpenG2P's registry repositories build theirs. Build from the repository root:
#   docker build -f docker/celery/Dockerfile .
ARG BASE_IMAGE_VERSION=1.2.2-rc.614
FROM openg2p/openg2p-registry-celery:${BASE_IMAGE_VERSION}

# Selects this registry's domain extension; the platform publishes it as
# openg2p_registry_extensions.
ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

# Native launcher extension hook, shared by worker and beat.
ENV CELERY_IMPORTS=openg2p_registry_extensions.worker
