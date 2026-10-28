# Connector signing, checkpoints and recovery

Dev uses `farmer-registry-connector` in `farmer`, isolated database
`farmer_connector_v2`, queue `farmer-registry-connector-v2`, and one beat scheduler.
Its permanent ODK pipeline remains active. The old dev release was uninstalled
after acceptance; its database and backups remain. Staging still uses
`farmer-connector` in `far`, with database `farmer_connector_far`.

The [staging migration candidate](staging-upgrade.md) prepares
`farmer-registry-connector` in `far`, database `farmer_connector_v2_far`, queue
`farmer-registry-connector-v2-far`, and a dedicated staging signing Secret. This
is a gated candidate; staging ingestion and retirement have not been executed.
Operator CLIs now take an explicit `--environment dev|staging` to select their
namespace and backup/acceptance contract.

`farmer-partner` is the approved permanent dev identity. Its private signing key
lives in retained Secret `farmer-connector-v2-signing`, never in Git. RS256
messages bind partner/message identifiers, canonical payload hash, issued-at and
expiry. Invalid, unsigned, tampered, wrong-key and expired envelopes are rejected;
exact signed retries return the original correlation identifier.

ODK collector identity populates the intake creator and Enumerator field and the
worker's change-request path. Attachments persist through approval. Dev web and
signed ODK intake passed the live approval policy and reached Register; see
acceptance evidence.

Operator tools live in `scripts/operations/connector/`:

- `inventory.py`: protected configuration/database/checkpoint backups and hashes.
- `rehearse.py`: disposable-database migration, retry and rollback rehearsal.
- `release_handoff.py`: guarded process, scheduler and route changes.
- `fetch_backup.py`: protected transfer using checked host keys.

Checkpoint reconciliation lives in the runtime integration. Recovery requires
paused pipelines and no in-progress work. Preserve successful idempotency keys
and same-timestamp boundary IDs. Never rewind checkpoints or start two schedulers.
Reconcile before resuming a previous implementation. The retained old unsigned
image cannot simply resume against signature-enforcing intake.

Server backups under `/var/backups/farmer-connector-20261015-*` and journals under
`/var/lib/registry-coordination/` are retained. Cleanup preserves those backups,
databases, shared PostgreSQL/Redis and live keys. Staging remains read-only.
