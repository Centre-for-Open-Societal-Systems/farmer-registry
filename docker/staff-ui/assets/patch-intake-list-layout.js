#!/usr/bin/env node
/*
 * Lay the intake-form list page out the way the 1.1.x portal (and the other
 * registries built on it, e.g. Crop Sown) do.
 *
 * 1.2.x hands the page to a combined list layout (`TF` in the commons module)
 * that puts the "Create New Submission +" dropdown top-right beside a "⋮"
 * card/table toggle, then a "Selected filters" bar carrying the search box,
 * then the cards. 1.1.x used the plain page header (`Vs`, still exported by
 * the same commons module) with the dropdown as its `capsule` beside the
 * title, search and pagination on the right, and the cards underneath.
 *
 * The page calls `(0,a.jsx)(c.TF,{...props})` once. Rather than rewrite that
 * prop list (the server copy inlines expressions in it), a small wrapper
 * component is hoisted into the page module and the call is pointed at it;
 * the wrapper renders `c.Vs` plus the card list from the same props. The
 * jsx-runtime and commons bindings it needs are the module-scope vars the
 * call already uses, read off the call itself.
 *
 * The dropdown component in the same module is restyled from a yellow button
 * with a "+" and a right-aligned menu to the 1.1.x select-like control: full
 * width of a w-100 wrapper, bordered, a down arrow, the menu opening flush
 * under it. Its label switches from create_new_submission to new_intake, a
 * key the 1.2.1 default catalog already carries. The open state (arrow
 * flipped, bottom border removed) is done in intake-list-header.css off the
 * menu's presence, since the button's class is memoised without the open flag.
 *
 * Both the static and the server copy of the page are patched, else the
 * server HTML would still carry the old layout and hydration would mismatch.
 * Exits non-zero unless both match, so a base-image change fails the build.
 */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";
const ID = "[A-Za-z_$][A-Za-z0-9_$]*";
const MARKER = 'viewStorageKey:"intakeFormView"';
const WRAPPER = "__farIntakeList";

function listJs(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listJs(full));
    else if (entry.name.endsWith(".js")) out.push(full);
  }
  return out;
}

// Replace exactly one occurrence, or fail loudly.
function once(src, from, to, what) {
  const re = from instanceof RegExp ? from : null;
  const count = re ? (src.match(re) || []).length : src.split(from).length - 1;
  if (count !== 1) throw new Error(`${what}: expected 1 match, found ${count}`);
  return re ? src.replace(re, to) : src.replace(from, to);
}

function wrapper(jsx, commons) {
  const el = (t, p) => `(0,${jsx}.jsx)(${t},${p})`;
  const header = el(
    `${commons}.Vs`,
    "{breadcrumb:e.breadcrumb,showFilters:!1,showPagination:e.showPagination," +
      "showCapsule:!0,capsule:e.actions,pageStart:e.pageStart,pageEnd:e.pageEnd," +
      "total:e.total,onPrev:e.onPrev,onNext:e.onNext,showSearch:!!e.showSearch," +
      "searchValue:e.searchValue,searchPlaceholder:e.searchPlaceholder,onSearch:e.onSearch}"
  );
  const list = el(
    '"div"',
    '{className:"px-7.5 mb-15",children:e.loading?' +
      el('"div"', '{className:"space-y-4",children:e.skeleton}') +
      ":e.items&&e.items.length?" +
      el('"div"', '{className:"space-y-4",children:e.items.map((t,r)=>e.renderCard(t,r))}') +
      ":e.emptyMessage}"
  );
  return (
    `function ${WRAPPER}(e){return (0,${jsx}.jsxs)("div",` +
    `{className:"min-h-screen bg-secondary-first",children:[${header},${list}]})}`
  );
}

function patch(src) {
  const at = src.indexOf(MARKER);
  const starts = [...src.slice(0, at).matchAll(new RegExp(`(\\d+):\\((${ID}),(${ID}),(${ID})\\)=>\\{"use strict";`, "g"))];
  if (!starts.length) throw new Error("no module prologue before the intake list call");
  const mod = starts[starts.length - 1];
  const prologueEnd = mod.index + mod[0].length;

  const call = src.match(new RegExp(`\\(0,(${ID})\\.jsx\\)\\((${ID})\\.TF,\\{`, "g"));
  if (!call || call.length !== 1) throw new Error(`expected one .TF call, found ${call ? call.length : 0}`);
  const [, jsx, commons] = call[0].match(new RegExp(`\\(0,(${ID})\\.jsx\\)\\((${ID})\\.TF,\\{`));

  let out = src.slice(0, prologueEnd) + wrapper(jsx, commons) + src.slice(prologueEnd);
  out = once(out, `(0,${jsx}.jsx)(${commons}.TF,{`, `(0,${jsx}.jsx)(${WRAPPER},{`, "list layout call");

  // The dropdown: select-styled control, menu flush underneath, 1.1.x label key.
  out = once(
    out,
    '"h-8.5 px-6 bg-primary-first rounded-[10px] flex items-center gap-2",title:',
    '"far-new-intake-btn w-full h-8.5 px-4 bg-neutral-second border border-primary-second rounded-[10px] flex items-center justify-between gap-2.5 truncate",title:',
    "dropdown button class"
  );
  out = once(
    out,
    new RegExp(`\\(0,${jsx}\\.jsx\\)\\("span",\\{className:"text-\\[20px\\] font-bold text-neutral-first leading-none",children:"\\+"\\}\\)`, "g"),
    `(0,${jsx}.jsx)("img",{src:"/images/common/down_arrow.png",alt:"",width:14,height:8,className:"far-new-intake-arrow shrink-0 transition-transform"})`,
    "dropdown plus glyph"
  );
  out = once(
    out,
    'className:"absolute right-0 top-full mt-1 w-100 bg-neutral-second border border-primary-second rounded-[10px] overflow-hidden z-50"',
    'className:"absolute left-0 top-full w-full bg-neutral-second border border-primary-second border-t-0 rounded-b-[10px] overflow-hidden z-50"',
    "dropdown menu class"
  );
  out = once(
    out,
    'className:"relative z-10",children:[',
    'className:"far-new-intake relative w-100 z-10",children:[',
    "dropdown wrapper class"
  );
  const labels = out.split('("create_new_submission")').length - 1;
  if (labels !== 2) throw new Error(`dropdown label: expected 2 uses of create_new_submission, found ${labels}`);
  out = out.split('("create_new_submission")').join('("new_intake")');
  return out;
}

let patched = 0;
for (const file of listJs(ROOT)) {
  const before = fs.readFileSync(file, "utf8");
  if (!before.includes(MARKER)) continue;
  fs.writeFileSync(file, patch(before));
  patched += 1;
  console.log("  patched " + path.relative(ROOT, file));
}

if (patched < 2) {
  console.error(
    `intake-list-layout patch matched ${patched} bundle(s), expected at least 2 ` +
      "(static + server) - the base image intake page changed, so the list would keep the 1.2.x layout"
  );
  process.exit(1);
}
console.log(`intake list uses the 1.1.x header layout in ${patched} bundle(s)`);
