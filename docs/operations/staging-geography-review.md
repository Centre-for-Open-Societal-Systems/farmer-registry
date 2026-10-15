# Staging shared-geography repair proposal

This proposal is **prepared for review, not approved or applied**. The user
extended the Farmer task to preparation of a separately reviewed shared repair.
Farmer's published ODK version 1.0.5 already uses canonical seed choices; the
Registry/connector cutover remains gated on geography and partner readiness.

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
