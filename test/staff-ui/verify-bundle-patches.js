// Post-build verification for the farmer staff-ui image.
//
// WHY THIS EXISTS
// The staff-ui image customises a prebuilt, MINIFIED Next.js bundle with sed
// and node patch scripts. The Dockerfile's own `here` guards prove a patch's
// marker text is PRESENT, which is necessary but nowhere near sufficient:
//
//   * a patch can inject text that is not valid JavaScript, producing a chunk
//     that contains the marker and is a syntax error -- that breaks the whole
//     intake page, i.e. strictly worse than the bug it was fixing;
//   * the injected code can parse and still be wrong (upload the file but
//     stamp nothing, stamp `undefined`, add a key when no file was picked --
//     which nulls a column another section owns -- or save the section
//     without the file and announce success);
//   * the rehash step renames content-hashed assets, so a missed reference
//     leaves the route pointing at a filename that no longer exists.
//
// None of those are visible to a grep for the marker. This checks all three,
// against the intake-upload block as patch-intake-photo-document.js leaves it:
// the one File a section save carries is uploaded, its document id fills a
// blank *_storage_id field of the record (a land certificate) or else is
// stamped as record_image_document_id (the farmer photo), the upload is listed
// in the section's documents under that field, and an upload that comes back
// empty abandons the save with an error toast instead of saving without it.
//
// USAGE (against a built image):
//   docker run --rm -v "$PWD/test/staff-ui:/t" --entrypoint node <image> \
//     /t/verify-bundle-patches.js
//
// Exits non-zero on any failure, so it can gate a pipeline.

const fs = require('fs');

