#!/usr/bin/env node
/*
 * Render an empty field as empty, not as "-".
 *
 * Every read-only widget in the platform's widget library substitutes a dash
 * for a missing value: the record header's Status Reason / Created by rows
 * (`children:b||"-"`), text and textarea displays (`p()||"-"`), select and
 * multi-select displays (`return eO.jsx("span",{children:"-"})`), dates
 * (`r=t?...:"-"`), table cells (`null==r||""===r?"-":...`) and so on. There is
 * no option to switch it off, so the fallbacks are rewritten to "" here.
 *
 * The same chunk also uses the literal "-" for things that are not
 * placeholders and must keep working:
 *
 *   startsWith("-") / (e?"-":"")+l       sign handling in the number formatter
 *   "-"===t, ("-"===e||"−"===e)          a typed minus in the numeric input
 *   void g("-")                          keeping that minus in the input
 *   e+"-"+r                              id generation
 *
 * so instead of a blanket replace the script walks each occurrence and skips
 * any that sits next to a comparison, a concatenation, a call argument, or the
 * sign formatter. Everything left is a display fallback.
 *
 * The widget library is a client module emitted into both a static chunk and a
 * server chunk; both are patched, otherwise the server-rendered HTML would
 * still carry the dash and hydration would flag a mismatch. Exits non-zero if
 * fewer than two bundles match or a bundle still contains a display fallback
 * afterwards, so a base-image change fails the build rather than silently
 * bringing the dashes back.
 */
const fs = require("fs");
const path = require("path");

const ROOT = "/app/.next";
// Present only in the widget library: the record header's field rows.
const MARKER = "hdr-field-value";
const LITERAL = '"-"';

function listJs(dir) {
  const out = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) out.push(...listJs(full));
    else if (entry.name.endsWith(".js")) out.push(full);
  }
  return out;
}

// True when the "-" at `at` is not a display placeholder.
function keep(src, at) {
  const before = src.slice(Math.max(0, at - 12), at);
  const after = src.slice(at + LITERAL.length, at + LITERAL.length + 6);
  return (
    /===$/.test(before) || /^===/.test(after) || // "-"===t / t==="-"
    /\+$/.test(before) || /^\+/.test(after) ||   // e+"-"+r
    /\($/.test(before) && /^\)/.test(after) ||   // g("-"), startsWith("-")
    /\?$/.test(before) && /^:""\)/.test(after)   // (e?"-":"")+l sign prefix
  );
}

function patch(src) {
  let out = "";
  let last = 0;
  let replaced = 0;
  let at = src.indexOf(LITERAL);
  while (at !== -1) {
    out += src.slice(last, at);
    if (keep(src, at)) {
      out += LITERAL;
    } else {
      out += '""';
      replaced++;
    }
    last = at + LITERAL.length;
    at = src.indexOf(LITERAL, last);
  }
  return { src: out + src.slice(last), replaced };
}

let patched = 0;
for (const file of listJs(ROOT)) {
  const src = fs.readFileSync(file, "utf8");
  if (!src.includes(MARKER)) continue;
  const result = patch(src);
  if (result.replaced === 0) continue;
  // The header rows are the one fallback every version of the widget has had;
  // if it is still there the walk above missed the shape this build uses.
  if (/(?:children|title):\w+\|\|"-"/.test(result.src)) {
    console.error("empty-value dash: a header fallback survived in " + file);
    process.exit(1);
  }
  fs.writeFileSync(file, result.src);
  patched++;
  console.log(
    `  patched ${file.replace(ROOT + "/", "")} (${result.replaced} placeholder(s))`
  );
}

if (patched < 2) {
  console.error(
    `empty-value dash: expected a static and a server bundle containing "${MARKER}", patched ${patched}`
  );
  process.exit(1);
}
console.log(`removed the "-" empty-value placeholder in ${patched} bundle(s)`);
