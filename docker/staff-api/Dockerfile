# The registry platform's staff-api image with OpenG2P's Farmer extension
# and the OAN layer on it installed, as OpenG2P's registry repositories build
# theirs. Build from the repository root:
#   docker build -f docker/staff-api/Dockerfile .
ARG BASE_IMAGE_VERSION=1.2.2-rc.625
FROM openg2p/openg2p-registry-staff-api:${BASE_IMAGE_VERSION}

# Selects this registry's domain extension; the platform publishes it as
# openg2p_registry_extensions.
ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_oan_farmer_extension

# OpenG2P's Farmer extension, which the OAN package builds on: a wheel built here from
# one full OpenG2P/farmer-registry commit, the one farmer-extension/pyproject.toml pins
# under [tool.oan.upstream-farmer-extension]. The platform image ships git and pip.
ARG UPSTREAM_FARMER_EXTENSION_REPOSITORY=https://github.com/OpenG2P/farmer-registry.git
ARG UPSTREAM_FARMER_EXTENSION_COMMIT=19597f7c15e13adf93ce85a630bede8a8826b84e
RUN mkdir /tmp/upstream && cd /tmp/upstream \
    && git init -q && git remote add origin "${UPSTREAM_FARMER_EXTENSION_REPOSITORY}" \
    && git fetch -q --depth 1 origin "${UPSTREAM_FARMER_EXTENSION_COMMIT}" && git checkout -q FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "${UPSTREAM_FARMER_EXTENSION_COMMIT}" \
    && pip wheel --no-deps --no-cache-dir --wheel-dir /tmp/upstream-wheel /tmp/upstream/farmer-extension \
    && pip install --no-cache-dir /tmp/upstream-wheel/openg2p_registry_farmer_extension-1.0.3-py3-none-any.whl \
    && rm -rf /tmp/upstream /tmp/upstream-wheel

# The OpenAgriNet layer, openg2p-registry-oan-farmer-extension.
COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension
