// Isolated HTTP contracts used only by the dashboard hook rehearsal.
import { createServer } from "node:http"
import { DatabaseSync } from "node:sqlite"

const stores = Object.fromEntries(["keycloak", "iam", "kubernetes"].map(name => {
  const db = new DatabaseSync(":memory:")
  db.exec("CREATE TABLE documents (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
  return [name, db]
}))
const get = (store, key) => {
  const row = stores[store].prepare("SELECT value FROM documents WHERE key=?").get(key)
  return row ? JSON.parse(row.value) : null
}
const put = (store, key, value) => stores[store].prepare(
  "INSERT INTO documents VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
).run(key, JSON.stringify(value))
const count = (store, prefix) => stores[store].prepare("SELECT count(*) n FROM documents WHERE key LIKE ?").get(`${prefix}%`).n
const failures = new Map()
let brokenSmoke = false
let deniedCharts = 0
const clientId = process.env.FIXTURE_CLIENT_ID
const apiClientId = process.env.FIXTURE_API_CLIENT_ID
const port = 9137
const base = `http://127.0.0.1:${port}`
const adminToken = "fixture-admin-token"
const serviceToken = "fixture-service-token"

createServer(async (request, response) => {
  const url = new URL(request.url, base)
  const path = decodeURIComponent(url.pathname)
  const chunks = []
  for await (const chunk of request) chunks.push(chunk)
  const raw = Buffer.concat(chunks).toString()
  const json = raw && request.headers["content-type"]?.includes("json") ? JSON.parse(raw) : null
  const send = (status, data = {}) => {
    response.writeHead(status, { "Content-Type": "application/json" })
    response.end(status === 204 ? "" : JSON.stringify(data))
  }
  try {
    if (path === "/fixture/state") return send(200, {
      clients: count("keycloak", "client/"), roles: count("keycloak", "role/"),
      grants: count("keycloak", "grant/"), applications: count("iam", "application/"),
      secrets: count("kubernetes", "secret/"), deniedCharts,
    })
    if (path === "/fixture/control" && request.method === "POST") {
      if (json.fail) failures.set(json.fail, 1)
      if ("brokenSmoke" in json) brokenSmoke = json.brokenSmoke
      return send(200)
    }
    const key = `${request.method}:${path}`
    if (failures.get(key)) { failures.delete(key); return send(503, { error: "injected fixture failure" }) }
    if (path === "/ping" || path === "/health") return send(200, { status: "ok" })
    if (path === "/auth/get_login_providers") return send(200, { loginProviders: [{ id: "fixture" }] })
    if (path === "/auth/start_authentication_transaction") return send(200, {
      redirectUrl: `${base}/realms/staff/protocol/openid-connect/auth?client_id=iam-staff-ui&redirect_uri=https%3A%2F%2Fstaff-iam.example.test%2Fcallback`,
    })
    if (path.endsWith("/protocol/openid-connect/token")) {
      const form = new URLSearchParams(raw)
      if (path.includes("/master/") && form.get("password") === "fixture-admin-password") return send(200, { access_token: adminToken })
      const client = get("keycloak", `client/${form.get("client_id")}`)
      if (!client || form.get("client_secret") !== client.secret || !count("keycloak", "grant/")) return send(401)
      return send(200, { access_token: serviceToken })
    }
    if (request.headers["x-amz-target"]?.endsWith(".GetAuthorizationToken")) return send(200, {
      authorizationData: [{ authorizationToken: Buffer.from("AWS:fixture-ecr-password").toString("base64"),
        expiresAt: Date.now() / 1000 + 3600, proxyEndpoint: "https://123456789012.dkr.ecr.ap-south-1.amazonaws.com" }],
    })
    if (path.startsWith("/api/v1/namespaces/farmer/secrets/") && request.method === "PUT") {
      if (json.kind !== "Secret" || json.metadata.namespace !== "farmer" || !json.metadata.name.startsWith("farmer-registry-dashboard-")) return send(403)
      put("kubernetes", `secret/${json.metadata.name}`, json)
      return send(200, json)
    }
    if (path === "/user-access/staff_portal_applications" && request.method === "POST") {
      if (request.headers.authorization !== `Bearer ${serviceToken}` || json.application_mnemonic !== clientId) return send(403)
      put("iam", `application/${clientId}`, json)
      return send(200, { registered: true })
    }
    if (path.startsWith("/api/v1/charts/")) {
      if (brokenSmoke || request.headers.authorization !== `Bearer ${serviceToken}`) { deniedCharts++; return send(401) }
      return send(200, [{ count: 1 }])
    }
    const admin = "/admin/realms/staff"
    if (path.startsWith(admin)) {
      if (request.headers.authorization !== `Bearer ${adminToken}`) return send(401)
      const route = path.slice(admin.length)
      if (route === "/clients" && request.method === "GET") {
        const client = get("keycloak", `client/${url.searchParams.get("clientId")}`)
        return send(200, client ? [client] : [])
      }
      if (route === "/clients" && request.method === "POST") {
        if (![clientId, apiClientId].includes(json.clientId)) return send(403)
        put("keycloak", `client/${json.clientId}`, { ...json, id: json.clientId })
        return send(201)
      }
      const role = route.match(/^\/clients\/([^/]+)\/roles\/([^/]+)$/)
      if (role) { const value = get("keycloak", `role/${role[1]}/${role[2]}`); return send(value ? 200 : 404, value || {}) }
      const roles = route.match(/^\/clients\/([^/]+)\/roles$/)
      if (roles && request.method === "POST") {
        put("keycloak", `role/${roles[1]}/${json.name}`, { ...json, id: `${roles[1]}:${json.name}` })
        return send(201)
      }
      const service = route.match(/^\/clients\/([^/]+)\/service-account-user$/)
      if (service) return send(200, { id: `service-${service[1]}` })
      const grant = route.match(/^\/users\/([^/]+)\/role-mappings\/clients\/([^/]+)$/)
      if (grant && request.method === "POST") {
        if (grant[1] !== `service-${clientId}` || grant[2] !== apiClientId) return send(403)
        for (const value of json) put("keycloak", `grant/${grant[1]}/${grant[2]}/${value.name}`, value)
        return send(204)
      }
      const client = route.match(/^\/clients\/([^/]+)$/)
      if (client && request.method === "PUT") { put("keycloak", `client/${client[1]}`, json); return send(204) }
    }
    send(501, { error: "Unmodeled rehearsal contract" })
  } catch { send(500, { error: "Fixture contract rejected request" }) }
}).listen(port, "127.0.0.1")
