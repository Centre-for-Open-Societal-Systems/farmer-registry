import type {
  Connector,
  ConnectorCreate,
  ConnectorUpdate,
  ConnectorMeta,
  ConnectorStats,
  IngestionRun,
  DLQEntry,
  DLQPage,
  MetadataList,
  PollNowResponse,
  RunsPage,
  WebSubSyncResponse,
} from "./types";

/**
 * Empty string = same-origin (Vite dev proxy to Connector API). Non-empty = direct URL (prod or custom).
 */
function apiBase(): string {
  const v = import.meta.env.VITE_CONNECTOR_API_BASE_URL
  if (v === undefined || v === '') return ''
  return String(v).replace(/\/$/, '')
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const BASE = apiBase()
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export type ListRunsParams = {
  connectorId?: string;
  q?: string;
  status?: string;
  offset?: number;
  limit?: number;
  includePayload?: boolean;
  sort?: "asc" | "desc";
  orderBy?: "time" | "connector";
  createdFrom?: string;
  createdTo?: string;
};

export type ListDLQParams = {
  connectorId?: string;
  errorCategory?: string;
  q?: string;
  offset?: number;
  limit?: number;
  sort?: "asc" | "desc";
  orderBy?: "time" | "connector";
  createdFrom?: string;
  createdTo?: string;
};

export const api = {
  meta: () => request<ConnectorMeta>("/connectors/meta"),

  listConnectors: () => request<Connector[]>("/connectors"),

  getConnector: (id: string) => request<Connector>(`/connectors/${id}`),

  createConnector: (data: ConnectorCreate) =>
    request<Connector>("/connectors", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateConnector: (id: string, data: ConnectorUpdate) =>
    request<Connector>(`/connectors/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),

  deleteConnector: (id: string) =>
    request<void>(`/connectors/${id}`, { method: "DELETE" }),

  getConnectorStats: (id: string) =>
    request<ConnectorStats>(`/connectors/${id}/stats`),

  pollNow: (id: string) =>
    request<PollNowResponse>(`/connectors/${id}/poll`, { method: "POST" }),

  resetCursor: (id: string) =>
    request<{ connector_id: string; poll_state: Record<string, unknown> }>(
      `/connectors/${id}/reset-cursor`,
      { method: "POST" }
    ),

  /** Remove dedupe keys so the same source_event_id can be processed again (testing / replay). */
  clearIdempotencyKeys: (id: string) =>
    request<{ connector_id: string; idempotency_keys_deleted: number }>(
      `/connectors/${id}/clear-idempotency`,
      { method: "POST" }
    ),

  /** Register + subscribe this connector’s callback URL at the WebSub hub (EDRMC, etc.). */
  websubSyncSubscriptions: (id: string) =>
    request<WebSubSyncResponse>(
      `/connectors/${id}/websub/sync-subscriptions`,
      { method: "POST" }
    ),

  listRuns: (params: ListRunsParams = {}) => {
    const p = new URLSearchParams();
    p.set("limit", String(params.limit ?? 50));
    p.set("offset", String(params.offset ?? 0));
    p.set("sort", params.sort ?? "desc");
    p.set("order_by", params.orderBy === "connector" ? "connector" : "time");
    if (params.connectorId) p.set("connector_id", params.connectorId);
    if (params.q) p.set("q", params.q);
    if (params.status) p.set("status", params.status);
    if (params.includePayload) p.set("include_payload", "true");
    if (params.createdFrom) p.set("created_from", params.createdFrom);
    if (params.createdTo) p.set("created_to", params.createdTo);
    return request<RunsPage>(`/runs?${p}`);
  },

  getRun: (runId: string, includePayload = true) =>
    request<IngestionRun>(
      `/runs/${runId}?include_payload=${includePayload ? "true" : "false"}`
    ),

  listDLQ: (params: ListDLQParams = {}) => {
    const p = new URLSearchParams();
    p.set("limit", String(params.limit ?? 50));
    p.set("offset", String(params.offset ?? 0));
    p.set("sort", params.sort ?? "desc");
    p.set("order_by", params.orderBy === "connector" ? "connector" : "time");
    if (params.connectorId) p.set("connector_id", params.connectorId);
    if (params.errorCategory) p.set("error_category", params.errorCategory);
    if (params.q) p.set("q", params.q);
    if (params.createdFrom) p.set("created_from", params.createdFrom);
    if (params.createdTo) p.set("created_to", params.createdTo);
    return request<DLQPage>(`/dlq?${p}`);
  },

  getDLQEntry: (dlId: string) => request<DLQEntry>(`/dlq/${dlId}`),

  replayDLQ: (dlIds: string[]) =>
    request<{ replayed: { dl_id: string; run_id?: string; status: string; error?: string }[] }>(
      "/dlq/replay",
      { method: "POST", body: JSON.stringify({ dl_ids: dlIds }) }
    ),

  listPartners: () => request<MetadataList>("/metadata/partners"),
  listRegisters: () => request<MetadataList>("/metadata/registers"),
};
