// Staff login in front of the published connector UI (see Dockerfile).
import Keycloak from "./keycloak.js";

const entry = document.querySelector('meta[name="oan-admin-entry"]').content;

function stop(message, keycloak) {
  const root = document.getElementById("root");
  root.innerHTML = "";
  const box = document.createElement("div");
  box.style.cssText = "max-width:32rem;margin:6rem auto;padding:1.5rem;background:#fff;border-radius:8px;font:15px system-ui";
  box.textContent = message;
  if (keycloak) {
    const out = document.createElement("button");
    out.textContent = "Sign out";
    out.style.cssText = "display:block;margin-top:1rem;padding:.4rem 1rem";
    out.onclick = () => keycloak.logout({ redirectUri: location.origin + "/" });
    box.appendChild(out);
  }
  root.appendChild(box);
}

const config = await fetch("/metadata/admin-auth", { cache: "no-store" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
if (!config || !config.configured) {
  stop("Connector administration is unavailable: staff login is not configured.");
} else {
  const keycloak = new Keycloak({ url: config.url, realm: config.realm, clientId: config.clientId });
  await keycloak.init({ onLoad: "login-required", pkceMethod: "S256", checkLoginIframe: false });
  const roles = keycloak.tokenParsed?.resource_access?.[config.roleClientId]?.roles ?? [];
  if (!roles.includes(config.role)) {
    stop(`Signed in as ${keycloak.tokenParsed?.preferred_username ?? "unknown"}, who does not have the ${config.role} role.`, keycloak);
  } else {
    const send = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
      const url = new URL(input instanceof Request ? input.url : String(input), location.href);
      if (url.origin !== location.origin) return send(input, init);
      await keycloak.updateToken(30).catch(() => keycloak.login());
      const headers = new Headers(init.headers ?? (input instanceof Request ? input.headers : undefined));
      headers.set("Authorization", `Bearer ${keycloak.token}`);
      return send(input, { ...init, headers });
    };
    await import(entry);
  }
}
