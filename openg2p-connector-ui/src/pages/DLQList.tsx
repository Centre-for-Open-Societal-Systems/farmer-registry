import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, ChevronRight, ExternalLink, RefreshCw, RotateCcw } from "lucide-react";
import { api } from "../api/client";
import { formatApiError } from "../api/errors";
import type { Connector, DLQEntry, DLQPage } from "../api/types";

const ERROR_CATEGORIES = ["transient", "permanent", "validation", "config"] as const;
const PAGE_SIZE = 25;
type DLQGroup = {
  connectorId: string;
  connectorName: string;
  items: DLQEntry[];
  total: number;
  page: number;
};

export default function DLQList() {
  const [data, setData] = useState<DLQPage | null>(null);
  const [groupedDLQ, setGroupedDLQ] = useState<DLQGroup[]>([]);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [replaying, setReplaying] = useState<Set<string>>(new Set());
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const [page, setPage] = useState(0);
  const [groupPages, setGroupPages] = useState<Record<string, number>>({});
  const [connectorFilter, setConnectorFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [q, setQ] = useState("");
  const [qApplied, setQApplied] = useState("");
  const [groupByConnector, setGroupByConnector] = useState(true);
  const isGroupedMode = groupByConnector && !connectorFilter;

  const entries = isGroupedMode
    ? groupedDLQ.flatMap((g) => g.items)
    : (data?.items ?? []);

  const connectorNameById = useMemo(() => {
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
            const dlq = await api.listDLQ({
              connectorId: connector.connector_id,
              errorCategory: categoryFilter || undefined,
              q: qApplied || undefined,
              offset: groupPage * PAGE_SIZE,
              limit: PAGE_SIZE,
              orderBy: "time",
            });
            return {
              connectorId: connector.connector_id,
              connectorName: connector.name,
              items: dlq.items,
              total: dlq.total,
              page: groupPage,
            } satisfies DLQGroup;
          })
        );
        const nonEmpty = groups.filter((g) => g.total > 0).sort((a, b) => a.connectorName.localeCompare(b.connectorName));
        setGroupedDLQ(nonEmpty);
        setData({ items: [], total: nonEmpty.reduce((acc, g) => acc + g.total, 0) });
        setExpandedGroups((prev) => {
          const next = new Set(prev);
          for (const g of nonEmpty) {
            if (!next.has(g.connectorId)) next.add(g.connectorId);
          }
          return next;
        });
        const visibleIds = new Set(nonEmpty.flatMap((g) => g.items.map((e) => e.dl_id)));
        setSelected((prev) => {
          const next = new Set<string>();
          for (const id of prev) if (visibleIds.has(id)) next.add(id);
          return next;
        });
        return;
      }

      const dlq = await api.listDLQ({
        connectorId: connectorFilter || undefined,
        errorCategory: categoryFilter || undefined,
        q: qApplied || undefined,
        offset: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        orderBy: groupByConnector ? "connector" : "time",
      });
      setData(dlq);
      setGroupedDLQ([]);
      setSelected((prev) => {
        const next = new Set<string>();
        for (const e of dlq.items) if (prev.has(e.dl_id)) next.add(e.dl_id);
        return next;
      });
    } catch (e: unknown) {
      setError(formatApiError(e));
    } finally {
      setLoading(false);
    }
  }, [connectorFilter, categoryFilter, qApplied, page, groupByConnector, isGroupedMode, connectors, groupPages]);

  useEffect(() => {
    load();
  }, [load]);

  const applySearch = () => {
    setPage(0);
    setGroupPages({});
    setQApplied(q.trim());
  };

  const toggleExpand = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    const visibleIds = entries.map((e) => e.dl_id);
    setSelected((prev) =>
      visibleIds.every((id) => prev.has(id)) ? new Set() : new Set(visibleIds)
    );
  };

  const replay = async (dlIds: string[]) => {
    if (dlIds.length === 0) return;
    setReplaying((prev) => {
      const next = new Set(prev);
      dlIds.forEach((id) => next.add(id));
      return next;
    });
    try {
      await api.replayDLQ(dlIds);
      load();
    } catch (e: unknown) {
      setError(formatApiError(e));
    } finally {
      setReplaying((prev) => {
        const next = new Set(prev);
        dlIds.forEach((id) => next.delete(id));
        return next;
      });
    }
  };

  const selectedCount = selected.size;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const totalEntries = isGroupedMode
    ? groupedDLQ.reduce((acc, g) => acc + g.total, 0)
    : data?.total ?? 0;

  return (
    <div>
      <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Dead Letter Queue</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {totalEntries} total · {isGroupedMode ? "grouped by pipeline" : `page ${page + 1} of ${totalPages}`} · {selectedCount} selected on this page
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => replay(Array.from(selected))}
            disabled={selectedCount === 0 || replaying.size > 0}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-amber-900 bg-amber-100 border border-amber-300 rounded-md hover:bg-amber-200 disabled:opacity-40 disabled:cursor-not-allowed"
            title="Replay all selected entries"
          >
            <RotateCcw className="w-4 h-4" />
            Replay selected{selectedCount > 0 ? ` (${selectedCount})` : ""}
          </button>
          <button
            onClick={load}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>
      </div>

      <div className="mb-4 bg-white rounded-lg border border-[#d9d5c5] p-4 flex flex-col gap-3">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Connector</label>
            <select
              value={connectorFilter}
              onChange={(e) => {
                setConnectorFilter(e.target.value);
                setPage(0);
                setGroupPages({});
              }}
              className="min-w-[240px] px-3 py-2 text-sm border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="">All connectors</option>
              {connectors.map((c) => (
                <option key={c.connector_id} value={c.connector_id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Error category</label>
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(0);
                setGroupPages({});
              }}
              className="min-w-[160px] px-3 py-2 text-sm border border-gray-300 rounded-md bg-white focus:outline-none focus:ring-2 focus:ring-amber-500"
            >
              <option value="">All categories</option>
              {ERROR_CATEGORIES.map((cat) => (
                <option key={cat} value={cat}>
                  {cat}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">Search</label>
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && applySearch()}
              className="min-w-[200px] px-3 py-2 text-sm border border-gray-300 rounded-md"
              placeholder="dl id, event, error text…"
            />
          </div>
          <button
            type="button"
            onClick={applySearch}
            className="px-3 py-2 text-sm bg-amber-700 text-white rounded-md hover:bg-amber-800"
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
      ) : totalEntries === 0 ? (
        <div className="text-center py-16 text-gray-500">No dead-letter entries.</div>
      ) : isGroupedMode ? (
        <div className="space-y-3">
          {groupedDLQ.map((group) => {
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
                    {group.total} entries
                    {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                  </span>
                </button>

                {isOpen && (
                  <div className="p-3 space-y-3">
                    <div className="overflow-x-auto">
                      <table className="min-w-full divide-y divide-gray-200">
                        <thead className="bg-[#f9f7f0]">
                          <tr>
                            <th className="px-3 py-3 w-10"></th>
                            <th className="w-10"></th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">ID</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Category</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Error</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Attempts</th>
                            <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Created</th>
                            <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">Action</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {group.items.map((e) => {
                            const isOpenRow = expandedRows.has(e.dl_id);
                            return (
                              <Fragment key={e.dl_id}>
                                <tr className="hover:bg-[#faf8f2]">
                                  <td className="px-3 py-3">
                                    <input
                                      type="checkbox"
                                      checked={selected.has(e.dl_id)}
                                      onChange={() => toggleSelect(e.dl_id)}
                                      className="rounded border-gray-300"
                                    />
                                  </td>
                                  <td className="px-2 py-3">
                                    <button
                                      onClick={() => toggleExpand(e.dl_id)}
                                      className="text-gray-500 hover:text-gray-800"
                                      aria-label={isOpenRow ? "Collapse" : "Expand"}
                                    >
                                      {isOpenRow ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                                    </button>
                                  </td>
                                  <td className="px-4 py-3 text-sm font-mono text-gray-700" title={e.dl_id}>
                                    {e.dl_id.slice(0, 12)}…
                                  </td>
                                  <td className="px-4 py-3 text-sm">
                                    <CategoryBadge category={e.error_category} />
                                  </td>
                                  <td className="px-4 py-3 text-sm text-red-600 max-w-xs truncate" title={e.error || undefined}>
                                    {e.error || "—"}
                                  </td>
                                  <td className="px-4 py-3 text-sm text-gray-600">{e.attempt_count}</td>
                                  <td className="px-4 py-3 text-sm text-gray-500">{new Date(e.created_at).toLocaleString()}</td>
                                  <td className="px-4 py-3 text-sm text-right">
                                    <button
                                      onClick={() => replay([e.dl_id])}
                                      disabled={replaying.has(e.dl_id)}
                                      className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-amber-800 bg-amber-50 border border-amber-200 rounded hover:bg-amber-100 disabled:opacity-50"
                                    >
                                      <RotateCcw className="w-3 h-3" />
                                      Replay
                                    </button>
                                  </td>
                                </tr>
                                {isOpenRow && (
                                  <tr className="bg-[#faf8f2]">
                                    <td colSpan={8} className="px-6 py-4">
                                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                        <div>
                                          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Metadata</div>
                                          <dl className="text-sm space-y-1">
                                            <div className="flex gap-2">
                                              <dt className="text-gray-500 w-36">DL ID</dt>
                                              <dd className="font-mono break-all">{e.dl_id}</dd>
                                            </div>
                                            <div className="flex gap-2">
                                              <dt className="text-gray-500 w-36">Connector ID</dt>
                                              <dd className="font-mono break-all">{e.connector_id}</dd>
                                            </div>
                                            <div className="flex gap-2">
                                              <dt className="text-gray-500 w-36">Source event ID</dt>
                                              <dd className="font-mono break-all">{e.source_event_id || "—"}</dd>
                                            </div>
                                          </dl>
                                          <div className="mt-3 text-xs">
                                            <Link
                                              to={`/pipelines/${e.connector_id}?tab=dlq`}
                                              className="inline-flex items-center gap-1 text-amber-800 hover:text-amber-900 hover:underline"
                                            >
                                              Open pipeline
                                              <ExternalLink className="w-3 h-3" />
                                            </Link>
                                          </div>
                                          {e.error && (
                                            <div className="mt-3">
                                              <div className="text-xs font-medium text-red-600 uppercase tracking-wide mb-1">Error</div>
                                              <pre className="text-xs bg-red-50 border border-red-200 rounded p-2 whitespace-pre-wrap text-red-800">{e.error}</pre>
                                            </div>
                                          )}
                                        </div>
                                        <div>
                                          <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Payload</div>
                                          <pre className="text-xs bg-white border border-gray-200 rounded p-2 max-h-80 overflow-auto">
                                            {JSON.stringify(e.payload ?? {}, null, 2)}
                                          </pre>
                                        </div>
                                      </div>
                                    </td>
                                  </tr>
                                )}
                              </Fragment>
                            );
                          })}
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
                    <th className="px-3 py-3 w-10">
                      <input
                        type="checkbox"
                        checked={selectedCount > 0 && selectedCount === entries.length}
                        onChange={toggleSelectAll}
                        className="rounded border-gray-300"
                      />
                    </th>
                    <th className="w-10"></th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">ID</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Connector</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Category</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Error</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Attempts</th>
                    <th className="px-4 py-3 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">Created</th>
                    <th className="px-4 py-3 text-right text-xs font-semibold text-gray-600 uppercase tracking-wider">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {entries.map((e) => {
                    const isOpen = expandedRows.has(e.dl_id);
                    const connectorName =
                      e.connector_name || connectorNameById[e.connector_id] || e.connector_id.slice(0, 12) + "…";
                    return (
                      <Fragment key={e.dl_id}>
                        <tr className="hover:bg-[#faf8f2]">
                          <td className="px-3 py-3">
                            <input
                              type="checkbox"
                              checked={selected.has(e.dl_id)}
                              onChange={() => toggleSelect(e.dl_id)}
                              className="rounded border-gray-300"
                            />
                          </td>
                          <td className="px-2 py-3">
                            <button
                              onClick={() => toggleExpand(e.dl_id)}
                              className="text-gray-500 hover:text-gray-800"
                              aria-label={isOpen ? "Collapse" : "Expand"}
                            >
                              {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                            </button>
                          </td>
                          <td className="px-4 py-3 text-sm font-mono text-gray-700" title={e.dl_id}>
                            {e.dl_id.slice(0, 12)}…
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-700">
                            <Link
                              to={`/pipelines/${e.connector_id}?tab=dlq`}
                              className="inline-flex items-center gap-1 text-amber-800 hover:text-amber-900 hover:underline"
                              title="Open pipeline details"
                            >
                              {connectorName}
                              <ExternalLink className="w-3 h-3" />
                            </Link>
                          </td>
                          <td className="px-4 py-3 text-sm">
                            <CategoryBadge category={e.error_category} />
                          </td>
                          <td className="px-4 py-3 text-sm text-red-600 max-w-xs truncate" title={e.error || undefined}>
                            {e.error || "—"}
                          </td>
                          <td className="px-4 py-3 text-sm text-gray-600">{e.attempt_count}</td>
                          <td className="px-4 py-3 text-sm text-gray-500">{new Date(e.created_at).toLocaleString()}</td>
                          <td className="px-4 py-3 text-sm text-right">
                            <button
                              onClick={() => replay([e.dl_id])}
                              disabled={replaying.has(e.dl_id)}
                              className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-amber-800 bg-amber-50 border border-amber-200 rounded hover:bg-amber-100 disabled:opacity-50"
                            >
                              <RotateCcw className="w-3 h-3" />
                              Replay
                            </button>
                          </td>
                        </tr>
                        {isOpen && (
                          <tr className="bg-[#faf8f2]">
                            <td colSpan={9} className="px-6 py-4">
                              <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                                <div>
                                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Metadata</div>
                                  <dl className="text-sm space-y-1">
                                    <div className="flex gap-2">
                                      <dt className="text-gray-500 w-36">DL ID</dt>
                                      <dd className="font-mono break-all">{e.dl_id}</dd>
                                    </div>
                                    <div className="flex gap-2">
                                      <dt className="text-gray-500 w-36">Connector ID</dt>
                                      <dd className="font-mono break-all">{e.connector_id}</dd>
                                    </div>
                                    <div className="flex gap-2">
                                      <dt className="text-gray-500 w-36">Source event ID</dt>
                                      <dd className="font-mono break-all">{e.source_event_id || "—"}</dd>
                                    </div>
                                  </dl>
                                  {e.error && (
                                    <div className="mt-3">
                                      <div className="text-xs font-medium text-red-600 uppercase tracking-wide mb-1">Error</div>
                                      <pre className="text-xs bg-red-50 border border-red-200 rounded p-2 whitespace-pre-wrap text-red-800">{e.error}</pre>
                                    </div>
                                  )}
                                </div>
                                <div>
                                  <div className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">Payload</div>
                                  <pre className="text-xs bg-white border border-gray-200 rounded p-2 max-h-80 overflow-auto">
                                    {JSON.stringify(e.payload ?? {}, null, 2)}
                                  </pre>
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div className="flex items-center justify-between mt-4 text-sm text-gray-600">
            <span>
              {data && data.total > 0
                ? `${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, data.total)} of ${data.total}`
                : "0"}
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

function CategoryBadge({ category }: { category: string | null }) {
  if (!category) return <span className="text-gray-400 text-xs">—</span>;
  const colors: Record<string, string> = {
    transient: "bg-yellow-100 text-yellow-800",
    permanent: "bg-red-100 text-red-800",
    validation: "bg-purple-100 text-purple-800",
    config: "bg-orange-100 text-orange-800",
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${colors[category] || "bg-gray-100 text-gray-700"}`}>
      {category}
    </span>
  );
}
