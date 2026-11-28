# OpenG2P staff-api with the OpenAgriNet Farmer Registry installed.
ARG BASE_IMAGE_VERSION=1.2.2-rc.625
FROM openg2p/openg2p-registry-staff-api:${BASE_IMAGE_VERSION}

# Selects this registry's domain extension; the platform publishes it as
# openg2p_registry_extensions.
ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_oan_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension
