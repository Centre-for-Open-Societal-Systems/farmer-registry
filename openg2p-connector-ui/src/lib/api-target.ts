/** Label for the Connector API the dev UI talks to (proxy or direct). */
export function connectorApiTargetLabel(): string {
  const direct = import.meta.env.VITE_CONNECTOR_API_BASE_URL
  if (direct !== undefined && String(direct).trim() !== "") {
    return String(direct).replace(/\/$/, "")
  }
  const proxy = import.meta.env.VITE_DEV_CONNECTOR_PROXY_TARGET
  if (proxy !== undefined && String(proxy).trim() !== "") {
    return `${String(proxy).replace(/\/$/, "")} (via Vite proxy)`
  }
  return "http://127.0.0.1:8050 (via Vite proxy)"
}

export function usesViteProxy(): boolean {
  const direct = import.meta.env.VITE_CONNECTOR_API_BASE_URL
  return direct === undefined || String(direct).trim() === ""
}
