# The registry platform's staff-api image with the Farmer extension installed, as
# OpenG2P's registry repositories build theirs. Build from the repository root:
#   docker build -f docker/staff-api/Dockerfile .
# BASE_IMAGE_VERSION is rpVersion of init.yaml, passed by ci/build/images.sh; no default.
ARG BASE_IMAGE_VERSION
FROM openg2p/openg2p-registry-staff-api:${BASE_IMAGE_VERSION}

# Selects this registry's domain extension; the platform publishes it as
# openg2p_registry_extensions.
ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension
