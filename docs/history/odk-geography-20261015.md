> Historical evidence. Use [current operations](../operations/README.md) for maintenance; recorded commands and job links describe past rollouts.

# ODK geography rollout and continuation evidence

## State verified on 2026-10-15

The initial investigation used strictly checked SSH host keys and read-only
database transactions. The user then explicitly selected **Replace shared
catalog**. The shared dev migration was rehearsed and applied as described
below. No application image release, XLSForm publication, partner onboarding or
connector replay was performed.

The earlier session completed the backed-up coordinate/document-history repair.
The current live recheck confirms **36 Float-compatible coordinate columns**, zero
incompatible coordinate columns, and a non-null `character varying` `event_type`
in document history. All registry and connector deployments are ready (1/1), and
the reporting-view refresh cronjob is unsuspended. Do not rerun the migrations
just because this session resumed. Backups and migration receipts remain in the
existing ignored `local/upstream/generated/server-schema-repair-20261015/`
location; database dumps must not be committed.

These checks establish schema and workload state, not end-to-end ODK approval.
The PM issuer/partner eligibility blockers in
[the connector diagnosis](../history/gen2-connector-diagnosis.md) were not repaired or
retested by this continuation.

## One canonical COSS source, not the existing dev catalog

`local/upstream/assets/geo/ethiopia_geo_seed.sql.gz` is the canonical COSS source
used by the local trial and `odk/build_location_media.py`. It was not changed in
this continuation. The ODK workbook/CSV changes included in this PR update are
validated against it, including sibling-label
disambiguation and the exceptional Woreda P-code `0420112`.

| Level | Shared dev before migration | COSS / rebuilt ODK / dev after migration |
| --- | ---: | ---: |
| Country | 1 | Not selectable |
| Region | 15 | 14 |
| Zone | 107 | 125 |
| Woreda | 1,148 | 1,379 |
| Kebele | 0 | 19,535 |

Dev previously used level IDs `l0` through `l3` and unprefixed `ET...` place IDs.
Dev now matches COSS, which uses
`level-region` through `level-kebele` and `region-ET...`, `zone-ET...`,
`woreda-ET...`, `kebele-ET...`. Adding just a Kebele CSV or padding an ID cannot
make these catalogs interchangeable.

Before migration, the read-only reference inventory inspected all **12 base tables** exposing
`geo_lowest_level_value_id`, including register, history and intake tables.
It included hierarchy-only selections and treated conflicting column/JSON
selections as unsafe. Four tables contained selected locations:

- **855 stored references** across 131 table/location groups (not unique people).
- **346 references** across 9 groups have unchanged `ET...` P-codes with exact
  canonical targets. These are migration candidates, not migrated records.
- **509 references** across 122 groups are unmappable legacy locations. Preserve
  their records and original values; do not guess Ethiopian replacements.
- No stored reference already uses an exact canonical COSS place ID.

This initial inventory covered Farmer only. The subsequent all-namespace
deployment/configuration inventory confirmed Crop and Livestock also use shared
Master Data. Crop's nine geography tables were empty; Livestock had 14 rows
across six geography tables and **zero selected geography references**. Their
full-record fingerprints were verified unchanged during the migration.

## Applied shared-catalog migration

`scripts/migrate-shared-odk-geography.py` defaults to dry-run. It parses the
checked-in catalog without executing its SQL and preserves all supplied metadata
columns supported by the target schema. Duplicate sibling labels use the same
P-code disambiguation as ODK. Parent-chain disagreement excludes an alias and
its descendants; an equal P-code is not sufficient to guess a moved place.
The restored catalog contained three such unused parent mismatches; none of the
346 selected migration candidates depended on them.

The rehearsal used newly restored, isolated `odk_geo_md_20261015_test` and
`odk_geo_registry_20261015_test` databases, not the original trial databases.
Dry-run, apply and completed-rerun checks passed. Legacy three-field hierarchy
JSON was upgraded to the RC format; extra JSON keys were retained. Fictional
district/ward/village hierarchies were left untouched rather than remapped.

For the live operation:

1. Saved the original replica/cronjob state, paused 20 affected deployments in
   `commons`, `farmer`, `crop` and `livestock`, and suspended the reporting cronjob.
2. Took fresh custom-format backups of Master Data and all three registries;
   validated their archive TOCs and retained SHA-256 hashes.
3. Captured preservation fingerprints and repeated preflight with writers stopped.
4. Installed four levels / **21,053 places** and migrated **346 references**.
   Preserved **509 legacy land records**, one empty selection and all other data.
   The old Master Data catalog is archived in `coss_geo_catalog_archive`; that
   archive is recovery/reference data, not an automatic runtime legacy resolver.
