import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

/** Dev-only: same-origin API paths → Connector API (avoids CORS). */
const connectorApiTarget =
  process.env.VITE_DEV_CONNECTOR_PROXY_TARGET ?? 'http://127.0.0.1:8050'
const proxySecure = connectorApiTarget.startsWith('https://')

const proxyOpts = {
  target: connectorApiTarget,
  changeOrigin: true,
  secure: proxySecure,
  configure: (proxy: any) => {
    proxy.on('error', (err: any, _req: any, res: any) => {
      console.error(
        `[vite] Connector API proxy failed (${connectorApiTarget}):`,
        err?.message ?? String(err)
      )
      if (res && 'writeHead' in res && !res.headersSent) {
        res.writeHead(502, { 'Content-Type': 'application/json' })
        res.end(
          JSON.stringify({
            detail: `Cannot reach ${connectorApiTarget}. Connect WireGuard (UD/EDRMC) or run npm run dev:local.`,
          })
        )
      }
    })
  },
}

const proxiedPaths = [
  '/connectors',
  '/runs',
  '/dlq',
  '/metadata',
  '/health',
  '/webhook',
] as const

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: Object.fromEntries(
      proxiedPaths.map((path) => [path, proxyOpts])
    ),
  },
})
