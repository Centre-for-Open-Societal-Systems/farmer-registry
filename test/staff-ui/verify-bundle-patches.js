// Post-build verification for the farmer staff-ui image.
//
// WHY THIS EXISTS
// The staff-ui image customises a prebuilt, MINIFIED Next.js bundle with sed.
// The Dockerfile's own `here` guards prove a patch's marker text is PRESENT,
// which is necessary but nowhere near sufficient:
//
//   * a sed can inject text that is not valid JavaScript, producing a chunk
//     that contains the marker and is a syntax error -- that breaks the whole
//     intake page, i.e. strictly worse than the bug it was fixing;
//   * the injected code can parse and still be wrong (upload the photo but
//     stamp nothing, stamp `undefined`, add a key when no photo was picked --
//     which nulls a column another section owns -- or propagate an upload
//     failure and abort the user's whole section save);
//   * the rehash step renames content-hashed assets, so a missed reference
//     leaves the route pointing at a filename that no longer exists.
//
// None of those are visible to a grep for the marker. This checks all three.
//
// USAGE (against a built image):
//   docker run --rm -v "$PWD/test/staff-ui:/t" --entrypoint node <image> \
//     /t/verify-bundle-patches.js
//
// Exits non-zero on any failure, so it can gate a pipeline.

const fs = require('fs');

const NEXT = '/app/.next';
const MARKER = 'record_image_document_id:__d.document_id';

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}${detail ? ' -- ' + detail : ''}`); }
};

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

check('photo-upload patch landed in exactly one static chunk',
      patchedChunks.length === 1,
      `found ${patchedChunks.length}`);
if (patchedChunks.length !== 1) { console.log(`\n${pass} passed, ${fail} failed`); process.exit(1); }

const chunkPath = patchedChunks[0];
const chunkName = chunkPath.split('/').pop().replace(/\.js$/, '');
console.log(`      patched chunk: ${chunkName}`);

// ------------------------------------------------------- 1. does it parse?
// Same V8 that will serve it. `new Function` forces a full parse.
for (const f of [chunkPath]) {
  try { new Function(fs.readFileSync(f, 'utf8')); check('patched chunk is syntactically valid JS', true); }
  catch (e) { check('patched chunk is syntactically valid JS', false, e.message); }
}

// -------------------------------------------- 2. does the logic behave?
// The snippet is EXTRACTED from the shipped chunk, not retyped, so this test
// cannot drift from what actually ships.
// Matched loosely on purpose: anchor on the injected body (which is ours and
// stable) rather than on the `if(i?.image)` guard, so that a REGRESSED guard
// still gets extracted and is then caught by the behavioural checks below --
// rather than merely failing to be found, which would report the wrong cause.
const src = fs.readFileSync(chunkPath, 'utf8');
const m = src.match(/if\([^)]*\)try\{let __u=await .*?\}catch\(__e\)\{[^}]*\}/);
check('injected snippet is locatable in the shipped chunk', !!m);

if (m) {
  const run = (i, h) =>
    new Function('i', 'h', `return (async()=>{ ${m[0]} ; return i; })()`)(i, h);

  (async () => {
    const photo = { name: 'farmer.jpg' };

    // The reported bug: a photo picked at intake must be uploaded and stamped.
    let got = null;
    const a = { image: photo, records: [{ first_name: 'Abebe' }, { first_name: 'Kebede' }] };
    await run(a, async (f) => { got = f; return [{ document_id: 'doc-123' }]; });
    check('photo is uploaded', got && got[0] === photo);
    check('document_id stamped on every record',
          a.records.every((r) => r.record_image_document_id === 'doc-123'));
    check('unrelated fields preserved', a.records[0].first_name === 'Abebe');

    // No photo: must not upload, and must not ADD the key. Adding it would
    // null a column a different section owns.
    let called = false;
    const b = { records: [{ first_name: 'Abebe' }] };
    await run(b, async () => { called = true; return [{ document_id: 'x' }]; });
    check('no upload attempted when no photo was picked', !called);
    check('no stray record_image_document_id key added',
          !('record_image_document_id' in b.records[0]));

    // Upload failure must not abort the section save and lose typed data.
    let threw = false;
    const c = { image: photo, records: [{ first_name: 'Abebe' }] };
    try { await run(c, async () => { throw new Error('boom'); }); } catch { threw = true; }
    check('upload failure does not abort the save', !threw);
    check('record intact after failed upload',
          c.records[0].first_name === 'Abebe' && !c.records[0].record_image_document_id);

    // Empty/!useful upload result must not stamp undefined.
    const d = { image: photo, records: [{ first_name: 'Abebe' }] };
    await run(d, async () => []);
    check('empty upload result does not stamp undefined',
          !('record_image_document_id' in d.records[0]));

    // Header-only photo edit with no records must not crash.
    let crashed = false;
    try { await run({ image: photo, records: [] }, async () => [{ document_id: 'd9' }]); }
    catch { crashed = true; }
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

    console.log(`\n${pass} passed, ${fail} failed`);
    process.exit(fail ? 1 : 0);
  })();
}
