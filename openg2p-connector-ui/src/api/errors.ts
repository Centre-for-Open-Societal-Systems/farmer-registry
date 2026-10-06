/** Map browser/network errors to actionable text for the Connector UI. */
export function formatApiError(e: unknown): string {
  const msg = e instanceof Error ? e.message : String(e);
  if (msg === "Failed to fetch" || msg.includes("NetworkError")) {
    const target =
      import.meta.env.VITE_DEV_CONNECTOR_PROXY_TARGET ||
      "http://127.0.0.1:8050"
    const isRemote = String(target).startsWith("https://")
    return (
      "Cannot reach Connector API. " +
      (isRemote
        ? `Proxy target is ${target} — connect the UD (or EDRMC) WireGuard tunnel, confirm curl ${target}/health, then restart npm run dev. `
        : "Leave VITE_CONNECTOR_API_BASE_URL empty so Vite proxies API calls (no CORS). Start the Connector API on port 8050 and restart npm run dev. ") +
      "For local API only: npm run dev:local. " +
      "If you set VITE_CONNECTOR_API_BASE_URL to a full URL, also set CONNECTOR_CORS_ORIGINS on the API."
    )
  }
  return msg;
} 
