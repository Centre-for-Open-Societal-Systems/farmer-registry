# Staging shared-geography repair proposal

The user approved this repair after review, and it was **applied and verified**
on 16 October 2026. The user had first requested a separately reviewed proposal.
Farmer's published ODK version 1.0.5 already uses canonical seed choices; the
Registry/connector cutover remains gated on legacy Farmer geography references,
partner readiness and the remaining enabled-hook acceptance checks.

## Proposed change and scope

The protected review package updates 2,489 existing `master_data` catalog rows:
289 parent links and 2,201 labels. It adds or removes no IDs, changes no other
catalog fields, and updates no Farmer, Crop or Livestock records.

Staging also has `ux_geo_level_values_mnemonic`, a global unique index on place
names. The restored-dump rehearsal showed canonical names violate that index.
The SQL explicitly checks its installed definition before replacing it with
`ux_geo_level_values_sibling_mnemonic`, unique on
`(level_id, parent_level_value_id, level_value_mnemonic) NULLS NOT DISTINCT`.
The existing ID, parent-lookup and name-lookup indexes remain. This schema change
must be reviewed with the owning Master Data deployment so a future migration
or bootstrap does not recreate global uniqueness or reload the old catalog.
The deployed `openg2p_gen2_master_data/models/g2p_geo.py` declares a nonunique
index on `level_value_mnemonic`; it does not declare the global unique index.
That runtime model inspection supports the proposed scope, but full API and
restart checks remain part of the shared change acceptance.

The SQL takes table locks inside one serializable transaction, verifies the
four levels, compares each changed row with its captured before-image, and
requires the complete final catalog to equal the canonical target. Unexpected
triggers, index definitions, catalog drift or missing rows abort the transaction.
An already-canonical rerun preserves all rows. Use PostgreSQL 16 tools. This is
a shared maintenance operation; the Farmer-only window does not authorize it.

## Consumer evidence

| Consumer database | Tables inventoried | Nonempty references | References with changed place/ancestor | Unresolved references |
| --- | ---: | ---: | ---: | ---: |
| farmer_registry_far | 18 | 2,191 | 1 | 2,187 |
| cropsown_registry_crop | 9 | 98 | 11 | 0 |
| livestock_registry_live | 6 | 0 | 0 | 0 |

The impact count follows canonical ancestors and includes canonical references
only. Eleven deployed workloads expose Master Data configuration. This is a
snapshot of deployed registries, not a claim about unknown external clients.
Crop selections and any stored hierarchy projections need explicit review even
though their IDs remain valid. Regenerate or reconcile embedded hierarchy names
only through a separately tested consumer change; this SQL does not touch them.

The unresolved Farmer snapshot has 697 table/ID groups representing 2,187
references. It includes slash-delimited non-Ethiopian location paths and UUIDs.
These IDs have no proven canonical target. Do not infer a location from a name,
delete a record, or relabel it as synthetic without record-level evidence.
A record owner must decide which records require source-based correction and
which, if proven fixtures, may be archived through an approved cleanup process.
The current exact-reference gate must remain closed until this is reconciled.

## Rehearsal and recovery evidence

The complete staging Master Data dump was restored into PostgreSQL 16 on an
internal Docker network, with no route to staging. The reviewed SQL installed
all 21,053 canonical rows, preserved IDs and all unrelated fields/rows in all
seven tables, and passed an idempotent rerun. An injected unrelated catalog edit
caused the whole SQL transaction to abort; a full catalog fingerprint proved
no partial update remained. The initial unmodified schema correctly rejected
canonical names under global uniqueness; the final proposal includes the
explicitly reviewed index replacement above.

Protected source backups:

- `/var/backups/farmer-staging-20261016-geography-review/master_data.dump`
- `/var/backups/farmer-staging-20261016-initial/farmer_registry_far.dump`
- `/var/backups/farmer-staging-20261016-initial/farmer_connector_far.dump`

The review package is retained at
`/var/lib/registry-coordination/farmer-staging-20261016-geography-review/` with
checksums, before/after catalog rows, unresolved reference groups, consumer
impact and rehearsal results. A protected second copy remains in the operator
workspace. These are preparation backups; take and restore-test fresh backups
again before any approved shared maintenance window. For recovery, restore the
reviewed catalog fields **and** global index from the retained dump only after
stopping shared writers and verifying there are no post-cutover dependent
writes. Do not use the full dump to overwrite unrelated live Master Data tables.
Rehearse the inverse or isolated restore and verify consumer consistency first.

## Reproducing the proposal

From protected snapshots, never from guessed labels:

```sh
python scripts/prepare-staging-geo-repair.py \
  --catalog /private/geography.json \
  --references /private/geography-references.json \
  --output /private/new-geography-review
```

The helper is offline and only writes a new protected directory. Inspect its
`review.json`, `catalog-diff.json`, `unresolved-references.json` and
`catalog-repair.sql`. It does not execute SQL or authorize an apply. Required
review covers the index replacement, every shared consumer, unresolved Farmer
records, owning Commons configuration, fresh backups, rehearsed recovery and a
shared maintenance window. The broader Commons immutable-selector repair is a
separate change.


## Authorized execution

Fresh full dumps of Master Data, Farmer, Crop and Livestock were taken under
`/var/backups/farmer-staging-20261016-approved-geo/`. Checksums were verified and
the fresh Master Data dump was restored in isolation. A guarded inverse restored
the captured catalog fields and original global unique index; inverse rerun and
forward reapplication passed before live execution.

The reviewed live SQL committed atomically. All 21,053 canonical IDs, names and
parents were verified; unrelated fields and rows across all seven Master Data
tables were preserved. No registry domain records were changed. The transaction's
catalog write lock kept the update consistent while readers and ODK collection
remained available. The journal and guarded inverse are under
`/var/lib/registry-coordination/farmer-staging-20261016-approved-geo/`.

API acceptance uncovered an independent credential mismatch. The installed
Master Data Deployment referenced `master-data/master-data-db-user`, which
failed database authentication. The dedicated Secret
`master-data-db-user/master-data-db-user-password` connected successfully.
Commons Services' existing owning Helm values and rendered manifest already
reference that dedicated Secret; the failed immutable-selector upgrade had not
applied it to the live Deployment. A resource-version-guarded patch applied
**only that one desired environment reference**, preserving every other spec
field. The rolling update completed with one ready replica. No database password
or Secret data was rotated, and the broader failed Commons release was not
upgraded. Four authenticated geography API requests then passed, checking all
levels, regions, and formerly broken Addis Ababa/Jimma child paths against the
canonical IDs, labels and parents. Signature, issuer and CSRF checks stayed on.

The remaining invalid Farmer selections are separate from this catalog repair.
Read-only provenance checks identify seeded Kamuntu demo locations; no domains
were rewritten or assigned invented Ethiopian locations.
