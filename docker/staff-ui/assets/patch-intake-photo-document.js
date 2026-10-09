#!/usr/bin/env node
/*
 * Upload every file picked during intake, record it on the record, and list it
 * with the submission's documents.
 *
 * From registry-platform 1.2.2 the widget library gathers a section's files
 * into SectionChanges.section_files, each tagged with where it came from and
 * the field it belongs to:
 *
 *   _profile        the picture in a header-section widget (the farmer photo)
 *   _direct_file    a file widget's file (the land certificate)
 *   _supporting_docs a section's supporting documents
 *
 * The intake save hook uploads only the _direct_file ones and lists them under
 * the submission's documents. It never uploads the _profile photo, so a photo
 * taken at intake never reached the server, and it never writes the uploaded
 * document_id back onto the record, so certificate_storage_id stayed blank (and
 * "Certificate Provided" stayed No) even though the file was uploaded.
 *
 * The hook's upload statement is replaced so that it:
 *  - uploads the _profile and _direct_file files (supporting documents keep
 *    the platform's own handling);
 *  - stamps each document_id onto the record: record_image_document_id for the
 *    photo, the widget's own field for a file. In a list section the record
 *    still holding the picked file gets it, else the first one with the field
 *    empty, so one file fills one row;
 *  - lists the photo under the submission's documents as "farmer_photo";
 *  - abandons the save with a message when an upload comes back empty (the API
 *    helper toasts the transport error and returns null, e.g. on the 413 a
 *    reverse proxy returns for a large certificate) instead of saving the
 *    section without the file and announcing success.
 *
 * The variable names are read off the minified statement rather than
 * hardcoded, and so is the toast binding (from the "section saved" toast in
 * the same function). Only the static (browser) chunk carries this statement:
 * a save happens in the browser. Exits non-zero unless it is patched once.
 */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";
const ID = "[A-Za-z_$][A-Za-z0-9_$]*";

const UPLOAD_FAILED =
  "The file could not be uploaded, so this section was not saved. Use a PDF, JPG, PNG or WebP up to 10 MB and try again.";

// let{filesToUpload:s,fileLabels:n}=(0,d.YX)(e?.section_files,"_direct_file"),
// l=void 0===s?[]:s,o=[];if(l.length>0){let e=await B(l);if(!e||0===e.length)return!1;o.push(...e)}
const UPLOAD = new RegExp(
  String.raw`let\{filesToUpload:(${ID}),fileLabels:(${ID})\}=\(0,(${ID})\.YX\)\((${ID})\?\.section_files,"_direct_file"\),` +
    String.raw`(${ID})=void 0===\1\?\[\]:\1,(${ID})=\[\];` +
    String.raw`if\(\5\.length>0\)\{let (${ID})=await (${ID})\(\5\);if\(!\7\|\|0===\7\.length\)return!1;\6\.push\(\.\.\.\7\)\}`
);
// a.oR.success(I("toast_section_saved_successfully")) -- the toast module binding.
const TOAST = new RegExp(`(${ID})\\.oR\\.success\\(${ID}\\("toast_section_saved_successfully"\\)\\)`);

function replacement(m, toast) {
  // The upload result gets its own name: the minifier reuses the changes
  // variable's name for it inside the block, which would shadow the records.
  const [, files, labels, util, changes, list, docs, , upload] = m;
  const up = "__up";
  const empty = (v) => `(null==${v}||""===${v})`;
  return (
    `let{filesToUpload:__fa,fileLabels:__fl,fileTargets:__ft}=(0,${util}.YX)(${changes}?.section_files),` +
    `__ix=(__ft||[]).map((t,i)=>t&&("_profile"===t.tag||"_direct_file"===t.tag)?i:-1).filter(i=>i>=0),` +
    `${files}=__ix.map(i=>__fa[i]),` +
    `${labels}=__ix.map(i=>"_profile"===__ft[i].tag?"farmer_photo":__fl[i]),` +
    `__tg=__ix.map(i=>__ft[i]),${list}=${files},${docs}=[];` +
    `if(${list}.length>0){let ${up}=await ${upload}(${list});` +
    `if(!${up}||${up}.length!==${list}.length||${up}.some(d=>!d||!d.document_id)){` +
    `${toast}.oR.error(${JSON.stringify(UPLOAD_FAILED)},{position:"top-right",autoClose:8e3});return!1}` +
    `${docs}.push(...${up});` +
    `let __rs=(${changes}.records||[]).map(r=>({...r}));` +
    `__tg.forEach((t,i)=>{let __id=${up}[i].document_id;` +
    `if("_profile"===t.tag){__rs.forEach(r=>{r.record_image_document_id=__id});return}` +
    `if(!t.field)return;` +
    `let __j=__rs.findIndex(r=>null!==r[t.field]&&"object"==typeof r[t.field]);` +
    `if(-1===__j)__j=__rs.findIndex(r=>${empty("r[t.field]")});` +
    `-1!==__j&&(__rs[__j][t.field]=__id)});` +
    `${changes}.records=__rs}`
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
for (const file of listJs(path.join(ROOT, "static"))) {
  const before = fs.readFileSync(file, "utf8");
  const m = UPLOAD.exec(before);
  if (!m) continue;
  const toast = TOAST.exec(before.slice(m.index));
  if (!toast) throw new Error(`${file}: intake upload found but the section-saved toast did not match`);
  const after = before.slice(0, m.index) + replacement(m, toast[1]) + before.slice(m.index + m[0].length);
  fs.writeFileSync(file, after);
  patched += 1;
  console.log("  patched " + path.relative(ROOT, file));
}

if (patched !== 1) {
  console.error(`intake-photo-document patch matched ${patched} static chunk(s), expected 1 - did the intake save hook change?`);
  process.exit(1);
}
console.log("intake photo and file uploads are recorded on the record and listed as documents");
