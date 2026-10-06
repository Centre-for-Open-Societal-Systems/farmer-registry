import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { Save, ArrowLeft, Loader2 } from "lucide-react";
import { api } from "../api/client";
import { formatApiError } from "../api/errors";
import type {
  ConnectorMeta,
  ConnectorCreate,
  MetadataList,
} from "../api/types";
import Card from "../components/Card";
import { EDRMC_WEBSUB_UD } from "../lib/edrmc-websub-template";

const EMPTY: ConnectorCreate = {
  name: "",
  platform: "",
  transport_type: "",
  enabled: true,
  paused: false,
  data_model_mnemonic: "",
  mapper_expression: "",
  g2p_sender_id: "",
  g2p_register_mnemonic: "",
  source_config_json: "",
  auth_type: "none",
  auth_secret_json: "",
  webhook_secret: "",
  webhook_path_slug: "",
  webhook_verifier: "hmac_sha256",
  max_in_flight: null,
  validation_schema_json: "",
};

export default function PipelineForm() {
  const { id } = useParams<{ id: string }>();
  const isEdit = Boolean(id);
  const navigate = useNavigate();

  const [meta, setMeta] = useState<ConnectorMeta | null>(null);
  const [partners, setPartners] = useState<MetadataList | null>(null);
  const [registers, setRegisters] = useState<MetadataList | null>(null);
  const [form, setForm] = useState<ConnectorCreate>({ ...EMPTY });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        // Run metadata calls in parallel; metadata failures shouldn't block form load.
        const [m, pRes, rRes] = await Promise.all([
          api.meta(),
          api.listPartners().catch(() => ({ configured: false, items: [] })),
          api.listRegisters().catch(() => ({ configured: false, items: [] })),
        ]);
        setMeta(m);
        setPartners(pRes);
        setRegisters(rRes);
        if (id) {
          const c = await api.getConnector(id);
          setForm({
            name: c.name,
            platform: c.platform,
            transport_type: c.transport_type,
            enabled: c.enabled,
            paused: c.paused,
            data_model_mnemonic: c.data_model_mnemonic || "",
            mapper_expression: c.mapper_expression || "",
            g2p_sender_id: c.g2p_sender_id || "",
            g2p_register_mnemonic: c.g2p_register_mnemonic || "",
            source_config_json: c.source_config_json || "",
            auth_type: c.auth_type,
            auth_secret_json: "",
            webhook_secret: "",
            webhook_path_slug: c.webhook_path_slug || "",
            webhook_verifier: c.webhook_verifier,
            max_in_flight: c.max_in_flight,
            validation_schema_json: c.validation_schema_json || "",
          });
        }
      } catch (e: unknown) {
        setError(formatApiError(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const set = <K extends keyof ConnectorCreate>(key: K, val: ConnectorCreate[K]) =>
    setForm((prev) => ({ ...prev, [key]: val }));

  const transportHint = meta?.transport_hints[form.transport_type] || "";
  const isWebhook = transportHint === "webhook";
  const isPoll = transportHint === "poll";
  const isConsumer = transportHint === "consumer";
  const isWebSub = form.transport_type === "websub";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const payload = { ...form };
      if (!payload.auth_secret_json) delete payload.auth_secret_json;
      if (!payload.webhook_secret) delete payload.webhook_secret;
      if (!payload.source_config_json) delete payload.source_config_json;
      if (!payload.validation_schema_json) delete payload.validation_schema_json;
      if (!payload.mapper_expression) delete payload.mapper_expression;
      if (payload.max_in_flight === null || payload.max_in_flight === undefined) delete payload.max_in_flight;

      if (isEdit && id) {
        await api.updateConnector(id, payload);
      } else {
        await api.createConnector(payload as ConnectorCreate);
      }
      navigate("/");
    } catch (e: unknown) {
      setError(formatApiError(e));
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="text-center py-16 text-gray-500">Loading…</div>;

  return (
    <form onSubmit={handleSubmit} className="space-y-6 pb-24">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="p-2 rounded-md hover:bg-gray-100 text-gray-500"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-xl font-semibold text-gray-900">
            {isEdit ? "Edit Pipeline" : "New Pipeline"}
          </h1>
        </div>
        {!isEdit && (
          <button
            type="button"
            className="px-3 py-1.5 text-sm rounded-md border border-amber-300 bg-amber-50 text-amber-900 hover:bg-amber-100"
            onClick={() =>
              setForm({
                ...EMPTY,
                ...EDRMC_WEBSUB_UD,
                auth_secret_json: "",
                webhook_secret: "",
              })
            }
          >
            Apply EDRMC → UD WebSub template
          </button>
        )}
      </div>

      {error && (
        <div className="p-3 rounded-md bg-red-50 border border-red-200 text-red-700 text-sm">{error}</div>
      )}

      {/* Identity */}
      <Card title="Identity">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Name" required>
            <input
              required
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              className="input"
              placeholder="ODK Household Poll"
            />
          </Field>
          <Field label="Platform" required>
            <input
              required
              value={form.platform}
              onChange={(e) => set("platform", e.target.value)}
              className="input"
              placeholder="odk, generic, kafka_registry_events…"
            />
          </Field>
          <Field label="Transport Type" required>
            <select
              required
              value={form.transport_type}
              onChange={(e) => set("transport_type", e.target.value)}
              className="input"
            >
              <option value="">Select…</option>
              {meta?.transport_types.map((t) => (
                <option key={t} value={t}>
                  {t} ({meta.transport_hints[t] || "unknown"})
                </option>
              ))}
            </select>
          </Field>
          <Field label="Data Model Mnemonic">
            <input
              value={form.data_model_mnemonic || ""}
              onChange={(e) => set("data_model_mnemonic", e.target.value)}
              className="input"
              placeholder="ODK_HOUSEHOLD"
            />
          </Field>
        </div>
        <div className="flex gap-6 mt-4">
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={form.enabled}
              onChange={(e) => set("enabled", e.target.checked)}
              className="rounded border-gray-300 text-amber-700 focus:ring-amber-600"
            />
            Enabled
          </label>
          <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
            <input
              type="checkbox"
              checked={form.paused}
              onChange={(e) => set("paused", e.target.checked)}
              className="rounded border-gray-300 text-amber-700 focus:ring-amber-600"
            />
            Paused
          </label>
        </div>
      </Card>

      {/* Registry delivery (G2P envelope) */}
      <Card
        title="Registry Delivery"
        subtitle="Required — fields the Partner API reads from the G2P envelope. Field-level mapping (e.g. flattening nested names) happens in the registry transformer, not here."
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field
            label="Sender (Partner Mnemonic)"
            required
            hint={
              partners?.configured === false
                ? "Metadata DSN not set — type a mnemonic manually."
                : "Must match an active partner in the registry."
            }
          >
            <MetadataSelectOrInput
              value={form.g2p_sender_id}
              onChange={(v) => set("g2p_sender_id", v)}
              source={partners}
              placeholder="test-partner"
              required
            />
          </Field>
          <Field
            label="Target Register"
            required
            hint={
              registers?.configured === false
                ? "Metadata DSN not set — type a register mnemonic manually."
                : "Determines which incoming_model_semantic_pattern matches."
            }
          >
            <MetadataSelectOrInput
              value={form.g2p_register_mnemonic}
              onChange={(v) => set("g2p_register_mnemonic", v)}
              source={registers}
              placeholder="farmer_register"
              required
            />
          </Field>
        </div>
      </Card>

      {/* Source Configuration */}
      {(isPoll || isConsumer || isWebhook) && (
        <Card title="Source Configuration">
          <Field
            label="Source Config (JSON)"
            hint={
              isWebSub
                ? "hub_url, partner_id, callback_url, topics, data_path"
                : "base_url, poll_interval_seconds, project_id, form_id, topic, bootstrap_servers, etc."
            }
          >
            <textarea
              value={form.source_config_json || ""}
              onChange={(e) => set("source_config_json", e.target.value)}
              className="input font-mono text-sm"
              rows={6}
              placeholder={
                isWebSub
                  ? '{"hub_url": "https://websub.example.org/hub", "topics": ["partner/WEBSUB_INDIVIDUAL_CREATED"]}'
                  : '{"base_url": "https://odk.example.com", "project_id": 1, "form_id": "household"}'
              }
            />
          </Field>
        </Card>
      )}

      {/* Auth */}
      <Card title="Authentication">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Auth Type">
            <select
              value={form.auth_type}
              onChange={(e) => set("auth_type", e.target.value)}
              className="input"
            >
              {meta?.auth_types.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
          </Field>
          {form.auth_type !== "none" && (
            <Field label="Auth Secrets (JSON)" hint={isEdit ? "Leave blank to keep existing" : "token_url, client_id, client_secret, email, password…"}>
              <textarea
                value={form.auth_secret_json || ""}
                onChange={(e) => set("auth_secret_json", e.target.value)}
                className="input font-mono text-sm"
                rows={4}
                placeholder='{"email": "admin@example.com", "password": "***"}'
              />
            </Field>
          )}
        </div>
      </Card>

      {/* Webhook */}
      {isWebhook && (
        <Card title={isWebSub ? "WebSub Callback" : "Webhook"}>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Field
              label="Path Slug"
              hint={
                isWebSub
                  ? "Hub callback alias, e.g. /webhook/by-slug/edrmc-websub"
                  : "Human-friendly URL alias (optional)"
              }
            >
              <input
                value={form.webhook_path_slug || ""}
                onChange={(e) => set("webhook_path_slug", e.target.value)}
                className="input"
                placeholder="odk-farm-survey-prod"
              />
            </Field>
            <Field label="Verifier">
              <select
                value={form.webhook_verifier}
                onChange={(e) => set("webhook_verifier", e.target.value)}
                className="input"
              >
                {meta?.webhook_verifiers.map((v) => (
                  <option key={v} value={v}>{v}</option>
                ))}
              </select>
            </Field>
            <Field label="Webhook Secret" hint={isEdit ? "Leave blank to keep existing" : "Shared secret for signature verification"}>
              <input
                type="password"
                value={form.webhook_secret || ""}
                onChange={(e) => set("webhook_secret", e.target.value)}
                className="input"
                placeholder="••••••••"
              />
            </Field>
          </div>
        </Card>
      )}

      {/* Mapping */}
      <Card title="Mapping">
        <Field label="Mapper Expression (JMESPath)" hint="Transform source record into DataModel shape; leave blank for passthrough">
          <textarea
            value={form.mapper_expression || ""}
            onChange={(e) => set("mapper_expression", e.target.value)}
            className="input font-mono text-sm"
            rows={4}
            placeholder="{name: outer.name, age: outer.age}"
          />
        </Field>
      </Card>

      {/* Advanced */}
      <Card title="Advanced">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Field label="Max In-Flight" hint="Bounded concurrency; leave empty for default">
            <input
              type="number"
              min={1}
              value={form.max_in_flight ?? ""}
              onChange={(e) => set("max_in_flight", e.target.value ? Number(e.target.value) : null)}
              className="input"
              placeholder="50"
            />
          </Field>
          <div /> {/* spacer */}
          <Field label="Validation Schema (JSON Schema)" hint="Optional; only applied when CONNECTOR_VALIDATE_MAPPED_PAYLOAD=true">
            <textarea
              value={form.validation_schema_json || ""}
              onChange={(e) => set("validation_schema_json", e.target.value)}
              className="input font-mono text-sm"
              rows={4}
              placeholder='{"type": "object", "required": ["name"]}'
            />
          </Field>
        </div>
      </Card>

      {/* Sticky save bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3 flex justify-end gap-3">
          <button
            type="button"
            onClick={() => navigate("/")}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-md hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="inline-flex items-center gap-1.5 px-5 py-2 text-sm font-medium text-white bg-amber-700 rounded-md hover:bg-amber-800 disabled:opacity-50 transition-colors"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {isEdit ? "Save Changes" : "Create Pipeline"}
          </button>
        </div>
      </div>
    </form>
  );
}

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-gray-700">
        {label}
        {required && <span className="text-red-500 ml-0.5">*</span>}
      </span>
      {hint && <p className="text-xs text-gray-400 mt-0.5 mb-1">{hint}</p>}
      <div className="mt-1 [&_.input]:w-full [&_.input]:rounded-md [&_.input]:border [&_.input]:border-gray-300 [&_.input]:px-3 [&_.input]:py-2 [&_.input]:text-sm [&_.input]:shadow-sm [&_.input]:focus:border-amber-500 [&_.input]:focus:ring-1 [&_.input]:focus:ring-amber-500 [&_.input]:focus:outline-none">
        {children}
      </div>
    </label>
  );
}

/**
 * Preferred UI is a required <select> backed by the registry metadata
 * endpoint. When the DSN isn't configured (or the lookup fails) we degrade
 * to a plain text input so the operator isn't blocked locally, but
 * `required` ensures they must still supply something.
 */
function MetadataSelectOrInput({
  value,
  onChange,
  source,
  placeholder,
  required,
}: {
  value: string;
  onChange: (v: string) => void;
  source: MetadataList | null;
  placeholder: string;
  required?: boolean;
}) {
  const hasDropdown = !!source?.configured && (source?.items.length ?? 0) > 0;

  if (!hasDropdown) {
    return (
      <input
        required={required}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="input"
        placeholder={placeholder}
      />
    );
  }

  // When editing an existing connector with a value that's no longer in the
  // live list (deleted partner etc.), keep it selectable so we don't blank
  // the form silently.
  const items = source!.items;
  const knownValues = new Set(items.map((i) => i.value));
  const showStrayOption = value && !knownValues.has(value);

  return (
    <select
      required={required}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="input"
    >
      <option value="">Select…</option>
      {showStrayOption && (
        <option value={value}>{value} (not in registry)</option>
      )}
      {items.map((it) => (
        <option key={it.value} value={it.value}>
          {it.label}
        </option>
      ))}
    </select>
  );
}
