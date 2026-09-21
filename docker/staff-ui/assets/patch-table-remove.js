#!/usr/bin/env node
/*
 * "Remove" on a table row that was never saved removes it.
 *
 * Both table widgets (the inline table and the dialog table) soft-delete on
 * Remove: the row is kept, marked edit_action DELETE and tinted with
 * --owt-widget-table-deleted-row-bg, which the theme resolves to #F3F1F4 --
 * indistinguishable from white. That is right for a row the server holds
 * (the DELETE must reach it on save) and meaningless for a row added in this
 * session and not yet saved: the enumerator clicks Remove and nothing
 * happens, and the row is only dropped later, silently, when the section
 * saves. Such a row -- one without a server-issued internal_record_id --
 * is now removed from the list at once; saved rows keep the soft delete,
 * which intake-form-fields.css makes visible (struck through, dimmed).
 * (edit_action is not the signal: the store still says "ADD" after the
 * section has been saved and the row re-read.)
 *
 * Patches the ui-widgets chunk in both the static and the server bundle
 * (same source, different minifier output is tolerated by matching the
 * identifiers). Exits non-zero unless both handlers are patched in at least
 * one static chunk.
 */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";
const ID = "[A-Za-z_$][A-Za-z0-9_$]*";

// DialogTableWidget.deleteRow:
//   q=(0,R.useCallback)(e=>{if(m){let t=[...c];t[e]={...t[e],edit_action:"DELETE"},a(t);return}a(c.filter((t,r)=>r!==e))},[c,a,m])
const DIALOG = new RegExp(
  `\\((${ID})=>\\{if\\((${ID})\\)\\{let (${ID})=\\[\\.\\.\\.(${ID})\\];\\3\\[\\1\\]=\\{\\.\\.\\.\\3\\[\\1\\],edit_action:"DELETE"\\},(${ID})\\(\\3\\);return\\}\\5\\(\\4\\.filter\\(`
);
// TableWidget.deleteRow:
//   ...,N){let t=[...g];t[e]={...t[e],edit_action:"DELETE"},a(t)}else{let t=g.filter((t,r)=>r!==e);a(t)}
const TABLE = new RegExp(
  `,(${ID})\\)\\{let (${ID})=\\[\\.\\.\\.(${ID})\\];\\2\\[(${ID})\\]=\\{\\.\\.\\.\\2\\[\\4\\],edit_action:"DELETE"\\},(${ID})\\(\\2\\)\\}else\\{let \\2=\\3\\.filter\\(`
);

function listJs(dir) {
  const out = [];
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listJs(full));
    else if (entry.name.endsWith(".js")) out.push(full);
  }
  return out;
}

let staticDialog = 0, staticTable = 0;
for (const file of [...listJs(path.join(ROOT, "static")), ...listJs(path.join(ROOT, "server"))]) {
  let s = fs.readFileSync(file, "utf8");
  let changed = false;
  const d = DIALOG.exec(s);
  if (d) {
    const [row, soft, , rows] = [d[1], d[2], d[3], d[4]];
    s = s.slice(0, d.index) + d[0].replace(`if(${soft}){`, `if(${soft}&&${rows}[${row}]?.internal_record_id){`) + s.slice(d.index + d[0].length);
    changed = true;
    if (!path.relative(ROOT, file).startsWith("server")) staticDialog += 1;
  }
  const t = TABLE.exec(s);
  if (t) {
    const [soft, , rows, row] = [t[1], t[2], t[3], t[4]];
    s = s.slice(0, t.index) + t[0].replace(`,${soft}){`, `,${soft}&&${rows}[${row}]?.internal_record_id){`) + s.slice(t.index + t[0].length);
    changed = true;
    if (!path.relative(ROOT, file).startsWith("server")) staticTable += 1;
  }
  if (changed) {
    fs.writeFileSync(file, s);
    console.log("  patched " + path.relative(ROOT, file) + (d ? " [dialog-table]" : "") + (t ? " [table]" : ""));
  }
}

if (staticDialog < 1 || staticTable < 1) {
  console.error(`table-remove patch: dialog-table handler in ${staticDialog} static chunk(s), table handler in ${staticTable} - expected both`);
  process.exit(1);
}
console.log("Remove drops an unsaved row outright; saved rows keep the soft delete");
