import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  Pencil,
  PlayCircle,
  RefreshCw,
  AlertCircle,
  CheckCircle2,
  Clock,
  Inbox,
  RotateCcw,
  ChevronDown,
  ChevronRight,
  Radio,
} from "lucide-react";
import { api } from "../api/client";
import { formatApiError } from "../api/errors";
import type {
  Connector,
  ConnectorStats,
  DLQPage,
  IngestionRun,
  RunsPage,
  WebSubSyncResponse,
} from "../api/types";
import Card from "../components/Card";
import StatusBadge from "../components/StatusBadge";

const POLL_REFRESH_MS = 5_000;
const PAGE_SIZE = 20;
const PUSH_TRANSPORTS = new Set(["webhook", "websub"]);

type TabId = "overview" | "runs" | "dlq";

export default function PipelineDetails() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const tab: TabId = (() => {
    const t = searchParams.get("tab");
    if (t === "runs" || t === "dlq") return t;
    return "overview";
  })();

  const setTab = (t: TabId) => {
    if (t === "overview") setSearchParams({});
    else setSearchParams({ tab: t });
  };

  const [connector, setConnector] = useState<Connector | null>(null);
  const [stats, setStats] = useState<ConnectorStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [pollingNow, setPollingNow] = useState(false);
  const [websubSyncing, setWebsubSyncing] = useState(false);
  const [websubSyncResult, setWebsubSyncResult] = useState<WebSubSyncResponse | null>(null);
  const [clearingIdempotency, setClearingIdempotency] = useState(false);
  const [message, setMessage] = useState("");
  const [refreshTick, setRefreshTick] = useState(0);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [c, s] = await Promise.all([
        api.getConnector(id),
        api.getConnectorStats(id),
      ]);
      setConnector(c);
      setStats(s);
      setError("");
    } catch (e) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setWebsubSyncResult(null);
    setLoading(true);
    load();
  }, [load]);

  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(load, POLL_REFRESH_MS);
    return () => clearInterval(t);
  }, [autoRefresh, load]);

  const handlePollNow = async () => {
    if (!id) return;
    setPollingNow(true);
    setMessage("");
    try {
      const r = await api.pollNow(id);
      setMessage(`Poll queued (task ${r.task_id.slice(0, 8)}). Watch live below…`);
      setRefreshTick((x) => x + 1);
      setTimeout(load, 1500);
    } catch (e) {
      setMessage(formatApiError(e));
    } finally {
      setPollingNow(false);
    }
  };

  const handleWebsubSync = async () => {
    if (!id) return;
    setWebsubSyncing(true);
    setMessage("");
    setWebsubSyncResult(null);
    try {
      const r = await api.websubSyncSubscriptions(id);
      setWebsubSyncResult(r);
      if (r.all_subscribe_ok) {
        setMessage(
          `WebSub hub: all ${r.topics_attempted.length} topic(s) subscribed successfully.`
        );
      } else {
        const failed = r.results.filter((x) => !x.subscribe_ok).map((x) => x.topic);
        setMessage(
          `WebSub hub: some subscriptions failed (${failed.join(", ") || "see details below"}).`
        );
      }
    } catch (e) {
      setMessage(formatApiError(e));
    } finally {
      setWebsubSyncing(false);
    }
  };

  const handleClearIdempotency = async () => {
    if (!id) return;
    if (
      !confirm(
        "Delete all idempotency keys for this pipeline? The same event IDs can be ingested again (use for testing; production duplicates may create extra registry rows)."
      )
    ) {
      return;
    }
    setClearingIdempotency(true);
    setMessage("");
    try {
      const r = await api.clearIdempotencyKeys(id);
      setMessage(`Cleared ${r.idempotency_keys_deleted} idempotency key(s).`);
      setRefreshTick((x) => x + 1);
      load();
    } catch (e) {
      setMessage(formatApiError(e));
    } finally {
      setClearingIdempotency(false);
    }
  };

  const sourceCfg = useMemo(() => parseJson(connector?.source_config_json), [connector]);

  if (loading) return <div className="text-center py-16 text-gray-500">Loading…</div>;
  if (!connector) return <div className="text-center py-16 text-gray-500">Not found.</div>;

  const isPush = PUSH_TRANSPORTS.has(connector.transport_type);
  const isPoll = !isPush;
  const counts = stats?.run_status_counts || {};

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/")}
            className="p-1.5 rounded hover:bg-gray-100 text-gray-500"
            title="Back"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">{connector.name}</h1>
            <div className="text-xs text-gray-500 font-mono">{connector.connector_id}</div>
          </div>
          <StatusBadge enabled={connector.enabled} paused={connector.paused} />
        </div>
        <div className="flex flex-wrap gap-2">
          <label className="inline-flex items-center gap-1.5 text-xs text-gray-600 px-2">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            Auto-refresh 5s
          </label>
          <button
            onClick={() => {
              load();
              setRefreshTick((x) => x + 1);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          {isPoll && (
            <button
              onClick={handlePollNow}
              disabled={pollingNow || !connector.enabled || connector.paused}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-amber-700 rounded-md hover:bg-amber-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <PlayCircle className="w-4 h-4" />
              {pollingNow ? "Queuing…" : "Poll now"}
            </button>
          )}
          {connector.transport_type === "websub" && (
            <button
              type="button"
              onClick={handleWebsubSync}
              disabled={websubSyncing || !connector.enabled || connector.paused}
              title="Register topics and subscribe this pipeline’s callback URL at the WebSub hub"
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-white bg-teal-700 rounded-md hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Radio className="w-4 h-4" />
              {websubSyncing ? "Syncing hub…" : "Sync hub subscriptions"}
            </button>
          )}
          <button
            type="button"
            onClick={handleClearIdempotency}
            disabled={clearingIdempotency || !connector.enabled || connector.paused}
            title="Remove dedupe keys so repeated event IDs are processed again"
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RotateCcw className="w-4 h-4" />
            {clearingIdempotency ? "Clearing…" : "Clear idempotency keys"}
          </button>
          <Link
            to={`/edit/${connector.connector_id}`}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <Pencil className="w-4 h-4" />
            Edit
          </Link>
        </div>
      </div>

      {error && (
        <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm">
          {error}
        </div>
      )}
      {message && (
        <div className="p-3 rounded-md bg-amber-50 border border-amber-200 text-amber-800 text-sm">
          {message}
        </div>
      )}
      {websubSyncResult && (
        <div className="p-4 rounded-md bg-white border border-[#d9d5c5] text-sm space-y-2">
          <div className="font-medium text-gray-900">WebSub hub sync</div>
          <div className="text-xs text-gray-600 break-all">
            <span className="font-medium">Hub:</span> {websubSyncResult.hub_url}
          </div>
          <div className="text-xs text-gray-600 break-all">
            <span className="font-medium">Callback:</span> {websubSyncResult.callback_url}
          </div>
          <ul className="mt-2 space-y-1.5 text-xs font-mono">
            {websubSyncResult.results.map((row) => (
              <li
                key={row.topic}
                className={`flex flex-wrap gap-x-2 gap-y-0.5 ${
                  row.subscribe_ok ? "text-green-800" : "text-red-700"
                }`}
              >
                <span className="break-all">{row.topic}</span>
                <span className="text-gray-500">
                  register {row.register_http_status ?? "—"} · subscribe{" "}
                  {row.subscribe_http_status ?? "—"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex gap-1 border-b border-[#d9d5c5]">
        {(
          [
            ["overview", "Overview"],
            ["runs", "Runs"],
            ["dlq", "Dead letter"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`px-4 py-2 text-sm font-medium rounded-t-md border border-b-0 -mb-px transition-colors ${
              tab === key
                ? "bg-white text-amber-900 border-[#d9d5c5] z-10"
                : "bg-[#f9f7f0] text-gray-600 border-transparent hover:text-gray-900"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          {isPoll && stats && <PollStatusBanner stats={stats} />}

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <Kpi label="Total runs" value={stats?.total_runs ?? 0} icon={<Inbox className="w-4 h-4" />} />
            <Kpi
              label="Success"
              value={counts.SUCCESS ?? 0}
              icon={<CheckCircle2 className="w-4 h-4" />}
              tone="green"
            />
            <Kpi
              label="Failed"
              value={counts.FAILED ?? 0}
              icon={<AlertCircle className="w-4 h-4" />}
              tone="red"
            />
            <Kpi
              label="Dead letter"
              value={stats?.dlq_count ?? 0}
              icon={<AlertCircle className="w-4 h-4" />}
              tone={(stats?.dlq_count ?? 0) > 0 ? "red" : "gray"}
            />
          </div>

          {stats?.last_run && (
            <Card title="Latest run" subtitle="Open the Runs tab for history, payloads, and filters.">
              <dl className="text-sm grid grid-cols-1 md:grid-cols-2 gap-2">
                <Row label="Run" value={<span className="font-mono text-xs">{stats.last_run.run_id}</span>} />
                <Row label="Status" value={<RunStatusChip status={stats.last_run.status} />} />
                <Row label="Source event" value={stats.last_run.source_event_id || "—"} />
                <Row label="Registry ID" value={<span className="font-mono text-xs">{stats.last_run.registry_correlation_id || "—"}</span>} />
                <Row
                  label="Last activity"
                  value={
                    <RelativeTime
                      iso={stats.last_run.updated_at || stats.last_run.created_at}
                    />
                  }
                />
              </dl>
              <button
                type="button"
                onClick={() => setTab("runs")}
                className="mt-3 text-sm text-amber-800 hover:underline"
              >
                View all runs →
              </button>
            </Card>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <Card title="Configuration">
              <dl className="text-sm divide-y divide-gray-100">
                <Row label="Platform" value={connector.platform} />
                <Row label="Transport" value={<code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{connector.transport_type}</code>} />
                <Row label="Auth" value={<code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{connector.auth_type}</code>} />
                <Row label="Data model" value={connector.data_model_mnemonic || "—"} />
                <Row
                  label="G2P sender"
                  value={
                    connector.g2p_sender_id
                      ? <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{connector.g2p_sender_id}</code>
                      : <span className="text-red-600">missing</span>
                  }
                />
                <Row
                  label="Target register"
                  value={
                    connector.g2p_register_mnemonic
                      ? <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{connector.g2p_register_mnemonic}</code>
                      : <span className="text-red-600">missing</span>
                  }
                />
                <Row label="Poll interval" value={stats?.poll_interval_seconds ? `${stats.poll_interval_seconds}s` : "—"} />
                <Row label="Max in-flight" value={connector.max_in_flight ?? "—"} />
                {sourceCfg && Object.keys(sourceCfg).length > 0 && (
                  <div className="py-2">
                    <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Source config</div>
                    <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto">{JSON.stringify(sourceCfg, null, 2)}</pre>
                  </div>
                )}
              </dl>
            </Card>

            <Card title="Polling">
              {isPush ? (
                <div className="text-sm text-gray-600">
                  {connector.transport_type === "websub" ? "WebSub" : "Webhook"} connector. Incoming events arrive at{" "}
                  <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">
                    POST /webhook/by-slug/{connector.webhook_path_slug || "(slug missing)"}
                  </code>
                  . No scheduled polling.
                </div>
              ) : (
                <dl className="text-sm divide-y divide-gray-100">
                  <Row
                    label="Last poll"
                    value={stats?.last_poll_at ? new Date(stats.last_poll_at).toLocaleString() : "Never"}
                  />
                  <Row label="Last status" value={<PollStatusChip status={stats?.last_poll_status} />} />
                  <Row label="Fetched last" value={stats?.last_poll_fetched ?? "—"} />
                  <Row
                    label="Duration"
                    value={stats?.last_poll_duration_ms != null ? `${stats.last_poll_duration_ms} ms` : "—"}
                  />
                  <Row
                    label="Next poll"
                    value={
                      stats?.next_poll_at
                        ? <RelativeTime iso={stats.next_poll_at} />
                        : stats?.poll_interval_seconds
                        ? "Soon (never polled)"
                        : "—"
                    }
                  />
                  {stats?.last_poll_error && (
                    <div className="py-2">
                      <div className="text-xs font-medium text-red-600 uppercase tracking-wide mb-1">Last poll error</div>
                      <pre className="text-xs bg-red-50 border border-red-200 rounded p-2 overflow-x-auto text-red-800 whitespace-pre-wrap">{stats.last_poll_error}</pre>
                    </div>
                  )}
                  {stats?.poll_state && Object.keys(stats.poll_state).length > 0 && (
                    <div className="py-2">
                      <div className="flex items-center justify-between mb-1">
                        <div className="text-xs font-medium text-gray-500 uppercase tracking-wide">Cursor (incremental)</div>
                        <button
                          onClick={async () => {
                            if (!confirm("Reset cursor? Next poll will re-fetch from the beginning.")) return;
                            try {
                              await api.resetCursor(id);
                              setMessage("Cursor reset. Next poll starts from the top.");
                              load();
                            } catch (e) {
                              setMessage(formatApiError(e));
                            }
                          }}
                          className="text-xs text-amber-700 hover:text-amber-900 hover:underline"
                        >
                          Reset cursor
                        </button>
                      </div>
                      <pre className="text-xs bg-gray-50 border border-gray-200 rounded p-2 overflow-x-auto">{JSON.stringify(stats.poll_state, null, 2)}</pre>
                    </div>
                  )}
                </dl>
              )}
            </Card>
          </div>

          {stats != null && stats.dlq_count > 0 && (
            <div className="text-sm text-gray-600">
              This pipeline has{" "}
              <button type="button" className="text-amber-800 font-medium hover:underline" onClick={() => setTab("dlq")}>
                {stats.dlq_count} dead-letter {stats.dlq_count === 1 ? "entry" : "entries"}
              </button>
              .
            </div>
          )}
        </>
      )}

      {tab === "runs" && (
        <PipelineRunsTab connectorId={id} refreshTick={refreshTick} />
      )}

      {tab === "dlq" && (
        <PipelineDLQTab connectorId={id} refreshTick={refreshTick} />
      )}
    </div>
  );
}

function PipelineRunsTab({ connectorId, refreshTick }: { connectorId: string; refreshTick: number }) {
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");
  const [qApplied, setQApplied] = useState("");
  const [status, setStatus] = useState("");
  const [data, setData] = useState<RunsPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [payloadByRun, setPayloadByRun] = useState<Record<string, IngestionRun>>({});

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const r = await api.listRuns({
        connectorId,
        offset: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: qApplied || undefined,
        status: status || undefined,
      });
      setData(r);
    } catch (e: unknown) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [connectorId, page, qApplied, status]);

  useEffect(() => {
    load();
  }, [load, refreshTick]);

  const applySearch = () => {
    setPage(0);
    setQApplied(q.trim());
  };

  const togglePayload = async (runId: string) => {
    if (expanded === runId) {
      setExpanded(null);
      return;
    }
    setExpanded(runId);
    if (!payloadByRun[runId]) {
      try {
        const full = await api.getRun(runId, true);
        setPayloadByRun((prev) => ({ ...prev, [runId]: full }));
      } catch {
        setPayloadByRun((prev) => ({ ...prev, [runId]: { run_id: runId } as IngestionRun }));
      }
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Card title="Ingestion runs" subtitle="Expand a row to load source / mapped / outbound payload (when stored). Duplicate ODK deliveries increment ×n on the canonical run.">
      <div className="flex flex-wrap gap-3 mb-4 items-end">
        <label className="block text-xs text-gray-600">
          <span className="block mb-1">Search</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applySearch()}
            className="input rounded-md border border-gray-300 px-2 py-1.5 text-sm w-56"
            placeholder="event id, run id, correlation…"
          />
        </label>
        <label className="block text-xs text-gray-600">
          <span className="block mb-1">Status</span>
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setPage(0);
            }}
            className="input rounded-md border border-gray-300 px-2 py-1.5 text-sm"
          >
            <option value="">Any</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILED">FAILED</option>
            <option value="IN_PROGRESS">IN_PROGRESS</option>
            <option value="PENDING">PENDING</option>
          </select>
        </label>
        <button
          type="button"
          onClick={applySearch}
          className="px-3 py-1.5 text-sm bg-amber-700 text-white rounded-md hover:bg-amber-800"
        >
          Search
        </button>
      </div>

      {err && <div className="mb-3 text-sm text-red-600">{err}</div>}

      {loading ? (
        <div className="text-gray-500 py-8">Loading…</div>
      ) : !data?.items.length ? (
        <div className="text-gray-500 py-8">No runs match.</div>
      ) : (
        <>
          <div className="overflow-x-auto border border-gray-200 rounded-md">
            <table className="min-w-full text-sm">
              <thead className="bg-[#f9f7f0]">
                <tr className="text-left text-xs text-gray-600 uppercase">
                  <th className="px-3 py-2 w-8" />
                  <th className="px-3 py-2">Run</th>
                  <th className="px-3 py-2">Event</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Dup</th>
                  <th className="px-3 py-2">Registry ID</th>
                  <th className="px-3 py-2">Last activity</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {data.items.map((r) => (
                  <Fragment key={r.run_id}>
                    <tr className="hover:bg-[#faf8f2]">
                      <td className="px-3 py-2">
                        <button
                          type="button"
                          onClick={() => togglePayload(r.run_id)}
                          className="p-1 text-gray-500 hover:text-gray-800"
                          aria-label="Toggle payload"
                        >
                          {expanded === r.run_id ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        </button>
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{r.run_id.slice(0, 12)}…</td>
                      <td className="px-3 py-2 text-gray-700 max-w-[200px] truncate" title={r.source_event_id || ""}>
                        {r.source_event_id || "—"}
                      </td>
                      <td className="px-3 py-2"><RunStatusChip status={r.status} /></td>
                      <td className="px-3 py-2">
                        {r.redelivery_count > 0 ? (
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-900" title="Extra deliveries after first success">
                            ×{r.redelivery_count}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-3 py-2 font-mono text-xs">{r.registry_correlation_id || "—"}</td>
                      <td className="px-3 py-2 text-gray-500 whitespace-nowrap">
                        <RelativeTime iso={r.updated_at || r.created_at} />
                      </td>
                    </tr>
                    {expanded === r.run_id && (
                      <tr className="bg-gray-50">
                        <td colSpan={7} className="px-3 py-3">
                          <div className="text-xs text-gray-500 mb-1">Payload (debug)</div>
                          <pre className="text-xs bg-white border border-gray-200 rounded p-2 overflow-x-auto max-h-96 overflow-y-auto">
                            {JSON.stringify(
                              payloadByRun[r.run_id]?.run_payload ?? { _note: "Loading or disabled (CONNECTOR_STORE_RUN_PAYLOADS)…" },
                              null,
                              2
                            )}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between mt-3 text-sm text-gray-600">
            <span>
              {data.total === 0 ? "0" : `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, data.total)}`} of {data.total}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="px-2 py-1 border rounded disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                className="px-2 py-1 border rounded disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}

function PipelineDLQTab({ connectorId, refreshTick }: { connectorId: string; refreshTick: number }) {
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");
  const [qApplied, setQApplied] = useState("");
  const [category, setCategory] = useState("");
  const [data, setData] = useState<DLQPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [replaying, setReplaying] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const r = await api.listDLQ({
        connectorId,
        offset: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        q: qApplied || undefined,
        errorCategory: category || undefined,
      });
      setData(r);
    } catch (e: unknown) {
      setErr(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [connectorId, page, qApplied, category]);

  useEffect(() => {
    load();
  }, [load, refreshTick]);

  const applySearch = () => {
    setPage(0);
    setQApplied(q.trim());
  };

  const replay = async (dlId: string) => {
    setReplaying((s) => new Set(s).add(dlId));
    try {
      await api.replayDLQ([dlId]);
      load();
    } catch (e: unknown) {
      setErr(formatApiError(e));
    } finally {
      setReplaying((s) => {
        const n = new Set(s);
        n.delete(dlId);
        return n;
      });
    }
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;

  return (
    <Card title="Dead letter queue" subtitle="Failed ingestions for this pipeline. Replay re-queues processing.">
      <div className="flex flex-wrap gap-3 mb-4 items-end">
        <label className="block text-xs text-gray-600">
          <span className="block mb-1">Search</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && applySearch()}
            className="input rounded-md border border-gray-300 px-2 py-1.5 text-sm w-56"
            placeholder="dl id, event, error…"
          />
        </label>
        <label className="block text-xs text-gray-600">
          <span className="block mb-1">Category</span>
          <select
            value={category}
            onChange={(e) => {
              setCategory(e.target.value);
              setPage(0);
            }}
            className="input rounded-md border border-gray-300 px-2 py-1.5 text-sm"
          >
            <option value="">Any</option>
            <option value="transient">transient</option>
            <option value="permanent">permanent</option>
            <option value="validation">validation</option>
            <option value="config">config</option>
          </select>
        </label>
        <button
          type="button"
          onClick={applySearch}
          className="px-3 py-1.5 text-sm bg-amber-700 text-white rounded-md hover:bg-amber-800"
        >
          Search
        </button>
      </div>

      {err && <div className="mb-3 text-sm text-red-600">{err}</div>}

      {loading ? (
        <div className="text-gray-500 py-8">Loading…</div>
      ) : !data?.items.length ? (
        <div className="text-gray-500 py-8">No dead-letter entries.</div>
      ) : (
        <>
          <div className="space-y-2">
            {data.items.map((d) => (
              <div key={d.dl_id} className="border border-red-200 bg-red-50/50 rounded-md p-3 text-sm">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <button
                    type="button"
                    onClick={() =>
                      setExpanded((prev) => {
                        const n = new Set(prev);
                        if (n.has(d.dl_id)) n.delete(d.dl_id);
                        else n.add(d.dl_id);
                        return n;
                      })
                    }
                    className="flex items-center gap-1 font-mono text-xs text-gray-800"
                  >
                    {expanded.has(d.dl_id) ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                    {d.dl_id.slice(0, 14)}…
                  </button>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500">{d.error_category || "unknown"}</span>
                    <button
                      type="button"
                      disabled={replaying.has(d.dl_id)}
                      onClick={() => replay(d.dl_id)}
                      className="text-xs px-2 py-1 bg-white border border-red-300 rounded hover:bg-red-50 disabled:opacity-50"
                    >
                      {replaying.has(d.dl_id) ? "Replaying…" : "Replay"}
                    </button>
                  </div>
                </div>
                <div className="text-red-800 mt-1 whitespace-pre-wrap break-words text-xs">{d.error}</div>
                {expanded.has(d.dl_id) && d.payload && (
                  <pre className="mt-2 text-xs bg-white border border-red-100 rounded p-2 overflow-x-auto max-h-64 overflow-y-auto">
                    {JSON.stringify(d.payload, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between mt-3 text-sm text-gray-600">
            <span>
              {data.total === 0 ? "0" : `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, data.total)}`} of {data.total}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="px-2 py-1 border rounded disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                className="px-2 py-1 border rounded disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </Card>
  );
}

function PollStatusBanner({ stats }: { stats: ConnectorStats }) {
  if (!stats.last_poll_at) {
    return (
      <div className="flex items-start gap-3 p-3 rounded-md bg-blue-50 border border-blue-200 text-blue-800 text-sm">
        <Clock className="w-4 h-4 mt-0.5 shrink-0" />
        <div>
          <div className="font-medium">Never polled yet.</div>
          <div className="text-blue-700 text-xs mt-0.5">
            Beat runs every 60s. Use <em>Poll now</em> to trigger immediately.
          </div>
        </div>
      </div>
    );
  }
  if (stats.last_poll_status === "FAILED") {
    return (
      <div className="flex items-start gap-3 p-3 rounded-md bg-red-50 border border-red-200 text-red-800 text-sm">
        <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
        <div>
          <div className="font-medium">Last poll failed.</div>
          <div className="text-xs mt-0.5">
            {new Date(stats.last_poll_at).toLocaleString()} —{" "}
            {stats.last_poll_error?.split("\n")[0]?.slice(0, 200) || "Unknown error"}
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-3 p-3 rounded-md bg-green-50 border border-green-200 text-green-800 text-sm">
      <CheckCircle2 className="w-4 h-4 mt-0.5 shrink-0" />
      <div>
        <div className="font-medium">
          Last poll {stats.last_poll_status?.toLowerCase() || "ok"} · fetched {stats.last_poll_fetched ?? 0}
        </div>
        <div className="text-xs mt-0.5">
          {new Date(stats.last_poll_at).toLocaleString()}
          {stats.last_poll_duration_ms != null && ` · ${stats.last_poll_duration_ms} ms`}
        </div>
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  icon,
  tone = "gray",
}: {
  label: string;
  value: number | string;
  icon?: React.ReactNode;
  tone?: "gray" | "green" | "red";
}) {
  const toneClass =
    tone === "green"
      ? "text-green-700"
      : tone === "red"
      ? "text-red-700"
      : "text-gray-900";
  return (
    <div className="bg-white rounded-lg border border-[#d9d5c5] shadow-sm p-4">
      <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wide">
        {icon}
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="py-2 flex items-start justify-between gap-3">
      <dt className="text-xs font-medium text-gray-500 uppercase tracking-wide shrink-0">{label}</dt>
      <dd className="text-sm text-gray-800 text-right break-words">{value}</dd>
    </div>
  );
}

function PollStatusChip({ status }: { status?: string | null }) {
  if (!status) return <span className="text-gray-400">—</span>;
  const map: Record<string, string> = {
    SUCCESS: "bg-green-100 text-green-800",
    PARTIAL: "bg-yellow-100 text-yellow-800",
    FAILED: "bg-red-100 text-red-800",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${map[status] || "bg-gray-100 text-gray-700"}`}>
      {status}
    </span>
  );
}

function RunStatusChip({ status }: { status: string }) {
  const map: Record<string, string> = {
    SUCCESS: "bg-green-100 text-green-800",
    FAILED: "bg-red-100 text-red-800",
    RETRYING: "bg-yellow-100 text-yellow-800",
    PENDING: "bg-gray-100 text-gray-700",
    IN_PROGRESS: "bg-blue-100 text-blue-800",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${map[status] || "bg-gray-100 text-gray-700"}`}>
      {status}
    </span>
  );
}

function RelativeTime({ iso }: { iso: string }) {
  const d = new Date(iso);
  const diff = (d.getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  const unit =
    abs < 60 ? `${Math.round(abs)}s` :
    abs < 3600 ? `${Math.round(abs / 60)}m` :
    abs < 86400 ? `${Math.round(abs / 3600)}h` :
    `${Math.round(abs / 86400)}d`;
  const label = diff >= 0 ? `in ${unit}` : `${unit} ago`;
  return <span title={d.toLocaleString()}>{label}</span>;
}

function parseJson(v: string | null | undefined): Record<string, unknown> | null {
  if (!v) return null;
  try {
    const p = JSON.parse(v);
    return typeof p === "object" && p !== null ? (p as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}
