#!/usr/bin/env node
/*
 * "Remove" on a table row soft-deletes it exactly when the server holds it.
 *
 * Both table widgets (the inline table and the dialog table) soft-delete on
 * Remove: the row is kept and marked edit_action DELETE so the DELETE reaches
 * the server on save, which intake-form-fields.css makes visible (struck
 * through, dimmed). A row added in this session and never saved has nothing to
 * delete and is dropped from the list at once.
 *
 * From registry-platform 1.2.2 the widgets do that themselves, but they also
 * treat any row whose edit_action is still "ADD" as unsaved. The store keeps
 * "ADD" on a row after its section has been saved and re-read, so Remove on
 * such a row dropped it locally and no DELETE was ever sent: the row came back
 * on the next load. The server-issued internal_record_id alone decides here,
 * as it did before 1.2.2.
 *
 * Patches the ui-widgets chunk in the static and the server bundle. Exits
 * non-zero unless both handlers are patched in at least one static chunk.
 */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";
const ID = "[A-Za-z_$][A-Za-z0-9_$]*";

// TableWidget.deleteRow:
//   let t=g[e];if(t?.edit_action!=="ADD"&&"string"==typeof t?.internal_record_id&&...
const TABLE = new RegExp(`let (${ID})=(${ID})\\[(${ID})\\];if\\(\\1\\?\\.edit_action!=="ADD"&&"string"==typeof \\1\\?\\.internal_record_id`, "g");
// DialogTableWidget.deleteRow:
//   let t=c[e];if(t?.edit_action==="ADD"||!("string"==typeof t?.internal_record_id&&...
const DIALOG = new RegExp(`let (${ID})=(${ID})\\[(${ID})\\];if\\(\\1\\?\\.edit_action==="ADD"\\|\\|!\\("string"==typeof \\1\\?\\.internal_record_id`, "g");

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
  const before = fs.readFileSync(file, "utf8");
  if (!before.includes('edit_action:"DELETE"')) continue;
  let t = 0, d = 0;
  let s = before.replace(TABLE, (_m, row, rows, i) => {
    t += 1;
    return `let ${row}=${rows}[${i}];if("string"==typeof ${row}?.internal_record_id`;
  });
  s = s.replace(DIALOG, (_m, row, rows, i) => {
    d += 1;
    return `let ${row}=${rows}[${i}];if(!("string"==typeof ${row}?.internal_record_id`;
  });
  if (s === before) continue;
  fs.writeFileSync(file, s);
  const isStatic = !path.relative(ROOT, file).startsWith("server");
  if (isStatic) { staticTable += t; staticDialog += d; }
  console.log("  patched " + path.relative(ROOT, file) + (d ? " [dialog-table]" : "") + (t ? " [table]" : ""));
}

if (staticDialog < 1 || staticTable < 1) {
  console.error(`table-remove patch: dialog-table handler in ${staticDialog} static chunk(s), table handler in ${staticTable} - expected both`);
  process.exit(1);
}
console.log("Remove soft-deletes saved rows and drops unsaved ones; edit_action ADD no longer counts as unsaved");
