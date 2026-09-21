#!/usr/bin/env node
/*
 * Readable errors when the server answers with something other than JSON.
 *
 * The portal's API helper (useApi's execute) does `await response.json()`
 * unconditionally. When a reverse proxy answers instead of the API -- the
 * 413 "Request Entity Too Large" page nginx returns for a certificate over
 * its body limit, a 502/504 while a pod restarts -- the body is HTML, the
 * parse throws, and the toast staff see is
 * "JSON.parse: unexpected character at line 1 column 1 of the JSON data",
 * which says nothing about what went wrong or what to do.
 *
 * Read the body as text first and parse it if it is JSON; if it is not,
 * synthesise the error shape the helper already understands ({statusText})
 * with a sentence: 413 says the file is too large, anything else names the
 * status. Everything downstream (toast, error state, null return) is
 * unchanged.
 *
 * Applies to every chunk that carries the hook: Next duplicates the module
 * into the home page chunk as well as the shared one, and the server bundle
 * holds a copy too (never runs a browser fetch, but patched alike so the
 * build-time check can assert the old shape is gone). Exits non-zero unless
 * a static chunk is patched.
 */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";
const ID = "[A-Za-z_$][A-Za-z0-9_$]*";

// let r=await t.json();if(!t.ok){
const BEFORE = new RegExp(`let (${ID})=await (${ID})\\.json\\(\\);if\\(!\\2\\.ok\\)\\{`);

function after(r, t) {
  return (
    `let ${r}=await ${t}.text();try{${r}=JSON.parse(${r})}catch(__e){${r}={statusText:` +
    `413===${t}.status?"The file is too large for the server to accept":` +
    `"The server returned "+${t}.status+" "+${t}.statusText}}if(!${t}.ok){`
  );
}

function listJs(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listJs(full));
    else if (entry.name.endsWith(".js")) out.push(full);
  }
  return out;
}

let patched = 0;
let staticPatched = 0;
for (const file of [...listJs(path.join(ROOT, "static")), ...listJs(path.join(ROOT, "server"))]) {
  const before = fs.readFileSync(file, "utf8");
  const m = BEFORE.exec(before);
  if (!m) continue;
  fs.writeFileSync(file, before.slice(0, m.index) + after(m[1], m[2]) + before.slice(m.index + m[0].length));
  patched += 1;
  if (!path.relative(ROOT, file).startsWith("server")) staticPatched += 1;
  console.log("  patched " + path.relative(ROOT, file));
}

if (staticPatched < 1) {
  console.error("api-error-messages patch matched no static chunk - has the API helper changed shape?");
  process.exit(1);
}
console.log(`non-JSON API responses toast a readable message in ${patched} bundle(s)`);
