# Farmer intake validation

What the farmer intake form checks, where each check runs, and the exact
message a user gets. The rule this document holds the form to:

> No message without the problem and the fix. Every message says
> **which field**, as the form labels it, **what is wrong**, and **what to
> enter instead**: `<Label>: <what is wrong>. <what to do>.`

## Where checks run

| Layer | What it checks | Source | Message |
| --- | --- | --- | --- |
| Staff UI (upstream widgets) | `widget-required`, `widget-data-validation` (pattern, min/max length, min/max), date constraints, show/hide/require conditions, required table cells on row save | section metadata (`12_form_sections.sql`, `10_sections.sql`) | under the field, from the translation keys in the metadata |
| Staff UI (OAN widgets) | file type and size, photo type and size, slots per document category, map pin inside Ethiopia | `ui/staff-ui/overrides/src/oan/widgets/` | under the widget, `documents_*`, `farmer_photo_*`, `geo_point_*` |
| Server, OAN widget rules | the same metadata rules again, plus the value's **kind** (yes/no, whole number, number, date, static choice) and **required table columns** | `register_domain/services/widget_rules.py` | `rule_*` keys, REQ-VAL-001 |
| Server, farmer extension | domain rules (dates not in the future, age vs birth date, household roster, duplicates) | upstream `farmer-extension` (never changed) | reworded by `register_domain/services/upstream_messages.py`, `upstream_*` keys, REQ-VAL-001 |
| Server, OAN required fields on save (Next) | the section being saved: every `widget-required` field (and every `require` rule that matches) is filled, evaluated like the UI (hidden fields are never required, the last show/hide wins, conditions may read other registers of the submission); a list section whose table is `widget-required` holds a row; a required document is attached. Applies to every register of every intake form, for a person or an API client. Not applied to the ingestion worker (ODK, partners), which is checked whole at submit. A household section left entirely blank is not refused (the farmer may pick a registered household) | `register_domain/services/required_fields.py` (mixin first in the registered intake service), `form_integrity.py`; the section metadata is the only source | `<Section>: <Field> is required. Fill it in before pressing Next.` (`save_missing`, `save_document_missing`, `save_list_missing`) |
| Server, OAN required fields on submit (whole form) | every section's required fields over every register the form holds (farmer, membership, household information, document categories) and "at least one row" of a required list section, including sections never opened; a household's sections only once the farmer's form holds a new household (the household check says one of the two is needed). The ingestion worker does not fail: the form is left as a draft with the reason in its remarks for staff to complete | `required_fields.py`, `form_integrity.py`, `household_intake.py` (the household and Fayda ID checks join the same message) | one list, `<Section>: <Field> is required. Open <Section>, fill it in and save, then submit again.` (`form_missing`, `form_document_missing`, `form_list_missing`); the draft's remarks read `Not submitted: required information is missing. ...` (`review_reason`) |
| Server, OAN Fayda ID | the FIN/FAN is not held by another register record or by another submitted form waiting for approval (section save, change request, submit) | `register_domain/services/form_integrity.py` | `fayda_fin_registered`, `fayda_fin_pending`: names the holder and the record |
| Server, OAN person names | the farmer's and household members' names take letters (any script, Ge'ez included), spaces, apostrophes and hyphens, at most 100 characters, the rule Crop applies; from every source (web, ODK, partner). The widgets carry the same rule as one pattern | `register_domain/name_rules.py`, `derivations.py`, `odk/transform.py`; pattern in `19_name_rules.sql` | `name_letters_only`; "First Name: use letters only (spaces, apostrophes and hyphens allowed)" |
| Server, registry core | file bytes against the documents profile; MDS codes (`REGISTRY_CORE_VALIDATE_ATTRIBUTE_VALUES`) | upstream core | core's own text for files (see [Files](#files-and-documents)); OAN wording for codes (`attribute_messages.py`) |

The UI is the first line; the server repeats the value rules because an API
client, an ODK import or a stale browser tab does not run the UI. Every server
message is a translation key with an English default, so a language rewords it
in `registry_languages.domain_translation` without a code change.

A test (`tests/test_upstream_messages.py`) reads every message the farmer
extension can raise and fails if one is neither reworded nor already says what
to do. An upstream upgrade that adds a check therefore cannot ship an
unexplained message unnoticed.

## Section by section

`UI` = enforced in the browser, `API` = enforced on save by the server.
Messages are the English defaults.

### Household (lookup)

| Field | Rule | Where | Message / behaviour |
| --- | --- | --- | --- |
| Household | optional; pick a registered household **or** leave empty and fill Household Information | UI | help text: "Pick the household if it is already registered. For a new household, leave this empty and fill in Household Information and Household Members below." |
| Is Household Head | yes / no | UI, API | "Is Household Head: \"…\" is not one of the choices. Pick one from the list." |
| Is Household Head = Yes, new household on the form | the household's head is the farmer: filled in from the farmer's names when empty, refused when it names someone else | API (submit) | "Household Head: the farmer is marked as the head, and the household information names … as its head. Enter … as the household's head, or answer No to Household Head" |
| Is Household Head = Yes, registered household picked | that household already names the farmer as its head, and no other farmer of it is its head; a farmer form never changes a registered household | API (submit, change request approval) | "Household Head: the farmer is marked as the head of HH-…, whose registered head is …. A household's head changes only through a change request on that household: raise one on its Household Information making … the head, and submit this again once it is approved. Or answer No to Household Head" · "Household Head: … is already the head of HH-…. Raise a change request on …'s record answering No to Household Head, and submit this again once it is approved. Or answer No to Household Head" |

### Personal Information

| Field | Rule | Where | Message |
| --- | --- | --- | --- |
| First Name (English), Grandfather's Name (English), Gender, Marital Status, Education Level | required | UI | upstream "required" under the field |
| Birth Date | a real date, not in the future; read-only once Fayda has verified the farmer | UI (past-only picker), API | "Birth Date: the date is in the future. Enter the real birth date, today or earlier." · "Birth Date: \"1980-02-30\" is not a date. Pick the date from the calendar (DD/MM/YYYY)." |
| Birth Date (Ethiopian) | read-only, shown from the Birth Date as it is typed; stored on save | — | — |
| Estimated Age | whole number 0–122; within a year of the Birth Date; disabled once a Birth Date is entered | UI, API | "Estimated Age: \"ten\" is not a whole number. Enter digits only, for example 12." · "Estimated Age: 130 is too large. Enter 122 or less." · "Estimated Age: does not match the Birth Date. Correct the age to within a year of the birth date, or clear one of the two." |
| Farmer's Language | from the Master Data LANGUAGE list; needed when a name in the farmer's language is entered | UI, API | "Farmer's Language: the name is entered in the farmer's language, but no language is chosen. Choose the language it is written in" |
| First / Father's / Grandfather's Name (Farmer's Language) | the same three names in the farmer's own language, ≤ 100 characters; Ge'ez script for Amharic and Tigrinya, any other script as typed; filled in and locked when Fayda holds them in Amharic, unlocked again when another language is chosen | UI, API | "First Name (own language): Amharic is written in Ethiopic (Ge'ez) script, and \"Almaz\" is not. Type the name in Ge'ez letters, or choose the farmer's language again" · "…: too long. Enter at most 100 characters." |
| Has National ID, Is PSNP User, Is a Farmer | Yes or No (no "Not set") | UI, API | "Has National ID: answer Yes or No." |
| Fayda ID | 12-digit FIN or 16-digit FAN, kept as entered; not registered to another farmer | UI, API | "Fayda ID: Enter a 12-digit FIN or a 16-digit FAN, using digits only." · "Fayda ID: … is already registered to … Open that record instead of registering the farmer again; if the ID was mistyped, correct it." |
| Fayda RID | 29 digits | UI, API | "Fayda RID: The Fayda RID has 29 digits. Enter all 29, numbers only, as printed on the registration slip." |
| ODK Farmer ID, Pula ID | ≤ 64 | UI, API | "…: too long. Enter at most 64 characters." |

### Master Data values (every channel)

| Rule | Where | Message |
| --- | --- | --- |
| Gender, Farmer's language and Marital status are on their Master Data lists (`GENDER`, `LANGUAGE`, `MARITAL_STATUS`), whether or not core's own check is on. Master Data unreadable: skipped with a logged warning | API (`coded_values.py`) | "Gender: choose one of Male, Female." |
| Has national ID answered Yes has a Fayda ID in the same record | API | "Has national ID: answered Yes, but no Fayda ID is entered. Enter the Fayda ID, or answer No." |
| the kebele id the location picker saved is a Master Data location | API | "Location: the place chosen is not in the Master Data list. Choose the region, zone, woreda and kebele again." |
| Validate runs the checks Submit runs (required fields of every section, Fayda ID, household), so a draft Submit refuses is not reported valid | API (`household_intake.py`) | the same text Submit gives |
| an unknown household id | API | "Household not found. Check the household ID." |

### Photo

| Rule | Where | Message |
| --- | --- | --- |
| JPEG, PNG or WebP | UI | "Use a JPEG, PNG or WebP image." |
| resized to 1024 px on the long side, then ≤ 2048 KB | UI | "The photo is larger than 2048 KB after resizing. Choose a smaller image, or take the photo again." |
| readable image | UI | "The image could not be read. Choose another photo, or take it again." |

### Phone numbers (table)

| Rule | Where | Message |
| --- | --- | --- |
| number required on every row | API | "Phone number: a row has no number. Enter the number, or remove the row." |
| country is the 2-letter country code (`ET`) or a dialing code (`+251`, `251`); the legacy `ETH` is read as `ET`; anything else is refused | API | "Country code: Ethiopia is not a country code. Enter the 2-letter country code, for example ET, or the dialing code, for example +251." |
| a valid Ethiopian mobile number: optional `+251`, `251` or `0`, then nine digits starting with 9 or 7 (`19_phone_rules.sql`; `90_checks.sql` runs the pattern) | UI, API | "Phone Number: Enter an Ethiopian mobile number, for example 0912345678 or +251912345678" · "Phone number: 0912… is not a phone number. Enter it as 0912345678 or +251912345678." |
| no duplicates; one primary | API | "Phone number: the same number is listed twice. Keep one row for it and remove the other." · "Primary: more than one number is marked primary. Tick Primary for one number only." |

### Socio-economic and Health

| Field | Rule | Where | Message |
| --- | --- | --- | --- |
| Has Disability | required, Yes or No | UI, API | "Has Disability: \"…\" is not one of the choices. Pick one from the list." |
| Disability Type, Severity | shown and required when disabled = Yes | UI | upstream "required" |
| Other Source of Income | shown and required for "Others", ≤ 100 | UI, API | "…: too long. Enter at most 100 characters." |

### Household Information (new household)

| Field | Rule | Where | Message |
| --- | --- | --- | --- |
| Household Size | required, whole number ≥ 1 | UI, API | "Household Size: must be at least 1. Count the head and every member living in the household." |
| Male / Female Members | required, whole numbers; together ≤ size | UI, API | "Male and Female Members: together they are more than the Household Size. Correct the counts or the size." |
| Children, Elderly | 0 … size | UI, API | "Number of Children: must be from 0 up to the Household Size. Correct the count or the size." |
| Other Land Owner | required, Yes or No | UI, API | "Other Land Owner: answer Yes or No." |

### Household Members (table)

| Rule | Where | Message |
| --- | --- | --- |
| First name, last name, birth date, gender required in every row | UI, API | "First Name: this is required. Fill it in on every row before saving." |
| exactly one head | API | "Household Members: no member is marked as the head. Tick Is Head for the head of the household." · "…more than one member is marked as the head. Tick Is Head for one member only." |
| relationship for everyone but the head; Self only for the head | UI, API | "Relationship to the Head: missing for a member who is not the head. Pick it for every other member." · "Relationship to the Head: Self is only for the head. Tick Is Head for that member, or pick their relationship." |
| members match the household's male/female counts | API | "Household Members: 2 male and 1 female are entered, but the household says 1 male and 2 female. Correct the members' gender or the household's counts so they match." |

### Location

| Field | Rule | Where | Message |
| --- | --- | --- | --- |
| Map pin | inside Ethiopia; fills region → kebele, latitude, longitude, altitude | UI | "The pin is outside the country. Place it where the farmer lives." · "The location could not be filled from the map. Choose it in the location fields." |
| Location hierarchy | required | UI | upstream "required" |
| Latitude / Longitude | −90…90 / −180…180 | UI, API | "Latitude: 100 is too large. Enter 90 or less." |
| Country Code | 2 capital letters, default ET | UI, API | "Country Code: Enter the 2-letter country code, ET for Ethiopia." |
| Plus Code | Open Location Code | UI, API | "Plus Code: Enter a valid Plus Code (for example 35AB+14 or 8FVC9G8F+6W)." |

### Lands, Crops, Livestock, Farm Inputs (tables)

| Rule | Where | Message |
| --- | --- | --- |
| required columns in a new row (land ownership, size, unit; commodity; livestock type; fertilizer use) | UI, API | "Livestock Type: this is required. Fill it in on every row before saving." |
| each row belongs to one of the farmer's lands | UI (parent picker), API | "Crop rows must be attached to one of the farmer's lands (select the land in the row); not a land: …" |
| land size > 0 | UI, API | "Land Size: must be more than 0. Enter the land's area, for example 0.5, or leave it empty." |
| year of acquisition 1900…2026, not in the future | UI, API | "Year of Acquisition: 2030 is too large. Enter 2026 or less." |
| planted date not in the future | UI, API | "Planted Date: the date is in the future. Enter the day the crop was planted, today or earlier." |
| head count, amounts ≥ 0 | UI, API | "Head Count: -3 is too small. Enter 0 or more." |
| one row per crop / livestock type | API | "Crops: the same crop is listed twice. Keep one row per crop and remove the other." |
| land certificate file | UI | see [Files](#files-and-documents) |

### Membership

| Field | Rule | Where | Message |
| --- | --- | --- | --- |
| Cooperative / union / cluster member | required, Yes or No | UI, API | "…: \"…\" is not one of the choices. Pick one from the list." |
| Cooperative / union name | shown and required when a member | UI | upstream "required" |

## Files and documents

| Rule | Value | Where | Message |
| --- | --- | --- | --- |
| Categories | identity, bank, land, representative, farmer, other | metadata | — |
| Required | identity document (type + at least one file); all others optional | UI | upstream "required" |
| Files per category | up to 5 | UI | "Up to 5 files can be attached here. Remove one to add another." |
| Types | PDF, JPG, JPEG, PNG | UI | "scan.docx cannot be attached here. Choose a PDF, JPG, JPEG or PNG file." |
| Size | ≤ 5 MB per file | UI | "The file is larger than 5 MB. Choose a smaller file, or scan it again at a lower resolution." |
| Server limit | PNG/JPEG/WebP ≤ 5 MB, PDF ≤ 10 MB, content sniffed (the extension must match the bytes) | API (core) | core's text, e.g. "File content could not be identified as an allowed type." |
| Land certificate (lands table) | one file, same types and size | UI | as above |
| Farmer photo | JPEG/PNG/WebP, ≤ 2048 KB after resizing to 1024 px | UI | see Photo |

The UI is stricter than the server, so a user of the form never reaches the
server's file messages; only an API client can. Those messages are core's and
are not reworded: the upload endpoint is core's and has no OAN hook. The
values live in two places, the metadata (`doc_settings` in
`12_form_sections.sql`) and the staff API's `DOCUMENT_UPLOAD_*` settings, and
must be changed together.

## Functional analysis

**Save per section.** Each section saves on its own and is checked on its own.
The staff UI saves "Next" as a draft with its required checks off, so the
server now refuses it: the section's required fields, evaluated with the same
show/hide/require rules the UI uses, must be filled (`required_fields.py`).
The ingestion worker (ODK, partners) is the exception: it saves what its source
holds and is checked whole at submit. Table rows are whole records, so their
required columns are enforced by the server too, for new rows and for any row
that sends a required column blank.

**Household.** The farmer form carries Household Information and Household
Members. Parent links are resolved by upstream within the submission: with one
household in it, the farmer and the members are attached to it; members need a
household in the same submission.

**Submit.** Every section of the form is checked, over every register it holds
(`required_fields.py`), so a section never opened, or a register with no
record at all (a farmer with no membership), cannot reach approval. When the
ingestion worker submits a form that lacks required fields it leaves the
submission a draft and writes the reason in its remarks, instead of failing the
task and retrying the same form; staff open the draft, complete it and submit.

**Finalize (household).** Upstream's whole-household check (members must match the size,
a head is required) runs at finalize only for household-form submissions. On
the farmer form the same rules run per save in the members table, which catches
a wrong head or wrong gender counts, but **a farmer submission can be finalized
with household information and no members**, and with neither a picked nor a
new household. See open items.

**Values of the wrong kind.** Before this change a "maybe" for a yes/no field or
"ten" for an age reached the database and came back as SYS-ERR-001 with no
explanation. The server now names the field and the fix.

## Edge cases checked against the API

Replayed against a staff API built from this branch (seeded metadata, real
validation path). ✔ = accepted, ✘ = rejected with the message shown above.

| Case | Result |
| --- | --- |
| valid personal information, location, land, livestock, household, members; finalize | ✔ |
| location hierarchy sent as text | ✔ |
| latitude 100 | ✘ Latitude: too large |
| birth date in the future; age not matching birth date | ✘ explained |
| FIN "abc"; yes/no "maybe"; age "ten" | ✘ explained (was SYS-ERR-001 for the last two) |
| land size −1; head count −3 | ✘ explained |
| blank livestock row | ✘ Livestock Type: required (was accepted) |
| members not matching the counts; no head | ✘ explained |
| unknown kebele code | ✔ (open item) |
| unknown gender code | ✔ (open item) |
| household entered, no members, finalize | ✔ (open item) |

## Open items

| Item | Why it is open | Proposed fix |
| --- | --- | --- |
| Core's file messages are not reworded | core endpoint, no hook | UI is stricter, so only API clients see them |
| The map pin is bounded to Ethiopia only in the browser | the server checks latitude/longitude ranges only | an Ethiopia bounding-box rule in `widget_rules.py` |

Closed: the farmer's household at submit and "picked and new" (`household_intake.py`);
Master Data codes (core's validator with OAN wording); acquisition-year and collected-date
bounds (`16_value_bounds.sql`); required fields of unopened sections and duplicate Fayda IDs
(`form_integrity.py`). Fayda verification is optional at submit by design: every change to a
register goes through approval.

## Adding a rule

1. Write it in the section metadata (`widget-data-validation`, `widget-required`
   on a table column, a static `widget-data-source`). The UI and the server both
   pick it up; nothing else to change.
2. Give it a message key (`patternMessage`, `minMessage`, `maxMessage`) and add
   the text to `30_translations.sql` in the form "what is wrong. What to do".
   OAN's text wins over a key already in the registry, so a rewording reaches
   existing registries on the next seed.
3. A rule that needs code (several fields, other records) goes in a domain
   service; raise `validation_error("<Label>: … . …")`.
