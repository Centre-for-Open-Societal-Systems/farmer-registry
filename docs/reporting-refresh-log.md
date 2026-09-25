# Reporting-view refresh log

The registry's reporting views (`fr_rpt_*`) are materialized views. The
`<release>-fr-reporting-views-refresh` CronJob rebuilds them on
`analytics.reportingViews.refreshSchedule` (hourly by default), in dependency order. If a refresh
fails, dashboards keep showing the last good snapshot, which is safe but silent. This log makes
refresh health observable.

The job logic lives in `helm/openg2p-farmer-registry/files/reporting-views-refresh.sh`, and the
CronJob embeds it.

## Outcomes

Each view in each run produces exactly one outcome:

| `status` | Meaning |
| --- | --- |
| `refreshed` | Refreshed `CONCURRENTLY`; readers were never blocked |
| `refreshed_blocking` | `CONCURRENTLY` failed (reason in `concurrent_error`, usually a missing unique index), and a plain `REFRESH` succeeded. Readers were blocked briefly. Treat it as a warning to fix |
| `failed` | Both attempts failed. The view keeps its previous snapshot. `error` and `sqlstate` say why. The Job exits non-zero |
| `skipped` | Run-level event (`view_name` is null): no views matched `matchPrefix`. Normal only before the post-install hook has created the views |

A failure outside a single view is recorded as `failed` with `view_name` null, for example when
view discovery fails. If the log table cannot be written, the job prints a
`reporting_refresh_log_unavailable` event and carries on refreshing.

## Where outcomes are written

### 1. JSON lines on stdout

The job prints one JSON object per outcome, suitable for any log collector (Loki, Elasticsearch,
CloudWatch, …):

```json
{"event": "reporting_view_refresh", "run_id": "20260925T053105Z-refresh-28791234-abcde",
 "job": "refresh-28791234-abcde", "view_name": "fr_rpt_farmer", "status": "failed",
 "error": "division by zero", "sqlstate": "22012", "concurrent_error": "division by zero",
 "started_at": "2026-09-25T05:31:05.85+00:00", "finished_at": "2026-09-25T05:31:05.86+00:00",
 "duration_ms": 6}
```

Filter on `event = "reporting_view_refresh"`.

### 2. The `reporting_refresh_log` table

Written to the registry database when `analytics.reportingViews.refreshLog.enabled` is true (the
default). The job creates the table and view if they are missing, so any registry version gets
them.

| Column | Type | Notes |
| --- | --- | --- |
| `id` | bigserial | |
| `run_id` | text | Same for every view in one run |
| `view_name` | text | Null for run-level events |
| `status` | text | See [Outcomes](#outcomes) |
| `concurrent_error` | text | Why `CONCURRENTLY` failed, when there was a fallback |
| `error`, `sqlstate` | text | Final error, for `failed` and run-level events |
| `started_at`, `finished_at` | timestamptz | |
| `duration_ms` | integer | |
| `job` | text | Pod name |

- **`reporting_refresh_latest`** is a view with the most recent outcome for each view.
- **Retention:** rows older than `analytics.reportingViews.refreshLog.retentionDays` (default 90)
  are deleted at the end of each run.

## Configuration

```yaml
analytics:
  reportingViews:
    refreshSchedule: "0 * * * *"
    matchPrefix: fr_rpt_
    refreshLog:
      enabled: true        # false: JSON lines only, no table
      retentionDays: 90
```

## Queries for a telemetry dashboard

Current state per view, and how stale each one is:

```sql
SELECT view_name, status, finished_at, now() - finished_at AS age, error
FROM reporting_refresh_latest
ORDER BY view_name;
```

Failure rate and duration per view, over the last 7 days:

```sql
SELECT view_name,
       count(*)                                      AS runs,
       count(*) FILTER (WHERE status = 'failed')     AS failed,
       count(*) FILTER (WHERE status = 'refreshed_blocking') AS blocking,
       percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_ms
FROM reporting_refresh_log
WHERE view_name IS NOT NULL AND started_at > now() - interval '7 days'
GROUP BY view_name
ORDER BY failed DESC, view_name;
```

Alert condition: a view whose last success is older than two refresh intervals:

```sql
SELECT view_name, max(finished_at) AS last_success
FROM reporting_refresh_log
WHERE status IN ('refreshed', 'refreshed_blocking')
GROUP BY view_name
HAVING max(finished_at) < now() - interval '2 hours';
```

A telemetry dashboard should read these through a read-only role with `SELECT` on
`reporting_refresh_log` and `reporting_refresh_latest`.

## Running the refresh by hand

The script needs only `psql` and a POSIX shell, so it runs in the registry `db-seed` image:

```bash
docker run --rm --network <registry-network> \
  -v "$PWD/helm/openg2p-farmer-registry/files/reporting-views-refresh.sh:/refresh.sh:ro" \
  -e PGHOST=postgres -e PGDATABASE=farmer_registry_db -e PGUSER=<user> -e PGPASSWORD=<password> \
  -e MATCH_PREFIX=fr_rpt_ \
  --entrypoint sh <db-seed-image> /refresh.sh
```

In a cluster, trigger it from the CronJob:
`kubectl create job --from=cronjob/<release>-fr-reporting-views-refresh refresh-now`.