5. Verified all 27 domain-table counts/fingerprints. Full records matched for
   Crop, Livestock and legacy lands; other Farmer tables matched excluding only
   the two deliberately migrated geography fields. A completed rerun verified
   exact canonical contents and no pending mapped-reference updates.
6. Restored Master Data and registry APIs first. Authenticated service-account
   reads verified every level/parent and **22 Kebeles** under a sampled Woreda,
   including the expected ODK target. Unauthenticated requests still return 401.
7. Restored all 20 original deployment replica counts/readiness, asynchronous
   processors and the reporting cronjob. No auth bypass, blanket seed rerun or
   legacy geo-widget synchronizer was applied.

The live backup, durable recovery journal, executed source and preservation/
workload receipts are retained on the PostgreSQL PVC under
`/bitnami/postgresql/coss-backups/odk-geo-live-20261015/`. A second private copy is
in ignored `local/upstream/generated/shared-geo-live-20261015/`. Never commit
these dumps, raw journals or private runtime artifacts.

Commits to the two databases are **not atomic**. The journal is persisted with
mode 600 before either commit and marked complete only after both succeed.
Recovery requires keeping writers stopped and reconciling both databases with
the retained journal/backups; tuple keys cannot be reused after writers resume.
No cross-database automatic rollback is claimed.

The strict reference audit intentionally remains non-green for the 509 retained
unmappable records. Catalog compatibility is established; complete reference
remediation is not. Historical locations remain available in their unchanged
stored JSON, but browser display/edit of those legacy selections is not verified.

## Connector ownership

Read-only Kubernetes metadata confirms all four deployments belong to the Helm
release **`farmer-connector`**, namespace **`farmer`**:

- `farmer-connector-api`
- `farmer-connector-worker`
- `farmer-connector-beat`
- `farmer-connector-ui`

There is no connector deployment in the inspected `commons` namespace. Commons
Base 2.3.3 / Services 2.3.4-rc.245 do not supply this live connector. Removing
vendored applications from the registry source does not migrate this release
into Commons. Preserve its release, database, keys, pipeline and deployment
source; a future combined-release upgrade still needs an ownership review.

## Repeatable offline compatibility gate

`scripts/check-odk-geo-compatibility.py` is a pure-stdlib, read-only snapshot
audit. It does not connect to a database, execute SQL, write files or migrate
anything. Obtain snapshots using explicitly read-only transactions and keep
them in the existing ignored generated directory, not tracked documentation.

Catalog snapshot shape:

```json
{
  "levels": [
    {"level_id": "level-region", "level_mnemonic": "region", "parent_level_id": null}
  ],
  "values": [
    {"level_value_id": "region-ET01", "level_id": "level-region",
     "parent_level_value_id": null, "level_value_mnemonic": "Tigray"}
  ]
}
```

The example shows the format, not a complete compatible catalog. Include all
levels/values, with their original text IDs. Reference snapshots are an array
of aggregate rows only:

```json
[
  {"table": "g2p_register_farmers", "geo_lowest_level_value_id": "ET010103", "count": 2}
]
```

Inspect every relevant base table, not only Farmer's current register. For each,
group by the effective lowest-level ID, falling back to the JSON
`lowest_level_value_id` when the dedicated column is null. Flag conflicting
column/JSON IDs or a nonempty hierarchy without an ID as unmappable, rather than
omitting them. Exclude empty `{}` and JSON `null` when neither field contains a
selection; those are not unmappable locations. An explicit `[]` asserts that a
complete inventory found no references; omission reports coverage as unknown.
The tool cannot certify the
completeness of a supplied snapshot or verify the full stored hierarchy JSON.

```sh
python scripts/check-odk-geo-compatibility.py \
  --catalog local/upstream/generated/catalog.json \
  --references local/upstream/generated/references.json
```

Exit codes: **0** exact catalog and known/already-exact references; **1**
incompatible catalog, unknown coverage, migration candidates or unmappable
references; **2** invalid input. Reports contain counts, never raw record IDs,
reference rows or PII. Legacy candidates preserve the full unchanged `ET...`
code; no truncation, padding or name-based matching is performed.

## Reusing the explicit migration tool

The shared-catalog scope decision is complete for this dev operation, not a
standing approval for other environments. Future runs require the same consumer
inventory, backup, writer-quiescence and restored-database rehearsal. The tool
supports one Master Data / one Registry database pair; additional consumers must
be independently inventoried. This dev run verified no selected references in
Crop/Livestock before proceeding. If they gain selections, do not assume the same
procedure can leave them untouched.

