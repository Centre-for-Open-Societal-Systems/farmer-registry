# ATI household and multi-Farmer native contract

## Finding

The shipped Household Ingestion Intake is one Household plus its HouseholdMember roster and location, not a ready-made complete multi-Farmer form. The generic 1.2 pipeline can represent multiple **non-subject** register rows with explicit native parent IDs, so a metadata-driven Household-subject form with Farmer list sections is a plausible extension. That is a proposed configuration, not demonstrated acceptance. A Farmer-subject ingestion cannot contain multiple Farmer subject rows: the ingestion worker explicitly rejects it. One household submission has one approval workflow/outcome, not independently approvable Farmer rows.

No source/runtime changes or tests were executed for this read-only investigation. Only this document was created. The data preview PR remains pending owner merge; no default-branch or publication bypass was attempted.

## Inspected sources and limits

- Read-only Farmer upstream checkout: `OpenG2P/openg2p-workspace/farmer-registry`, commit `ed1e70ccf18df5476fa404ed8018e12d55e418fa`.
- Read-only registry platform 1.2 checkout: `OpenG2P/openg2p-workspace/registry-platform`, commit `53551e379a710417963ab2ef7c252ba1d1336fff` (branch 1.2).
- Actual ATI v3 workbook in Farmer deploy-develop: SHA-256 `c7b022fc4007bf50a3d8dc9e8555d3eec536156fa16e72b501e031a45d92cfae`; source paths/requiredness also recorded in ATI-MAPPER-AUDIT-20261026.csv. Original COSS mapper comparison: develop `75bb62b58d6ee5a3bd398be40d4ad9a80b5f88ca`.
- Local package source is evidence for that source revision, not proof that an installed wheel or deployment executes identical code. Exact package wheel/image pin comparison and native disposable-DB acceptance remain required. No suitable checked-in end-to-end multi-Farmer example was established by this inspection; code capabilities are not presented as an official supported recipe.

## Shipped metadata

In Farmer `farmer-extension/src/openg2p_registry_farmer_extension/meta_data/register-metadata/`:

- `g2p_intake_form_definitions.sql:1`: `household_ingestion_intake`, form `9055ab43-c85d-4833-bd00-ca657bb72650`, Household register `9055ab43-c85d-4833-bd00-ca657bb72644`, one verification, ingestion-only. Farmer has a separate Farmer-subject ingestion form.
- `g2p_intake_form_ui_tabs.sql:3` and `g2p_intake_form_ui_tab_sections.sql:7` bind household information, household location and household members only. No Farmer identity, Farmer land/crop/input/membership sections are bound to this household form in these base bindings.
- `g2p_register_definitions.sql` defines Household as root; Farmer and HouseholdMember have Household as master; Land and MembershipDetails have Farmer as master; Crop/Livestock/FarmInputs have Land as master. These metadata relationships, not dictionary nesting, determine native allowed parents.
- Household and HouseholdMember schema/model files define household totals/head and person/roster attributes. HouseholdMember is not a Farmer and lacks the complete Farmer socioeconomics/identity/machinery/land graph. OAN adds only its declared member fields; a full source repeat cannot be represented by calling it a member summary.

## Actual service and worker contracts

Paths below are relative to registry platform unless noted.

1. `celery/openg2p-registry-celery-worker/src/openg2p_registry_celery_worker/tasks/ingest_data_worker.py:_validate_transformed_data_json` (around 184-250) accepts a dictionary keyed by **bound section mnemonic**, each value a list of objects. Unknown mnemonics fail. Any section whose section_register_id equals the submission register_id must be non-list and contain exactly one row. Thus two Farmers are invalid when Farmer is the subject.
2. `_save_sections_async` (263) saves bound sections in tab/section order and accumulates rows per section register. `_merge_subject_section_records` (365) keeps one subject ID. `_merge_list_section_records` (414) merges non-subject list sections using explicit IDs or positional matching; it rejects duplicate explicit IDs and unsafe shorter positional lists. Multi-section Farmer identity/name/personal data must use the same explicit IDs and `is_list` semantics throughout; a non-list Farmer section later would require exactly one record and cannot safely carry the whole multi-Farmer batch.
3. `core/openg2p-registry-core/src/openg2p_registry_core/services/intake_form_data_service.py:save_intake_form_submission_with_session` (123) validates section codes/domain rules, upserts every record and deletes missing rows for that register. `_upsert_intake_rows` (415) resolves parent links and invokes domain validate_intake_parent_link. Stable IDs and complete accumulated rows are essential to prevent one section from replacing another Farmer.
4. `services/g2p_intake_form_link_service.py:G2PIntakeFormLinkService` documents and implements zero/one/many parent handling. Immediate parent comes from master_register_id. One parent can auto-link; two or more require explicit link_internal_record_id. Required non-subject children may link only to same-submission parent candidates; only optional subject-parent links may reference a live register row. A Household-subject child Farmer therefore cannot simply point to an existing external household.
5. Farmer `register_domain/models/farmer.py:get_link_internal_record_id` and `models/land.py:get_link_internal_record_id` contain first-row convenience lookups. The inspected core upsert path instead uses the metadata link service; any other execution path invoking those convenience methods must be checked. Do not rely on first-row methods for a multi-Farmer design.
6. `intake_form_data_service.py:finalize_submission_with_session` (586) starts one AWE intake workflow for the submission. Approval (623/695) changes one submission status and queues register ingestion. This is atomic household-submission approval, not per-Farmer decisions.
7. Farmer `services/g2p_intake_form_data_service_farmer.py:finalize_submission_with_session` applies `household_submission_validation.py:validate_household_submission` (86), loading the first Household and all HouseholdMembers. It validates a roster, not full Farmer-to-member identity equivalence or every additional Farmer's verification evidence.
8. `intake_form_register_ingest_worker.py:_get_unique_form_sections` (174) selects one section per register; `_get_intake_rows` (220) loads all rows for that submission; `_process_submission_async` (68) inserts every row of every bound register in one transactional pass. `_insert_register_row` (322) rejects an already-existing register ID. This is create-ingestion, not a way to update an existing member/household. `_resolve_submission_subject_internal_record_id` (373) uses the first primary row with warning if multiple; the ingress one-subject rule must not be bypassed. History/outgest subject references remain the Household for a Household-subject form and need consumer acceptance.

