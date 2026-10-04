import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { RefreshCw, ChevronDown, ChevronRight } from "lucide-react";
import { api } from "../api/client";
import { formatApiError } from "../api/errors";
import type { Connector, IngestionRun, RunsPage } from "../api/types";

const PAGE_SIZE = 25;
type RunsGroup = {
  connectorId: string;
  connectorName: string;
  items: IngestionRun[];
  total: number;
  page: number;
};

export default function RunsList() {
  const [data, setData] = useState<RunsPage | null>(null);
  const [groupedRuns, setGroupedRuns] = useState<RunsGroup[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(0);
  const [groupPages, setGroupPages] = useState<Record<string, number>>({});
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [connectorFilter, setConnectorFilter] = useState("");
  const [q, setQ] = useState("");
  const [qApplied, setQApplied] = useState("");
  const [status, setStatus] = useState("");
  const [groupByConnector, setGroupByConnector] = useState(true);
  const isGroupedMode = groupByConnector && !connectorFilter;

  const nameById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const c of connectors) m[c.connector_id] = c.name;
    return m;
  }, [connectors]);

  useEffect(() => {
    api.listConnectors().then(setConnectors).catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      if (isGroupedMode) {
        const groups = await Promise.all(
          connectors.map(async (connector) => {
            const groupPage = groupPages[connector.connector_id] ?? 0;
            const runsPage = await api.listRuns({
              connectorId: connector.connector_id,
              q: qApplied || undefined,
              status: status || undefined,
              offset: groupPage * PAGE_SIZE,
              limit: PAGE_SIZE,
              orderBy: "time",
            });
            return {
              connectorId: connector.connector_id,
              connectorName: connector.name,
              items: runsPage.items,
              total: runsPage.total,
              page: groupPage,
            } satisfies RunsGroup;
          })
        );
        const nonEmpty = groups.filter((g) => g.total > 0).sort((a, b) => a.connectorName.localeCompare(b.connectorName));
        setGroupedRuns(nonEmpty);
        setData({ items: [], total: nonEmpty.reduce((acc, g) => acc + g.total, 0) });
        setExpandedGroups((prev) => {
          const next = new Set(prev);
          for (const g of nonEmpty) {
            if (!next.has(g.connectorId)) next.add(g.connectorId);
          }
          return next;
        });
        return;
      }

      const runsPage = await api.listRuns({
        connectorId: connectorFilter || undefined,
        q: qApplied || undefined,
        status: status || undefined,
        offset: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        orderBy: groupByConnector ? "connector" : "time",
      });
      setData(runsPage);
      setGroupedRuns([]);
    } catch (e: unknown) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [connectorFilter, qApplied, status, page, groupByConnector, isGroupedMode, connectors, groupPages]);

  useEffect(() => {
    load();
  }, [load]);

  const applySearch = () => {
    setPage(0);
    setGroupPages({});
    setQApplied(q.trim());
  };

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const totalRuns = isGroupedMode
    ? groupedRuns.reduce((acc, g) => acc + g.total, 0)
    : data?.total ?? 0;
  const ungroupedData = data ?? { items: [], total: 0 };

  return (
    <div>
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-gray-900">Ingestion Runs</h1>
        <button
          onClick={load}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      <div className="bg-white rounded-lg border border-[#d9d5c5] shadow-sm p-4 mb-4 space-y-3">
        <div className="flex flex-wrap gap-3 items-end">
          <label className="block text-xs text-gray-600">
            <span className="block mb-1">Pipeline</span>
            <select
              value={connectorFilter}
              onChange={(e) => {
                setConnectorFilter(e.target.value);
                setPage(0);
                setGroupPages({});
              }}
              className="rounded-md border border-gray-300 px-2 py-1.5 text-sm min-w-[200px]"
            >
              <option value="">All pipelines</option>
              {connectors.map((c) => (
                <option key={c.connector_id} value={c.connector_id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-xs text-gray-600">
            <span className="block mb-1">Search</span>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applySearch()}
              className="rounded-md border border-gray-300 px-2 py-1.5 text-sm w-56"
              placeholder="event, run id, correlation…"
            />
          </label>
          <label className="block text-xs text-gray-600">
            <span className="block mb-1">Status</span>
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(0);
                setGroupPages({});
              }}
              className="rounded-md border border-gray-300 px-2 py-1.5 text-sm"
            >
              <option value="">Any</option>
              <option value="SUCCESS">SUCCESS</option>
              <option value="FAILED">FAILED</option>
              <option value="IN_PROGRESS">IN_PROGRESS</option>
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
        <label className="inline-flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
          <input
            type="checkbox"
            checked={groupByConnector}
            onChange={(e) => {
              setGroupByConnector(e.target.checked);
              setPage(0);
              setGroupPages({});
            }}
            className="rounded border-gray-300 text-amber-700"
          />
          Group by pipeline (accordion)
        </label>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>
      )}

      {loading ? (
        <div className="text-center py-16 text-gray-500">Loading…</div>
      ) : totalRuns === 0 ? (
        <div className="text-center py-16 text-gray-500">No runs yet.</div>
      ) : isGroupedMode ? (
        <div className="space-y-3">
          {groupedRuns.map((group) => {
            const isOpen = expandedGroups.has(group.connectorId);
            const groupTotalPages = Math.max(1, Math.ceil(group.total / PAGE_SIZE));
            return (
              <div key={group.connectorId} className="bg-white rounded-lg border border-[#d9d5c5] shadow-sm overflow-hidden">
                <button
                  type="button"
                  className="w-full px-4 py-3 bg-[#f9f7f0] flex items-center justify-between text-left hover:bg-[#f3efe3]"
                  onClick={() =>
                    setExpandedGroups((prev) => {
                      const next = new Set(prev);
                      if (next.has(group.connectorId)) next.delete(group.connectorId);
                      else next.add(group.connectorId);
                      return next;
                    })
                  }
                >
                  <span className="text-sm font-semibold text-gray-800">{group.connectorName}</span>
                  <span className="inline-flex items-center gap-2 text-xs text-gray-600">
                    {group.total} runs
                    {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </span>
                </button>

                {isOpen && (
                  <div className="p-3 space-y-3">
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-[#f9f7f0]">
                          <tr>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Run ID</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Source Event</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Status</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Dup</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Registry ID</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Last activity</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase" />
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {group.items.map((r) => (
                            <tr key={r.run_id} className="hover:bg-[#faf8f2]">
                              <td className="px-4 py-3 text-sm font-mono text-gray-700">{r.run_id.slice(0, 12)}…</td>
                              <td className="px-4 py-3 text-sm text-gray-600 max-w-xs truncate">{r.source_event_id || "—"}</td>
                              <td className="px-4 py-3 text-sm">
                                <RunStatusBadge status={r.status} />
                              </td>
                              <td className="px-4 py-3 text-sm">
                                {r.redelivery_count > 0 ? (
                                  <span className="inline-flex px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-900">
                                    ×{r.redelivery_count}
                                  </span>
                                ) : (
                                  "—"
                                )}
                              </td>
                              <td className="px-4 py-3 text-sm font-mono text-xs text-gray-600">{r.registry_correlation_id || "—"}</td>
                              <td className="px-4 py-3 text-sm text-gray-500">{new Date(r.updated_at || r.created_at).toLocaleString()}</td>
                              <td className="px-4 py-3 text-sm">
                                <Link
                                  to={`/pipelines/${r.connector_id}?tab=runs`}
                                  className="inline-flex items-center gap-0.5 text-amber-800 hover:underline text-xs"
                                >
                                  Pipeline <ChevronRight className="w-3 h-3" />
                                </Link>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="flex items-center justify-between text-sm text-gray-600">
                      <span>
                        {group.total === 0
                          ? "0"
                          : `${group.page * PAGE_SIZE + 1}–${Math.min((group.page + 1) * PAGE_SIZE, group.total)} of ${group.total}`}
                      </span>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          disabled={group.page <= 0}
                          onClick={() =>
                            setGroupPages((prev) => ({
                              ...prev,
                              [group.connectorId]: Math.max(0, group.page - 1),
                            }))
                          }
                          className="px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40"
                        >
                          Previous
                        </button>
                        <button
                          type="button"
                          disabled={group.page >= groupTotalPages - 1}
                          onClick={() =>
                            setGroupPages((prev) => ({
                              ...prev,
                              [group.connectorId]: group.page + 1,
                            }))
                          }
                          className="px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <>
          <div className="bg-white rounded-lg border border-[#d9d5c5] shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-[#f9f7f0]">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Pipeline</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Run ID</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Source Event</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Status</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Dup</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Registry ID</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase">Last activity</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {ungroupedData.items.map((r) => {
                    const g = r.connector_name || nameById[r.connector_id] || r.connector_id;
                    return (
                      <tr key={r.run_id} className="hover:bg-[#faf8f2]">
                        <td className="px-4 py-3 text-sm text-gray-700 max-w-[140px] truncate" title={g}>
                          {g}
                        </td>
                        <td className="px-4 py-3 text-sm font-mono text-gray-700">{r.run_id.slice(0, 12)}…</td>
                        <td className="px-4 py-3 text-sm text-gray-600 max-w-xs truncate">{r.source_event_id || "—"}</td>
                        <td className="px-4 py-3 text-sm">
                          <RunStatusBadge status={r.status} />
                        </td>
                        <td className="px-4 py-3 text-sm">
                          {r.redelivery_count > 0 ? (
                            <span className="inline-flex px-1.5 py-0.5 rounded text-xs font-medium bg-amber-100 text-amber-900">
                              ×{r.redelivery_count}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className="px-4 py-3 text-sm font-mono text-xs text-gray-600">{r.registry_correlation_id || "—"}</td>
                        <td className="px-4 py-3 text-sm text-gray-500">{new Date(r.updated_at || r.created_at).toLocaleString()}</td>
                        <td className="px-4 py-3 text-sm">
                          <Link
                            to={`/pipelines/${r.connector_id}?tab=runs`}
                            className="inline-flex items-center gap-0.5 text-amber-800 hover:underline text-xs"
                          >
                            Pipeline <ChevronRight className="w-3 h-3" />
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
            <span>
              {ungroupedData.total === 0
                ? "0"
                : `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, ungroupedData.total)}`} of {ungroupedData.total}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                disabled={page <= 0}
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                className="px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1.5 border border-gray-300 rounded-md disabled:opacity-40"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function RunStatusBadge({ status }: { status: string }) {
  const colors: Record<string, string> = {
    SUCCESS: "bg-green-100 text-green-800",
    FAILED: "bg-red-100 text-red-800",
    IN_PROGRESS: "bg-blue-100 text-blue-800",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[status] || "bg-gray-100 text-gray-700"}`}>
      {status}
    </span>
  );
}
