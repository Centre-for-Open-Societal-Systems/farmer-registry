# Farmer extension

`openg2p_registry_farmer_extension`, laid out as OpenG2P's registry extension
documentation describes: the registry images are the platform images with this
package installed, selected with
`REGISTRY_EXTENSION_MODULE=openg2p_registry_farmer_extension`.

OpenG2P's Farmer extension (1.0.3, the code of the published Farmer images) is
kept unchanged in `openg2p_farmer/`; `../sample-farmer-extension/` holds it as
published, to diff against on an upgrade. The OpenAgriNet layer is the package
top level: each module re-exports `openg2p_farmer` and redefines the classes it
extends under the same names, because the platform resolves domain classes by
name on these modules. `__init__.py` makes the platform's
`openg2p_registry_extensions.*` names resolve to the modules already loaded here.

| Path | Holds |
|---|---|
| `register_domain/fields.py` | the OAN columns on the farmer registers, declared once |
| `register_domain/models/`, `schemas/` | append those columns to the farmer models and schemas; the FarmerPhone register (`farmer_phone.py`) |
| `register_domain/derived.py` | the values derived rather than typed (land totals in hectares, location names, Ethiopian calendar dates, phone numbers, the farmer's search text), with no framework imports |
| `register_domain/ethiopian_calendar.py` | Gregorian and Ethiopian calendar conversion |
| `register_domain/services/` | the farmer domain services, each extended with the derived values (`derivations.py`) and the section widgets' value rules (`widget_rules.py`); the FarmerPhone service |
| `app.py` | the farmer initializer, plus migration of OAN registers |
| `openg2p_farmer/` | OpenG2P's Farmer extension code, unchanged |
| `meta_data/`, `awe_meta_data/`, `templates/` | OpenG2P's Farmer seed content, with the OAN layer in `zz-oan/` (applied after the Farmer tree) and OAN's templates; `templates/blocks/` holds the block built into the DCI response |
| `tests/` | `uv run --no-project --with pytest pytest farmer-extension/tests` |

Images are built FROM the registry platform images (`docker/<component>/Dockerfile`).
The staff UI image is upstream's staff UI build, from the commit of the published image,
with `ui/staff-ui/overrides/` copied on top (`docker/staff-ui/Dockerfile`).

## Staff UI widgets

`ui/staff-ui/overrides/src/oan/widgets/` holds OAN's widgets, registered from
the one overridden upstream file, `src/shared/widgets/RegistryWidgetProvider.tsx`
(a single added import).

The farmer photo (`FarmerPhotoWidget.tsx`) has one picker (a phone offers its
camera or its gallery for an image input), previews the photo, and scales it
down before upload. The widget
package uploads a section's photo into `record_image_document_id` only for
widgets of type `header-section`, so the photo section declares that type with
`"widget-variant": "oan-farmer-photo"`, and the OAN registration renders the
OAN widget for that variant and upstream's header for everything else.

## Farmer attributes

Following OpenG2P's review of the previous registry:

- Identifiers are attributes of the farmer, not a table or a section: the Fayda
  FIN is upstream's `foundational_id`, beside `rid`, `odk_farmer_id` and
  `pula_id` in personal identification; it is typed on the intake form and
  verified on the record with the platform's `id-authentication` widget (see
  [Fayda verification](#fayda-verification-of-the-record)). Offline ODK identity
  evidence follows the separate unverified intake approval path. A household
  member's ODK Member ID is `odk_member_id`.
- Location stays on the farmer tab.
- The farmer's `search_text` holds only what a user types to find a farmer: its
  ids and its names in each language (`derived.FARMER_SEARCH_FIELDS`).
- Dates are entered and stored in the Gregorian calendar with the registry's
  own date widget, as OpenG2P does (its ODK forms show Ethiopian dates and
  still record the Gregorian one). Each register lists the dates that keep an
  Ethiopian calendar twin (`ethiopic_dates` in `services/derivations.py`), and
  the domain service derives the twin on every way in: birth dates, planting
  dates and livestock count dates.
- The household link and household-head field use the native intake context and
  registered OAN service. Additional household Farmer repeat registration is a
  known acceptance gap; see [the candidate status](../docs/refactor-candidate.md).

Derived and never typed: the land totals and land ownership, a land's area in
hectares and whether its certificate is on file, the region to kebele names,
the `*_ec` dates, the farmer's phone list (from the phone rows), and the
enumerator details. A household's head is never derived from a farmer: it
changes only through a change request on the household. The enumerator name and date come from
the submission. The position comes from the enumerator's device, if the browser
allows it. They are shown on the read-only Enumerator tab.

## Farmer data for Crop and Livestock

Crop and Livestock keep a reference to each farmer they use. The Farmer
registry is the source (`meta_data/50_outgestion.sql`, templates in
`templates/`):

| What | How |
|---|---|
| Lookup | the signed, consent-checked DCI search on the partner API. Its response is the farmer extension's own template plus a `farmer_reference` block (record id, farmer id, FIN or FAN, approval time, status, names, Amharic names, phone, location). `build_dci_template.py` builds it at image build, so the block follows upstream's template. A Consent Manager policy with scope `farmer_reference` releases that block only |
| Change notice | outgestion publishes `farmer_reference.changed.v1` (event id, farmer id, FIN or FAN; no personal details) to the WebSub topic `oan.farmer-reference.changed.v1` on every approved farmer change; receivers fetch the details through the lookup |
| Seed | `LOAD_TEMPLATES=true` uploads both templates (`farmer_dci_search_response.j2`, `farmer_reference_changed_v1.j2`); the Farmer register's `outgest_applicable` is on |

Per deployment, outside this repository:
- the partner API's response signing key;
- Partner Management partners with their public keys;
- the Consent Manager partner policies (purpose `farmer-reference`, scope `farmer_reference`);
- the Celery outgestion worker and beat with the WebSub base URL.

## Staff UI widget types

Besides the farmer photo, `ui/staff-ui/overrides/src/oan/widgets/` registers:

| Widget | Does |
|---|---|
| `oan-file-cell` | a file in a table cell, such as a land certificate: the table hides labels in its cells, and upstream's file widget is one |
| `oan-geo-point` | an OpenStreetMap map to pin a place, as ODK's map question does; saves latitude, longitude and altitude (device altitude, or the ground elevation at the pin from `elevationUrl`), and fills the location hierarchy from the pin |
| `oan-enumerator-position` | renders nothing; records the device's position once, if allowed |
| `file` with `"widget-variant": "oan-documents"` | a documents category with several files: the first of the category's file widgets lists them all; the others (`oan-document-slot`) render nothing |

The map needs its tile and elevation hosts in the staff UI's CSP (`CSP_SRC_IMG`,
`CSP_SRC_CONNECT`). The elevation lookup sends the pin's coordinates to that
service; leave `elevationUrl` out of the section to keep them in.

### Location from the map

The farmer location map is kept to Ethiopia, and the pin fills Region, Zone and
Woreda; the address lines are typed. The polygons are Master Data's, which seeds
them with the hierarchy from the country pack (ETH-OAN `boundaries/`, OCHA
COD-AB, in the openg2p-data fork), so every OAN registry and dashboard has one
map with the same ids as its location fields. The staff UI reads them through
`/api/master-data/geo-boundary?level=woreda` (an override route for Master
Data's `/catalogue/get_geo_boundary`). The woreda under the pin gives a P-code;
its region and zone are read from Master Data, never from the polygon, so a
woreda moved to a new zone gets the new one. The geo hierarchy widget then
shows the chain and asks for the kebele, which has no polygons. A woreda without
a polygon (new since 2021) is chosen from the lists.

Master Data serves boundaries from its catalogue, which published images have
from `0.0.0-develop.118`; on an older Master Data the route answers 404, the pin
still saves its coordinates, and the location is chosen from the lists.

### Documents

Six categories, each with the kind of document and up to five files; only the
identity document is required (`12_form_sections.sql`). The staff UI stores one
file per file widget label, so a category is five upstream file widgets
(`<category>_1` .. `_5`) shown as one list. A new file goes to the first free
slot; a saved document keeps its slot, since it is stored under that label.

### Fayda verification of the record

The farmer's Fayda ID (FIN, 12 digits, or FAN, 16 digits) is typed on the
intake form (`foundational_id`, shown when the farmer has a national ID);
approval is the control, as for every other value. The record is then verified
with the platform's own `id-authentication` widget, in the *Fayda verification*
section of the farmer tab (`18_identity_verification.sql`): it starts core's
registrant authentication for the record (`authenticate_registrant`, provider
`esignet`), opens the eSignet sign-in, and core completes it on
`/registrant-auth/callback`: it checks that the person who signed in has the
record's FIN (the eSignet `individual_id`), keeps the `g2p_registrant_authentications`
row, and writes the outcome on the record. Core writes that outcome only for a
register whose model carries its `G2PRegisterAuthentication` mixin, so OAN's
Farmer model does (`register_domain/models`): `last_authentication_status`,
`last_authenticated_at`, `authentication_expiry_at`, which the widget shows and
the name, gender, birth date and FIN widgets lock on `SUCCESS`
(`12_form_sections.sql`). Nothing of this is OAN code: the widget, the
endpoints and the checks are the platform's.

**Deployment.** The Farmer register has `requires_registrant_authentication`
(`05_registers.sql`). The eSignet provider row (adapter `esignet`,
`oauth_callback_url` = the staff API's `/registrant-auth/callback`, client id,
PEM private key, `provider_config` with issuer, audiences and the claims) and
the matching eSignet client are deployment data, provisioned by the chart's
`registrantAuth` hook (oan-helm, `docs/registry-esignet-onboarding.md`), never
seed data. With `private_key_jwt` the key must be the PEM text, not DER. The
adapter must be `esignet`, not `default_oidc`: only the eSignet adapter reads
userinfo and compares `individual_id` with the FIN. Core keeps the sign-in
transactions in Redis, so the staff API needs
`REGISTRY_CORE_REGISTRANT_AUTH_REDIS_URL`.

The pinned platform (`1.2.2-rc.557`) calls `get_async_session_maker` in the
registrant authentication service without importing it;
`register_domain/services/registrant_auth_compat.py` gives the module that name
until a platform image does (a no-op then).

## Metadata layer

Each file runs after the whole farmer seed, in name order:

| File | Does |
|---|---|
| `05_registers.sql` | the FarmerPhone register, the location names in the farmer list, and Fayda verification for the Farmer register |
| `10_sections.sql` | the table sections: each upstream one with OAN columns added, so upstream changes carry over on the next seed; the household link and the intake photo section |
| `12_form_sections.sql` | the form sections as one row of three columns: which widget goes where, upstream's by `widget-id` and OAN's written out (identity, name, personal details, socio-economic and health, membership, household, location, documents) |
| `15_sections.sql` | sections with no upstream counterpart: phones, land totals, enumerator |
| `16_value_bounds.sql`, `17_multi_choice.sql` | value bounds and multi-answer questions on the OAN widgets |
| `18_identity_verification.sql` | the Fayda verification section of the farmer's record |
| `20_layout.sql` | attaches the OAN sections where the upstream ones were, then detaches those by explicit id |
| `22_retired_rows.sql` | deletes, by explicit id, rows that earlier seeds wrote and no current seed writes |
| `30_translations.sql` | adds labels to each language's domain translations; OAN's text wins on a shared key |
| `40_deduplication.sql` | the farmer duplicate check, with the father's name (middle name) added |
| `50_outgestion.sql` | the Farmer DCI search response and the farmer reference change notice (see above) |
| `55_default_approvals.sql` | the default approval policies of the farmer and household forms and change requests |
| `60_odk_ingestion.sql` | ODK connector submissions as Farmer intakes |
| `90_checks.sql` | raises an error in the seed log if anything above did not apply, or if a row still carries a retired id |

OAN's ids name what a row holds or does, without an `oan_` prefix:

| Row | Id |
|---|---|
| section | the farmer's data it holds, which is also its mnemonic and its UI `section-id`: `farmer_identity`, `farmer_name`, `farmer_personal_details`, `farmer_identity_verification`, `farmer_socio_economic_health`, `farmer_location`, `farmer_photo`, `farmer_phones`, `farmer_documents`, `farmer_household_lookup`, `household_information`, `farmer_membership`, `farmer_lands`, `farmer_land_summary`, `farmer_crops`, `farmer_livestock`, `farmer_farm_inputs` (and `*_intake` for the intake form's table sections), `farmer_enumerator` |
| tab | `farmer_tab_enumerator` |
| attachment | `<tab_id>__<section_id>` on a register tab, `farmer_intake__<section_id>` and `household_intake__<section_id>` on the intake forms |
| ODK ingestion | data model `odk_to_farmer_intake` (mnemonic `ODK_TO_FARMER_INTAKE`, which the connector sends), key path `odk_to_farmer_intake_key_path`, pattern `odk_to_farmer_intake_pattern` with the enricher `OdkToFarmerIntakeEnricher`, template `odk_to_farmer_intake_template` and its document `odk_to_farmer_intake_document` (`templates/odk_to_farmer_intake.j2`) |
| outgestion | `farmer_dci_search_response_document` (`farmer_dci_search_response.j2`, built from `templates/farmer_reference_block.j2`; upstream's `OUT-TMPL-1` points at it), `farmer_reference_changed_v1_template`, `farmer_reference_changed_v1_document` (`templates/farmer_reference_changed_v1.j2`), `farmer_reference_changed_v1_topic`; the data model `FARMER_REFERENCE_CHANGED_V1`, the event type and the topic name are what the subscribers use |

The staff UI's own labels are `farmer_photo_*`, `geo_point_*` and `documents_*`;
the server's messages are `rule_*`, `upstream_*`, `form_*`, `fayda_fin_*` and
`household_*`.

Upstream section rows are never changed. Every choice list (body condition,
production type, commodities, languages, the kinds of document, phone number
type, finance access) comes from the country pack in Master Data
(`widget-data-source` of type `api`, service `attributes`); the only static
options are yes/no. `90_checks.sql` and `ci/validation/check_native_metadata.py`
fail if a list is written in the registry.

## Migration from the previous registries

Every field of the previous registries (Gen1 `g2p_ati`, and the COSS farmer
registry) has a Gen2 column, so a migration keeps everything. Most keep their
name; these map:

| Previous field | Gen2 |
|---|---|
| `given_name`, `family_name`, `gf_name_eng` | `first_name`, `middle_name`, `last_name` |
| Gen1 `first_name_amh`, `family_name_amh`, `gf_name_amh` | `first_name_local`, `middle_name_local`, `last_name_local`, with `language_spoken` = `AMHARIC` |
| COSS `*_om` (Afaan Oromo) | `*_local`, with `language_spoken` = `AFAAN_OROMO` |
| `birthdate_ec`, `collected_ec`, `expiry_date_ec` | derived again from the Gregorian date (`*_ec`) |
| `age` | `estimated_age` |
| `is_disabled` | `disabled` |
| `martial_status`, `education` | `marital_status`, `education_level` |
| `hh_is_household_head`, `hh_income_type` | `is_household_head`, `source_of_income` |
| `size_of_family`, `number_of_children_in_family`, `number_of_males_in_family`, `number_of_females_in_family`, `other_family_member_own_land`, `other_farmer_in_hh` | household `size_of_group`, `number_of_children`, `number_of_male_members`, `number_of_female_members`, `other_land_owner`, `other_farmer_in_household` |
| `do_you_use_*`, `amount_*_utilized`, `crop_water_sources`, `livestock_water_sources`, `access_to_machinery`, `type_of_machinery`, `irrigation_types`, `has_finance_access`, `finance_accesses` | farm inputs `*_use`, `amount_*_utilized`, `water_source`, `livestock_water_source`, `access_to_machinery`, `machinery_type`, `irrigation_type`, `access_to_finance`, `finance_access_type` |
| cooperative and cluster fields | membership details |
| land `total_land_area`, `land_certificate`, `certficate_provided`, `ownership_type` | land `land_size` (unit `HECTARE`), `certificate_storage_id`, `certificate_provided`, `land_ownership_type` |
| crop `crop`, `collected_gc`, `illness_type` | crop `commodity`, `planted_date`, `disease_type` |
| livestock `number_of_livestock`, `collected_gc`, `illness_type` | livestock `head_count`, `collected_date`, `disease_type` |
| reg ids (Fayda FIN, RID, ODK farmer and member ack ids) | `foundational_id`, `rid`, `odk_farmer_id`, `odk_member_id` |
| `farmer_id`, `rejection_reason`, `state`, `rec_import_source`, `odk_instance_id` | `functional_record_id`, `record_status_reason`, `legacy_state`, `import_source`, `odk_instance_id` |
| COSS `father_*_name`, `is_duplicated`, member `certificate_*`, `woreda_level_value_id` | the same names; `woreda_level_value_id` is in `geo_code_hierarchy_json` |

A previous id's expiry date and status have no column: the identifiers are
attributes of the farmer, as OpenG2P advised, not rows of an id table.

## Validation on the server

Core applies coded-value checks itself (`REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES`).
The widgets' `widget-data-validation` rules (pattern, length, range) are applied
by every register's domain service after the farmer checks, read from the same
section metadata (cached for five minutes), so a rule is written once.
Whether a field is required stays with the UI and with the domain code.

When a farmer's intake form is finalized, its household is checked as a whole
(`services/household_intake.py`), since a section save sees one section only:
the farmer either joins a household picked in the household lookup or brings a
new one entered on the same form, never both and never neither, and a new
household's members must pass the farmer extension's own roster rules (members
entered, one head, relationship for the others, counts matching the household).
It runs ahead of the farmer extension's finalize, which checks a household's
own intake form the same way.

A farmer answering Yes to Household Head never changes a household. A new
household on the form takes the farmer as its head (filled in before approval,
so the approver sees it); a registered household must already name the farmer
as its head, with no other farmer of it marked head, both at submit and when a
farmer change request is approved. The message names the change request to
raise first.
