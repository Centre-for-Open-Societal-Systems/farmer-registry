#!/usr/bin/env node
/*
 * Load farmer-intake-rules.js on every portal page.
 *
 * The root layout is a server component (it only exists in a server chunk),
 * and its <head> holds one child, the branding <style>:
 *
 *     (0,d.jsx)("head",{children:(0,d.jsx)("style",{id:"branding-css-variables",...})})
 *
 * A <script defer src="/farmer-intake-rules.js?v=<hash>"> is added beside it.
 * Being part of the server-rendered tree, the same element is in the RSC
 * payload React hydrates against, so nothing mismatches. The hash of the
 * script's content is the cache key: a changed script gets a new URL, an
 * unchanged one keeps serving from cache. The portal's CSP allows same-origin
 * scripts (script-src 'self'), and /public files are served at the root.
 *
 * Exits non-zero unless exactly one layout is patched, so a base-image change
 * fails the build rather than silently dropping the intake behaviours.
 */
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";
const SCRIPT = process.env.STAFF_UI_PUBLIC_SCRIPT || "/app/public/farmer-intake-rules.js";
const ID = "[A-Za-z_$][A-Za-z0-9_$]*";

const HEAD = new RegExp(
  `\\(0,(${ID})\\.jsx\\)\\("head",\\{children:(\\(0,\\1\\.jsx\\)\\("style",\\{id:"branding-css-variables",[^{}]*\\{[^{}]*\\}\\}\\))\\}\\)`
);

function listJs(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listJs(full));
    else if (entry.name.endsWith(".js")) out.push(full);
  }
  return out;
}

const version = crypto.createHash("md5").update(fs.readFileSync(SCRIPT)).digest("hex").slice(0, 10);
const src = JSON.stringify(`/farmer-intake-rules.js?v=${version}`);

let patched = 0;
for (const file of listJs(path.join(ROOT, "server"))) {
  const before = fs.readFileSync(file, "utf8");
  if (!before.includes('"branding-css-variables"')) continue;
  const after = before.replace(HEAD, (_m, jsx, style) =>
    `(0,${jsx}.jsxs)("head",{children:[${style},(0,${jsx}.jsx)("script",{src:${src},defer:!0})]})`
  );
  if (after === before) continue;
  fs.writeFileSync(file, after);
  patched += 1;
  console.log("  patched " + path.relative(ROOT, file));
}

if (patched !== 1) {
  console.error(`intake-rules script patch matched ${patched} layout(s), expected 1 - the root layout's <head> changed`);
  process.exit(1);
}
console.log(`root layout loads ${src}`);