const NEXT = '/app/.next';
const MARKER = 'record_image_document_id:__doc.document_id';
const ID = '[A-Za-z_$][A-Za-z0-9_$]*';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}${detail ? ' -- ' + detail : ''}`); }
};
const done = () => { console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0); };

// ---------------------------------------------------------------- discovery
function walk(dir, out = []) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = `${dir}/${e.name}`;
    if (e.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

const allFiles = walk(NEXT);
const patchedChunks = allFiles.filter(
  (f) => f.startsWith(`${NEXT}/static/chunks/`) &&
         f.endsWith('.js') &&
         fs.readFileSync(f, 'utf8').includes(MARKER),
);

check('intake-upload patch landed in exactly one static chunk',
      patchedChunks.length === 1,
      `found ${patchedChunks.length}`);
if (patchedChunks.length !== 1) done();

const chunkPath = patchedChunks[0];
const chunkName = chunkPath.split('/').pop().replace(/\.js$/, '');
console.log(`      patched chunk: ${chunkName}`);

// ------------------------------------------------------- 1. does it parse?
// Same V8 that will serve it. `new Function` forces a full parse.
try { new Function(fs.readFileSync(chunkPath, 'utf8')); check('patched chunk is syntactically valid JS', true); }
catch (e) { check('patched chunk is syntactically valid JS', false, e.message); }

// -------------------------------------------- 2. does the logic behave?
// The block is EXTRACTED from the shipped chunk, not retyped, so this test
// cannot drift from what actually ships. Its free variables -- the section
// changes, the upload helper, the toast module, the labels and documents
// lists -- are minified names, read off the block and supplied as stubs.
const src = fs.readFileSync(chunkPath, 'utf8');
const BLOCK = new RegExp(
  `if\\((${ID})\\?\\.image\\)\\{let __up=await (${ID})\\(\\[\\1\\.image\\]\\).*?(${ID})\\.push\\(__doc\\)\\}\\}`,
);
const m = BLOCK.exec(src);
check('injected upload block is locatable in the shipped chunk', !!m);
if (!m) done();

const block = m[0];
const [, CHANGES, UPLOAD, DOCS] = m;
const toastM = new RegExp(`\\{(${ID})\\.oR\\.error\\(`).exec(block);
const labelsM = new RegExp(`;(${ID})=\\1\\|\\|\\[\\];\\1\\[${DOCS.replace('$', '\\$')}\\.length\\]`).exec(block);
check('toast and labels bindings are readable off the block', !!toastM && !!labelsM);
if (!toastM || !labelsM) done();
const TOAST = toastM[1], LABELS = labelsM[1];
const names = [CHANGES, UPLOAD, TOAST, LABELS, DOCS];
check('block free variables are distinct', new Set(names).size === names.length, names.join(','));

// Runs the block once. Resolves to false when the block abandoned the save
// (its own `return!1`), otherwise to the labels/docs it left behind.
function run(changes, upload) {
  const toasts = [];
  const toast = { oR: { error: (msg) => toasts.push(msg) } };
  const labels = [];
  const docs = [];
  const fn = new Function(...names,
    `return (async () => { ${block}; return { labels: ${LABELS}, docs: ${DOCS} }; })();`);
  return fn(changes, upload, toast, labels, docs).then((out) => ({ out, toasts, labels, docs }));
}

(async () => {
  const photo = { name: 'farmer.jpg' };
  const ok = async () => [{ document_id: 'doc-123' }];

  // Farmer photo: uploaded, stamped on every record, listed as the photo.
  let got = null;
  const a = { image: photo, records: [{ first_name: 'Abebe' }, { first_name: 'Kebede' }] };
  const ra = await run(a, async (f) => { got = f; return ok(); });
  check('picked file is uploaded', got && got[0] === photo);
  check('photo document id stamped on every record',
        a.records.every((r) => r.record_image_document_id === 'doc-123'));
  check('unrelated fields preserved', a.records[0].first_name === 'Abebe');
  check('photo listed in the section documents as farmer_photo',
        ra.docs.length === 1 && ra.docs[0].document_id === 'doc-123' && ra.labels[0] === 'farmer_photo');

  // Land certificate: the document id fills the blank storage field instead.
  const b = { image: { name: 'deed.pdf' }, records: [{ land_id: 'LAN-001', certificate_storage_id: '' }] };
  const rb = await run(b, ok);
  check('certificate document id fills the blank *_storage_id field',
        b.records[0].certificate_storage_id === 'doc-123');
  check('certificate is not also stamped as the profile image',
        !('record_image_document_id' in b.records[0]));
  check('certificate listed in the section documents under its field',
        rb.labels[0] === 'certificate_storage_id' && rb.docs.length === 1);

  // No file picked: no upload, and no key ADDED -- adding it would null a
  // column a different section owns.
  let called = false;
  const c = { records: [{ first_name: 'Abebe' }] };
  const rc = await run(c, async () => { called = true; return ok(); });
  check('no upload attempted when no file was picked', !called);
  check('no stray record_image_document_id key added', !('record_image_document_id' in c.records[0]));
  check('nothing listed in documents when no file was picked', rc.docs.length === 0);

  // Upload came back empty (the API helper toasts and returns null, e.g. a
  // 413 from a proxy): the save is abandoned, with a message, records untouched.
  for (const [label, result] of [['null', null], ['empty list', []], ['no document_id', [{}]]]) {
    const d = { image: photo, records: [{ first_name: 'Abebe' }] };
    const rd = await run(d, async () => result);
    check(`failed upload (${label}) abandons the save`, rd.out === false);
    check(`failed upload (${label}) says so`, rd.toasts.length === 1 && /could not be uploaded/.test(rd.toasts[0]));
    check(`failed upload (${label}) leaves the record untouched`,
          d.records[0].first_name === 'Abebe' && !('record_image_document_id' in d.records[0]));
  }

  // Header-only photo edit with no records must not crash.
  let crashed = false;
  try { await run({ image: photo, records: [] }, ok); } catch { crashed = true; }
  check('empty records list does not crash', !crashed);

  // ------------------------------------ 3. is it wired into the routes?
  const refs = allFiles.filter(
    (f) => /\.(js|json)$/.test(f) && f !== chunkPath &&
           fs.readFileSync(f, 'utf8').includes(chunkName),
  );
  check('patched chunk is referenced by the build',
        refs.length > 0, 'nothing references it; the route would 404');
  check('patched chunk is reachable from an intake-form route',
        refs.some((r) => r.includes('intake-form')),
        'not referenced by any intake-form manifest');

  // A rehash that renamed a file but missed a reference leaves a dangling
  // /_next/static/... URL, which 404s in the browser.
  const dangling = [];
  for (const f of allFiles.filter((x) => /\.(js|json)$/.test(x))) {
    const s = fs.readFileSync(f, 'utf8');
    for (const ref of s.match(/static\/chunks\/[A-Za-z0-9._\-[\]]+\.js/g) || []) {
      if (!fs.existsSync(`${NEXT}/${ref}`)) dangling.push(`${f.replace(NEXT, '')} -> ${ref}`);
    }
  }
  check('no dangling static chunk references after rehash',
        dangling.length === 0, dangling.slice(0, 5).join('; '));

  done();
})().catch((e) => { check('verifier ran to completion', false, e.stack); done(); });
