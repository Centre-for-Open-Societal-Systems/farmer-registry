# ATI Farmer mapper audit

Source: Farmer deploy-develop `odk/ATI_Farmers_Profile_ODK_Form_v3.xlsx`, SHA-256 c7b022fc4007bf50a3d8dc9e8555d3eec536156fa16e72b501e031a45d92cfae. The [102 main survey leaf rows](ATI-MAPPER-AUDIT-20261026.csv) include exact row, full group path, source type, requiredness and relevance. Additional Farmer repeat leaves are assessed separately below. Read-only COSS develop baseline 75bb62b58d6ee5a3bd398be40d4ad9a80b5f88ca `odk/templates/farmer_transform.j2` was compared with the current native section mapper. No workbook, upstream, worker, service, metadata or pipeline file was edited in this task.

## Pure mapper corrections

- Root sibling resource/finance groups merge with agricultural input, preserving all four finance answers under actual `access_to_finance/finance` and all machinery answers using the approved nine-code data contract. Existing native exact aliases remain; unknown standaloneharvester stays unknown.
- Root parent-group crop/livestock water answers survive in farm-input multiselects. Equivalent nested input groups remain supported. Native child_land still rejects ambiguous parent linkage.
- Main Farmer farming type is retained directly, and optional email maps to the platform person `emails` list. This needs native section-save/approval acceptance because no current email widget establishes section inclusion.
- Membership `other_primary_cooperative` and `other_coop_union` replace the literal other selection. Nested additional_farmers question sets the existing household flag.
- Additional member source `hh_memeber_farmer_reference_id` and its first stored nested certificate map to existing HouseholdMember fields. This preserves the legacy summary behavior without claiming complete Farmer registration.
- Mapping copies source repeat lists before aggregation and does not mutate the input submission.

Six pure source-shaped regressions pass without platform/database initialization. Existing platform-dependent mapper suites remain the lead agent's integration responsibility. No shared-tree staging or commit was performed.

## Promotion blockers and bounded gaps

1. The actual source asks multiple land repeats but its root crop/livestock/input questions contain no land selection. Mapping cannot infer a parent for more than one land. Source amendment or supported domain intake design is needed; attaching every answer to the first land would invent relationships.
2. Full additional Farmer repeats include national IDs, local geography/language/names, phones/email, socioeconomics, membership, land/crop/livestock, input/machinery/finance and reference IDs. Both legacy COSS Jinja and current mapper reduce them to HouseholdMember summaries, not separate Farmer submissions/approvals. Raw retention is not complete functionality. A native HouseholdIngestionIntake route was identified by the lead; its exact supported multi-Farmer contracts and acceptance must be established before implementing this capability. No worker fanout or core copy is introduced.
3. The head=yes/member_registered=yes branch asks existing member reference and relationship. Current enricher resolves only head=no/head_registered=yes via a unique active registered head. The first branch and relationship persistence remain incomplete, not fixed by pure mapping.
4. Consent answer has no explicit consent-event mapping. Local member-script names and estimated age lack current mapped HouseholdMember fields. Other woreda/kebele answers lack supported entity/address handling. Legacy omission does not establish acceptable feature preservation.
5. Requiredness in the CSV is source requiredness, not proof of server validation. Source confirmation/calculation controls are not independent stored attributes. Existing native service validation must be exercised separately. Main enumerator coordinate twin fields are not populated although Farmer location coordinates are mapped.
6. Optional email mapping targets the supported person schema but section metadata/approval read-back is pending. Native metadata and approval tests must establish which non-widget fields persist; no success is inferred from the pure dictionary test.

Legacy Jinja also defaulted missing season, demographic codes and livestock count/system. Those defaults are not restored: source v3 requires an actual season and unknown/missing values remain for native validation. Legacy Jinja captured only one member certificate and did not instantiate full repeated Farmers; those historical facts are not represented as completed source capability.

All changes are OAN pure mapping; OpenG2P framework/upstream sources remain unchanged. Live ingestion, native saves, workflow approvals and full source capability acceptance remain pending.