## Proposed native fixture shape (not implemented)

Use one Household as subject. Add OAN-owned list sections for all Farmer fields and children, retaining normal native schemas and extension registration. The names below are proposed mnemonics, not claimed existing metadata.

```json
{
  "oan_household_information": [{"internal_record_id":"HH-UUID","household_head":"Head Fixture Person","size_of_group":2}],
  "oan_household_members": [
    {"internal_record_id":"MEMBER-A","link_internal_record_id":"HH-UUID","first_name":"Head","is_head":true},
    {"internal_record_id":"MEMBER-B","link_internal_record_id":"HH-UUID","first_name":"Other","relationship_to_the_head":"SPOUSE"}
  ],
  "oan_household_farmer_identity": [
    {"internal_record_id":"FARMER-A","link_internal_record_id":"HH-UUID","foundational_id":"001234567890"},
    {"internal_record_id":"FARMER-B","link_internal_record_id":"HH-UUID","foundational_id":"009876543210"}
  ],
  "oan_household_farmer_names": [
    {"internal_record_id":"FARMER-A","first_name":"Head","middle_name":"Fixture","last_name":"Person"},
    {"internal_record_id":"FARMER-B","first_name":"Other","middle_name":"Fixture","last_name":"Person"}
  ],
  "oan_household_farmer_lands": [
    {"internal_record_id":"LAND-A","link_internal_record_id":"FARMER-A","land_id":"PLOT-A"},
    {"internal_record_id":"LAND-B","link_internal_record_id":"FARMER-B","land_id":"PLOT-B"}
  ],
  "oan_household_farmer_crops": [
    {"internal_record_id":"CROP-A","link_internal_record_id":"LAND-A","commodity":"CROP_FOOD_BARLEY"},
    {"internal_record_id":"CROP-B","link_internal_record_id":"LAND-B","commodity":"CROP_TEA"}
  ]
}
```

All IDs above are symbolic fixture placeholders, not executable UUIDs. Complete required household roster, domain fields, geography, dates, documents, season and proof must be supplied by native acceptance fixtures. Independent data attributes are possible structurally; independent approvals are not established by this one-submission shape. Membership links to Farmer; machinery/finance/input and livestock link to each selected Land. Preserve stable IDs across every section, retries and approvals using a supported enrichment contract; no worker fanout/core patches.

## Source branches and bounded next implementation

ATI rows 163-284 collect full additional Farmers under `other_farmers_in_hh/other_farmers_repeat`, including hh_member_national_id_section, hh_member_basic_info, hh_member_socio_economic_data, hh_member_membership, hh_member_land_info, hh_member_crop_information, hh_member_livestock_info, hh_member_agricultural_input, hh_member_access_to_resource, hh_member_access_to_finance and the actual `hh_memeber_farmer_reference_id`. Current and legacy mappings produce household-member summaries only. That behavior remains incomplete relative to source capability.

A bounded next experiment is an isolated OAN household-intake metadata fixture using standard list sections and normal native ingestion with two Farmers, followed by an explicit decision whether one household approval is acceptable. Do not route production until each contract below passes. If separate Farmer approvals are required, use separate supported Farmer submissions linked to an approved Household through an explicitly supported orchestration mechanism; no such automatic orchestration contract is established here.

For source head=yes/member_registered=yes (rows 8,10,12), the referenced existing member is not equivalent to an existing approved head. Current enricher resolves only head=no/head_registered=yes. Safe implementation must identify exact source ownership/reference type, query unique approved membership through supported lookup, preserve existing household/head, and use normal approved changes for head/relationship updates. Creating a Household-subject batch cannot replace those updates. Ambiguous/duplicate references must fail, not choose first.

## Required acceptance / promotion blockers

- Verify exact installed 1.2 wheel/worker hashes against inspected source and bind the proposed form through supported metadata only.
- Native disposable PostgreSQL test: one Household, two Farmer list rows with separate FINs/names, two lands per Farmer, disjoint crops/livestock/inputs/memberships. Save split sections, reorder rows, retry and remove a child; no merged identities, deletions or cross-parent links.
- Reject duplicate IDs, unknown section mnemonics, missing/wrong/foreign links, multiple subject Households, duplicate source submissions and conflicting existing identities.
- Test every source repeat field, requiredness, multilingual names, documents, inherited geography and member?Farmer relationship explicitly. Native roster validation alone does not cover this graph.
- Verify each Farmer's verification proof is bound to its own identity; optional unverified path cannot inherit another row's SUCCESS. Verify domain/claim/household checks run for every Farmer, not only first or submission subject.
- Confirm one AWE household approval semantics, zero live rows before approval, rejection behavior, atomic failure, idempotent retry, functional IDs, history subject links, outgest/notifications and scores for all created Farmers.
- Existing-head/member branches require unique ownership lookup and separate normal changes; cannot insert an existing row through create-only ingestion.
- Live serial acceptance and user review of one-household versus independent-Farmer approval remain necessary. No multi-Farmer production support is claimed from this source inspection.
