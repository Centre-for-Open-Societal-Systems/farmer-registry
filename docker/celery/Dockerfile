# The published farmer celery image with the OAN extension on top. Build from the
# repository root:  docker build -f docker/celery/Dockerfile .
ARG FARMER_VERSION=1.2.1-rc.192
FROM openg2p/openg2p-farmer-registry-celery:${FARMER_VERSION}

COPY oan-extension/ /app/oan-extension/
RUN pip install --no-cache-dir --no-deps /app/oan-extension
ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_oan_extension

# Native launcher extension hook, shared by worker and beat.
ENV CELERY_IMPORTS=openg2p_registry_extensions.worker
