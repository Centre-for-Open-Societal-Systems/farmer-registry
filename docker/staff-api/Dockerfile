# Farmer Registry — Staff Portal API image.
#
# Under the inverted build model the registry-platform publishes the base image
# (platform code + fastapi-common/iam-core runtime + entrypoint/CMD/ENV). This
# image only adds the farmer domain model on top: the farmer-extension is pip-
# installed under its own import name (openg2p_registry_farmer_extension) and
# selected at runtime by REGISTRY_EXTENSION_MODULE (Option C). ENV defaults and
# the migrate+gunicorn CMD are inherited from the base.
#
# RP_VERSION pins the openg2p-registry base image tag. Keep it in lockstep with
# the openg2p-registry chart dependency pinned in helm/openg2p-farmer-registry/Chart.yaml.
#
# Build context = repo root (so farmer-extension/ is reachable).
ARG RP_VERSION=0.0.0-develop.384
FROM registry.gitlab.com/openg2p/registry/registry-platform/staff-api:${RP_VERSION}

# Option C: select farmer's domain model (coexists with the base image's
# reference extension; env picks farmer, no uninstall needed).
ENV REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension

COPY farmer-extension/ /app/farmer-extension/
RUN pip install --no-cache-dir /app/farmer-extension

# Pinned base's openg2p_registry_core declares _build_intake_policy_condition
# as a plain `def` while every call site `await`s it. With no data policies
# configured it hits the early `return None` and `await None` crashes,
# silently swallowed into an empty result — so intake form submission search
# always comes back empty. Fixed upstream as `async def`; patch it in place
# here rather than rebuilding the whole base image off a newer platform tag.
RUN python3 -c "\
import pathlib; \
p = pathlib.Path('/usr/local/lib/python3.12/site-packages/openg2p_registry_core/services/intake_form_data_service.py'); \
s = p.read_text(); \
old = '    def _build_intake_policy_condition('; \
new = '    async def _build_intake_policy_condition('; \
assert s.count(old) == 1, f'expected exactly one match, found {s.count(old)}'; \
p.write_text(s.replace(old, new))"
