#!/usr/bin/env node
/*
 * Put Configuration and the language switch back in the header bar.
 *
 * The 1.2.x staff portal tucks both behind a "⋮" More button; the 1.1.x
 * portal showed them inline. The header's right-hand side is a fixed list:
 *
 *     (0,r.jsxs)("div",{className:"flex items-center gap-4",children:[
 *         (0,r.jsx)(m.default,{}),   // notifications
 *         (0,r.jsx)(u.default,{}),   // account
 *         (0,r.jsx)(f.default,{})    // "More" menu: Configuration + language
 *     ]})
 *
 * The 1.1.x inline components are still compiled into the same chunk, only
 * required for their side effects (`i(42158),i(29551);`): a Configuration
 * button that pushes /configuration/registry/details, and a language
 * dropdown that lists the registry languages. The More menu wraps
 * Configuration in the RBAC guard (`(0,r.jsx)(g.A,{anyOf:x.Ll,...})`), so the
 * inline button gets the same guard. The list becomes
 *
 *     [ guard(Configuration), language, notifications, account ]
 *
 * which is the 1.1.x order. Nothing is hardcoded by module id: each module
 * is found by what it renders (the config icon, the languages hook, the More
 * button's aria attributes) and the require function is read off the module
 * factory, so the same script patches the static chunk and the server chunk,
 * whose ids and local names differ. Both must be patched or the server HTML
 * would still carry the More button and hydration would flag a mismatch.
 * Exits non-zero if fewer than two bundles match, so a base-image change
 * fails the build instead of silently bringing the menu back.
 *
 * The required modules are bound at module scope, next to the header's own
 * imports, not required inline inside the component: the minified component
 * declares locals named e, t, i, ... that shadow the factory's require
 * parameter, so `i(60431)` inside the render is a call on an element
 * ("i is not a function" on every page).
 */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";

const ID = "[A-Za-z_$][A-Za-z0-9_$]*";

// Every webpack module in a chunk starts `<id>:(<module>,<exports>,<require>)=>{`.
const MODULE_START = new RegExp(`(\\d+):\\((${ID}),(${ID}),(${ID})\\)=>\\{`, "g");

// The header's right-hand list, exactly three parameterless components.
const HEADER_LIST = new RegExp(
  `\\(0,(${ID})\\.jsxs\\)\\("div",\\{className:"flex items-center gap-4",children:\\[` +
    `\\(0,\\1\\.jsx\\)\\((${ID})\\.default,\\{\\}\\),` +
    `\\(0,\\1\\.jsx\\)\\((${ID})\\.default,\\{\\}\\),` +
    `\\(0,\\1\\.jsx\\)\\((${ID})\\.default,\\{\\}\\)\\]\\}\\)`
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

// Split a chunk into its modules: [{id, requireName, start, end, body}].
function modules(src) {
  const starts = [];
  for (const m of src.matchAll(MODULE_START)) {
    starts.push({ id: m[1], requireName: m[4], start: m.index });
  }
  return starts.map((s, i) => {
    const end = i + 1 < starts.length ? starts[i + 1].start : src.length;
    return { ...s, end, body: src.slice(s.start, end) };
  });
}

function patch(src) {
  const mods = modules(src);
  const find = (pred, what) => {
    const hits = mods.filter(pred);
    if (hits.length !== 1) {
      throw new Error(`expected exactly one ${what} module, found ${hits.length}`);
    }
    return hits[0];
  };

  const more = find(
    (m) => m.body.includes('"aria-haspopup":"true"') && m.body.includes("config_icon.png"),
    "More-menu"
  );
  const config = find(
    (m) => m.body.includes("config_icon.png") && m.id !== more.id,
    "Configuration-button"
  );
  const language = find(
    (m) =>
      m.body.includes("languagesLoading") &&
      m.body.includes("rotate-180") &&
      m.id !== more.id,
    "language-dropdown"
  );

  // The guard and permission-set the More menu already applies to Configuration.
  const guardUse = more.body.match(new RegExp(`\\((${ID})\\.A,\\{anyOf:(${ID})\\.Ll,`));
  if (!guardUse) throw new Error("More-menu module: RBAC guard around Configuration not found");
  const moduleIdOf = (mod, local) => {
    const m = mod.body.match(new RegExp(`[,;\\s(]${local}=${mod.requireName}\\((\\d+)\\)`));
    if (!m) throw new Error(`module ${mod.id}: no require bound to ${local}`);
    return m[1];
  };
  const guardId = moduleIdOf(more, guardUse[1]);
  const permsId = moduleIdOf(more, guardUse[2]);

  const header = find((m) => HEADER_LIST.test(m.body), "header");
  const req = header.requireName;
  // Names no minifier emits, so they cannot collide with the module's locals.
  const G = "__farGuard", P = "__farPerms", C = "__farConfig", L = "__farLanguage";
  const useStrict = '"use strict";';
  const at = header.body.indexOf(useStrict);
  if (at < 0) throw new Error("header module: no \"use strict\" prologue to bind imports after");
  const bindings =
    `var ${G}=${req}(${guardId}),${P}=${req}(${permsId}),` +
    `${C}=${req}(${config.id}),${L}=${req}(${language.id});`;
  let body = header.body.slice(0, at + useStrict.length) + bindings + header.body.slice(at + useStrict.length);
  const before = body;
  body = body.replace(HEADER_LIST, (_m, jsx, notifications, account) => {
    const el = (expr, props) => `(0,${jsx}.jsx)(${expr},${props})`;
    const configuration = el(`${G}.A`, `{anyOf:${P}.Ll,children:${el(`${C}.default`, "{}")}}`);
    return (
      `(0,${jsx}.jsxs)("div",{className:"flex items-center gap-4",children:[` +
      configuration +
      `,${el(`${L}.default`, "{}")}` +
      `,${el(`${notifications}.default`, "{}")}` +
      `,${el(`${account}.default`, "{}")}]})`
    );
  });
  if (body === before) throw new Error("header module: list not rewritten");
  return src.slice(0, header.start) + body + src.slice(header.end);
}

let patched = 0;
for (const file of listJs(ROOT)) {
  const before = fs.readFileSync(file, "utf8");
  if (!before.includes("config_icon.png") || !HEADER_LIST.test(before)) continue;
  const after = patch(before);
  fs.writeFileSync(file, after);
  patched += 1;
  console.log("  patched " + path.relative(ROOT, file));
}

if (patched < 2) {
  console.error(
    `header-inline-controls patch matched ${patched} bundle(s), expected at least 2 ` +
      "(static + server) - the base image header changed, so Configuration and the " +
      "language switch would stay behind the More menu"
  );
  process.exit(1);
}
console.log(`header shows Configuration and the language switch inline in ${patched} bundle(s)`);
