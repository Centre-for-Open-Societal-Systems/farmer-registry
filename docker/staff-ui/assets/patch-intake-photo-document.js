#!/usr/bin/env node
/*
 * Record the file picked during intake on the record AND with the
 * submission's documents.
 *
 * The Dockerfile's "intake profile image upload" sed uploads the one File the
 * widget library pulls out of a section's records (SectionChanges.image) and
 * stamps its document_id onto every record as record_image_document_id. Two
 * things were missing:
 *
 *  - The library pulls out ANY File in the records, not just the farmer
 *    photo: a land certificate picked in the Lands dialog took the same path,
 *    so the land row's certificate_storage_id stayed blank (and "Certificate
 *    Provided" stayed No) while the file was silently uploaded as a profile
 *    image. When a record carries a blank *_storage_id field, the upload now
 *    goes there instead.
 *  - Nothing added the upload to the section's `documents` list, which is
 *    what the submission's Attached Documents show. It is now listed under
 *    the field it filled (certificate_storage_id -> "Land Certificate") or
 *    farmer_photo ("Farmer Photo") for the profile picture.
 *
 * The block the sed inserted is replaced wholesale; the list and label
 * variables are read off the minified statement before it rather than
 * hardcoded, and so is the toast binding (from the "section saved" toast in
 * the same function). When the upload comes back empty -- the API helper
 * toasts the transport error and returns null, e.g. on the 413 a reverse
 * proxy returns for a large certificate -- the save is abandoned with a
 * message that says so, instead of saving the section without the file and
 * announcing success. One File per section save is what the library hands over, so a
 * dialog with several certificate rows attaches the first.
 *
 * Only the static (browser) chunk carries the sed's insertion: the server
 * copy of this client hook is minified differently and never runs there (a
 * save happens in the browser), so it is left alone, as the sed leaves it.
 * Exits non-zero unless the static chunk is patched.
 */
const fs = require("fs");
const path = require("path");

const ROOT = process.env.STAFF_UI_NEXT_ROOT || "/app/.next";
const ID = "[A-Za-z_$][A-Za-z0-9_$]*";

// {filesToUpload:n,fileLabels:a}=(0,d.YX)(s)||{},o=void 0===n?[]:n,c=[];
const HEAD = new RegExp(
  `fileLabels:(${ID})\\}=\\(0,${ID}\\.${ID}\\)\\(${ID}\\)\\|\\|\\{\\},${ID}=void 0===${ID}\\?\\[\\]:${ID},(${ID})=\\[\\];`
);
// l.oR.success(J("toast_section_saved_successfully")) -- the toast module binding.
const TOAST = new RegExp(`(${ID})\\.oR\\.success\\(${ID}\\("toast_section_saved_successfully"\\)\\)`);
const UPLOAD_FAILED =
  "The file could not be uploaded, so this section was not saved. Use a PDF, JPG, PNG or WebP up to 10 MB and try again.";
// The sed's insertion, from `if(<changes>?.image){` to its closing brace.
const SED_BLOCK = new RegExp(
  String.raw`if\((${ID})\?\.image\)\{let __up=await (${ID})\(\[\1\.image\]\),__doc=Array\.isArray\(__up\)\?__up\[0\]:null;` +
    String.raw`__doc&&__doc\.document_id&&\(\1\.records=\(\1\.records\|\|\[\]\)\.map\(__r=>\(\{\.\.\.__r,record_image_document_id:__doc\.document_id\}\)\)\)\}`
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

function block(changes, upload, labels, docs, toast) {
  return (
    `if(${changes}?.image){let __up=await ${upload}([${changes}.image]),__doc=Array.isArray(__up)?__up[0]:null;` +
    `if(!__doc||!__doc.document_id){${toast}.oR.error(${JSON.stringify(UPLOAD_FAILED)},{position:"top-right",autoClose:8e3});return!1}` +
    `if(__doc&&__doc.document_id){let __slot=null;` +
    `${changes}.records=(${changes}.records||[]).map(__r=>{` +
    `let __k=Object.keys(__r).find(k=>/_storage_id$/.test(k)&&!__r[k]);` +
    `if(__k){__slot=__k;return{...__r,[__k]:__doc.document_id}}` +
    `return{...__r,record_image_document_id:__doc.document_id}});` +
    `${labels}=${labels}||[];${labels}[${docs}.length]=__slot||"farmer_photo";${docs}.push(__doc)}}`
  );
}

let patched = 0;
for (const file of listJs(path.join(ROOT, "static"))) {
  const before = fs.readFileSync(file, "utf8");
  const sed = SED_BLOCK.exec(before);
  if (!sed) continue;
  const head = HEAD.exec(before.slice(0, sed.index));
  if (!head) throw new Error(`${file}: photo upload found but the labels/documents statement did not match`);
  const [, labels, docs] = head;
  const toast = TOAST.exec(before.slice(sed.index));
  if (!toast) throw new Error(`${file}: photo upload found but the section-saved toast did not match`);
  const after = before.slice(0, sed.index) + block(sed[1], sed[2], labels, docs, toast[1]) + before.slice(sed.index + sed[0].length);
  fs.writeFileSync(file, after);
  patched += 1;
  console.log("  patched " + path.relative(ROOT, file));
}

if (patched < 1) {
  console.error("intake-photo-document patch matched no static chunk - did the intake profile image upload sed apply?");
  process.exit(1);
}
console.log(`intake uploads are recorded on the record and listed as documents in ${patched} bundle(s)`);