Requirements: Python 3.10+, `psycopg2`, `PGHOST`/`PGPORT`/`PGUSER`/`PGPASSWORD` in
the runtime environment; POSIX journal permissions for apply. Never print or
commit those credentials. Run in the repository layout so the canonical source
and parser resolve correctly. Use an existing reviewed backup directory.

```sh
# Default: validate, stage in temporary tables, then roll back both databases.
# Still takes exclusive table locks: use only restored DBs or stopped writers.
python -B scripts/migrate-shared-odk-geography.py \
  --master-data-db master_data --registry-db farmer_registry \
  --journal-dir /backups/reviewed-new-migration

# Only after independent fresh-backup and stopped-writer verification:
python -B scripts/migrate-shared-odk-geography.py \
  --master-data-db master_data --registry-db farmer_registry \
  --journal-dir /backups/reviewed-new-migration --apply --writers-stopped
```

Apply requires nonempty `master-data.dump` and `registry.dump` in that directory.
The script checks their paths/type/size, **not freshness, provenance or restore
quality**; the operator must validate those separately. A pending recovery
journal blocks reruns. An unchanged completed rerun verifies the checksum,
catalog and mapped references before returning without writes.

Do not run the trial-only `geo_override.py` against the server or weaken its
database guard. Do not apply the inherited `sync_geo_widgets.py` blindly: it
assumes the root is Country and would skip Region in this catalog. The inspected
Farmer/Crop register metadata uses dynamic `geo-hierarchy` widgets; no metadata
rewrite was needed for those widgets. Intake/UI coverage must still be checked
before claiming browser acceptance across all products.

## Remaining rollout work

1. Publish the rebuilt workbook and both media files together as a new version
   of the same `farmer_profile` form. The current workbook remains version
   `1.0.4`; it has **not** been republished. Validate XLSForm conversion and ODK
   Central draft publication before replacing the live form. Upload the matching
   transform through the owning connector deployment/template process.
2. Resolve and verify PM issuer/onboarding prerequisites. Check for an already
   accepted source event before replaying one matching DLQ entry. Verify actual
   intake ingestion, attachments, Kebele readback, AWE approval and promotion.
3. Agree a separately reviewed remediation/display approach for the 509 legacy
   land selections. They are preserved, not converted into valid COSS places.
4. Align the owning Commons seed/deployment configuration with this catalog so
   a later blanket country-pack seed cannot silently restore the old hierarchy.
   No Commons Helm upgrade or long-term bootstrap configuration change was made
   here; the version/checksum ledger only guards this explicit migration tool.

## Checks run in this continuation

- Final focused combined pytest run: **151 passed, 2 skipped, 57 subtests
  passed**, covering ODK media, compatibility audit, migration, RC pins, PM
  manifest and effective metadata. The two skipped POSIX-only journal tests on
  Windows were included in a separate Linux run: **70 migration tests passed**.
- `tests/unit/test_odk_transform.py`: passed with UTF-8 stdout. The first Windows run
  rendered valid JSON but failed when cp1252 stdout printed Amharic; rerunning
  with process-local `PYTHONIOENCODING=utf-8` passed.
- `odk/build_location_media.py --check`: passed without changing the workbook.
- `local/upstream/stack.py validate` and `git diff --check`: passed. The private
  second-copy dump and journal paths were confirmed Git-ignored.
- Live read-only schema, workload readiness, connector ownership and catalog/
  reference inventory: completed as recorded above.
- Isolated restored-database migration dry-run/apply/idempotence; live apply and
  completed-state verification; authenticated Master Data API readback; all 27
  domain-table preservation comparisons; all four second-copy backup hashes;
  mode-600 completed journal and restored workloads: passed. The temporary
  maintenance pod was removed; the backup PVC and private copies remain.
- The live **local trial catalog** matches every canonical level, ID, parent and
  label. The full local reference gate is **not green**: after excluding empty
  hierarchies, 27 references are exact and one intake reference is a legacy
  P-code candidate. It was not rewritten or deleted. An initial inventory
  incorrectly counted 20 empty hierarchy objects as unmappable; that inventory
  predicate was corrected before recording this result. This does not invalidate
  the earlier scoped browser acceptance, but it prevents claiming full trial
  reference compatibility.

No full image build, browser acceptance, XLSForm conversion, ODK publication or
live ODK-to-AWE end-to-end test was performed in this continuation.
