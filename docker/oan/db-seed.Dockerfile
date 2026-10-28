# The published farmer db-seed image with the OAN metadata layer. Its files sit
# under zz-oan/, so the seed applies them after the farmer's whole tree.
ARG FARMER_VERSION=1.2.1-rc.192
FROM openg2p/openg2p-farmer-registry-db-seed:${FARMER_VERSION}

COPY oan-extension/src/openg2p_registry_oan_extension/meta_data/ /seed/meta_data/zz-oan/

# Domain policy metadata is replaceable seed content. Keep native callback
# registration and machinery; retain old installed policy/task rows in the DB.
RUN rm -f /seed/awe_meta_data/10_approval_policy.sql \
    /seed/awe_meta_data/20_approval_stage.sql /seed/awe_meta_data/30_approver_rule.sql
COPY oan-extension/src/openg2p_registry_oan_extension/awe_meta_data/ /seed/awe_meta_data/zz-oan/

# OAN's templates (meta_data/50_outgestion.sql), uploaded with LOAD_TEMPLATES=true.
# The DCI response is the farmer extension's own template plus OAN's block, so
# it follows the farmer extension on every upgrade.
COPY oan-extension/templates/ /oan/templates/
RUN python3 /oan/templates/build_dci_template.py /seed/templates/openg2p_farmer_to_dci.json.j2 \
        /oan/templates/farmer_reference.json.j2 /seed/templates/oan_farmer_to_dci.json.j2 \
    && cp /oan/templates/oan_farmer_reference_changed.json.j2 /seed/templates/ \
    && cp /oan/templates/oan_farmer_odk_transform.j2 /seed/templates/

# MDS-owned sample input; replace inherited country-specific demo loaders.
COPY docker/db-seed/load_sample_data.py docker/db-seed/master_data_samples.py /seed/
RUN rm -rf /seed/seed-data /openg2p-data/demography \
    && rm -f /seed/generate_fr_bulk_sample.py
# Registry metadata and templates remain extension-owned.
COPY oan-extension/reporting/ /seed/oan-reporting/
COPY oan-extension/reporting/reporting_views.sql /seed/reporting_views.sql

COPY --chmod=755 oan-extension/seed/ /oan/
ENTRYPOINT ["/oan/entrypoint.sh"]
