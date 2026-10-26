# OAN extension

The OpenAgriNet layer on the OpenG2P Farmer Registry. It changes nothing
upstream: the package re-exports the farmer extension and adds its own
registers, services and metadata in new files. It is selected at runtime with
`REGISTRY_EXTENSION_MODULE=openg2p_registry_oan_extension`, as the registry
platform's Extensions Contract describes for coexisting extensions.

| Path | Holds |
|---|---|
| `register_domain/fields.py` | the OAN columns on the farmer registers, declared once |
| `register_domain/models/`, `schemas/` | append those columns to the farmer models and schemas; OAN's own register, FarmerPhone (`registers.py`) |
| `register_domain/derived.py` | the values derived rather than typed (land totals in hectares, location names, Ethiopian calendar dates, phone numbers, the farmer's search text), with no framework imports |
| `register_domain/ethiopian_calendar.py` | Gregorian and Ethiopian calendar conversion |
| `register_domain/services/` | the farmer domain services, each extended with the derived values (`derivations.py`) and the section widgets' value rules (`widget_rules.py`); the FarmerPhone service |
| `app.py` | the farmer initializer, plus migration of OAN registers |
| `meta_data/` | the `oan_` metadata layer, applied after the farmer's (`/seed/meta_data/zz-oan/`) |
| `seed/` | the db-seed entrypoint: sample people come from Master Data (the country pack's `samples/`) instead of the Kamuntu demo files; `OAN_SAMPLES_FROM_MASTER_DATA=false` keeps the farmer seed's own |
| `tests/` | `uv run --no-project --with pytest pytest oan-extension/tests` |

Images are built FROM the published farmer images (`docker/oan/`). The staff
UI image is upstream's staff UI build, from the commit of the published image,
with `ui/staff-ui/overrides/` copied on top (`docker/oan/staff-ui.Dockerfile`).

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
  `pula_id` in personal identification. FIN is collected only by the verification
  popup; its main-form value is read-only. Offline ODK identity evidence follows
  the separate unverified intake approval path. A household member's ODK
  Member ID is `odk_member_id`.
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
| Seed | `LOAD_TEMPLATES=true` uploads both templates; the Farmer register's `outgest_applicable` is on |

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
| `oan-identity-verification` | verifies the farmer with Fayda (eSignet) during intake and fills in what Fayda verified; see [Fayda verification](#fayda-verification-during-intake) |

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

### Fayda verification during intake

Current FIN-once behavior and native completion bridge: [fin-once.md](docs/fin-once.md).

The FIN is entered only on eSignet; **Verify with Fayda** opens the
Fayda (eSignet) sign-in in a pop-up. When the farmer has signed in, the names,
gender and birth date Fayda holds are filled in on the form and can no longer be
changed. Test identities are picked in the pop-up (eSignet with the mock
identity system), never on the form.

It is core's registrant authentication, unchanged: the provider row, the
`/registrant-auth/callback` that completes the sign-in, the check that the
person who signed in has the FIN on the form (the eSignet `individual_id`), and
the `g2p_registrant_authentications` row with the encrypted claims. OAN adds
(`register_domain/services/identity_verification.py`):

* starting it before the farmer has a record, with the FIN from the form
  (`POST /oan/identity-verification/start`, staff from the session, permission
  `register:authenticate`), and reading the outcome with the verified values
  (`/oan/identity-verification/result`, only by the staff member who started it);
* on every save of the farmer: the verification must have succeeded and not
  expired, belong to this record (the first save ties it to the record) and to
  the FIN on the form; a verified value cannot be changed; and the outcome
  (`last_authentication_status`, `last_authenticated_on`,
  `authentication_expiry_date`) is set from the verification, never from the form.

Every refusal says what to do, for example *"The person who signed in with
Fayda is not the FIN on this form. Check the FIN, or ask the farmer to sign in
with their own Fayda ID, then verify again"*.

**Deployment.** The Farmer register has `requires_registrant_authentication`
(`05_registers.sql`). Each environment adds its eSignet client as a row in
`g2p_registrant_authentication_providers` for the Farmer register (adapter
`esignet`, `oauth_callback_url` = the staff API's `/registrant-auth/callback`,
client id and private key, and `provider_config` with `scope`, `issuer`,
`audiences`); these are environment secrets, not seed data. With
`private_key_jwt` the key in `client_private_key` must be the PEM text
(`-----BEGIN PRIVATE KEY-----`, stored as its bytes), not DER: core decodes it as
text, and a DER key fails every sign-in after Fayda returns. The eSignet client
must have that callback among its redirect URIs. `provider_config` must ask for
the claims, or eSignet returns only its pairwise `sub` and every verification
fails as "not the FIN on this form":

```json
{"extra_authorize_params": {"claims_locales": "en am", "claims": {"id_token": {},
  "userinfo": {"individual_id": {"essential": true}, "name": {"essential": true},
               "gender": {"essential": false}, "birthdate": {"essential": false}}}}}
```


For a local HTTP gateway in front of an HTTPS canonical eSignet issuer, set
`provider_config.jwt_assertion_aud` to the exact canonical token endpoint from
discovery. The OAN registered service maps this native IAM audience setting
separately from the provider's transport `token_endpoint`. Do not change keys,
disable signature verification, or alter ID-token audiences to fix this mismatch.
Six regressions cover the override, native default and invalid configuration.

The adapter must be `esignet`, not `default_oidc`: only the eSignet adapter
reads userinfo and compares `individual_id` with the FIN. Core keeps the
sign-in transactions in Redis by default and its URL defaults to
`redis://localhost`, so the staff API needs
`REGISTRY_CORE_REGISTRANT_AUTH_REDIS_URL` (any Redis the workers share).

`provider_config.claim_mapping` says which claim fills which field; without it
the default in `register_domain/identity_claims.py` applies (full name in
English and Amharic split into the three names, gender, birth date):

```json
{"first_name": {"claim": ["name#en", "name"], "part": 0},
 "gender": {"claim": "gender", "values": {"male": "MALE", "female": "FEMALE"}},
 "birth_date": {"claim": "birthdate", "format": "date"}}
```

The pinned platform (`1.2.2-rc.557`) calls `get_async_session_maker` in the
registrant authentication service without importing it; the OAN service gives
the module that name until a platform image does (a no-op then). Upstream's
`IdAuthenticationWidget` opens its pop-up with `noopener`, so `window.open`
returns `null` and it reports a blocked pop-up while the sign-in is open; OAN's
widget opens the window without it and cuts the opener by hand.

## Metadata layer

Each file runs after the whole farmer seed, in name order:

| File | Does |
|---|---|
| `05_registers.sql` | the FarmerPhone register, the location names in the farmer list, and Fayda verification for the Farmer register |
| `10_sections.sql` | the table sections: each upstream one with OAN columns added, so upstream changes carry over on the next seed; the household link and the intake photo section |
| `12_form_sections.sql` | the form sections as one row of three columns: which widget goes where, upstream's by `widget-id` and OAN's written out (personal identification, socio-economic, membership, household, location, documents) |
| `15_sections.sql` | sections with no upstream counterpart: phones, land totals, enumerator |
| `20_layout.sql` | attaches the OAN sections where the upstream ones were, then detaches those by explicit id |
| `30_translations.sql` | adds labels to each language's domain translations; upstream wording wins on a shared key |
| `40_deduplication.sql` | the farmer duplicate check, with the father's name (middle name) added |
| `90_checks.sql` | raises an error in the seed log if anything above did not apply |

Upstream section rows are never changed. Code lists (body condition,
production type, commodities, languages) come from the country pack in Master Data;
short fixed lists (phone type) are static options in the section.

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
