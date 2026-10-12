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
// Verify the rc.544 section_files contract using both the upload block and
// file deserializer extracted from the bundle. Photos and file-widget uploads
// must persist their IDs, and failed uploads must abort the section save.
//
// USAGE (against a built image):
//   docker run --rm -v "$PWD/test/staff-ui:/t" --entrypoint node <image> \
//     /t/verify-bundle-patches.js
//
// Exits non-zero on any failure, so it can gate a pipeline.

const fs = require('fs');

const {loadUploadHarness, serializedFile} = require('./upload-bundle-harness.cjs');

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}${detail ? ' -- ' + detail : ''}`); }
};
const done = () => { console.log(`\n${pass} passed, ${fail} failed`); process.exit(fail ? 1 : 0); };

let harness;
try { harness = loadUploadHarness(); }
catch (e) { check('shipped upload block and deserializer load', false, e.message); done(); }
const {root: NEXT, allFiles, chunkPath, run} = harness;
const chunkName = chunkPath.split('/').pop().replace(/\.js$/, '');
check('exactly one patched chunk parses and its upload block loads', true);

(async () => {
  const photo = serializedFile('farmer.jpg', '_profile');
  const ok = async () => [{ document_id: 'doc-123' }];

  // Farmer photo: uploaded, stamped on every record, listed as the photo.
  let got = null;
  const a = { section_files: [photo], records: [{ first_name: 'Abebe' }, { first_name: 'Kebede' }] };
  const ra = await run(a, async (f) => { got = f; return ok(); });
  check('picked file is uploaded', got && got.length === 1 && got[0] instanceof File && got[0].name === photo.name);
  check('photo document id stamped on every record',
        a.records.every((r) => r.record_image_document_id === 'doc-123'));
  check('unrelated fields preserved', a.records[0].first_name === 'Abebe');
  check('photo listed in the section documents as farmer_photo',
        ra.docs.length === 1 && ra.docs[0].document_id === 'doc-123' && ra.labels[0] === 'farmer_photo');

  // Land certificate: the document id fills the blank storage field instead.
  const b = { section_files: [serializedFile('deed.pdf', '_direct_file', 'certificate_storage_id')], records: [{ land_id: 'LAN-001', certificate_storage_id: '' }] };
  const rb = await run(b, ok);
  check('certificate document id fills its target field',
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
    const d = { section_files: [photo], records: [{ first_name: 'Abebe' }] };
    const rd = await run(d, async () => result);
    check(`failed upload (${label}) abandons the save`, rd.out === false);
    check(`failed upload (${label}) says so`, rd.toasts.length === 1 && /could not be uploaded/.test(rd.toasts[0]));
    check(`failed upload (${label}) leaves the record untouched`,
          d.records[0].first_name === 'Abebe' && !('record_image_document_id' in d.records[0]));
  }

  // Header-only photo edit with no records must not crash.
  let crashed = false;
  try { await run({ section_files: [photo], records: [] }, ok); } catch { crashed = true; }
  check('empty records list does not crash', !crashed);

  // Multiple files keep labels, IDs and record targets aligned. Supporting
  // documents retain the platform's own handling and are not uploaded here.
  const multi = {
    section_files: [photo,
      serializedFile('deed.pdf', '_direct_file', 'certificate_storage_id'),
      serializedFile('support.pdf', '_supporting_docs')],
    records: [{certificate_storage_id: null, first_name: 'Abebe'}],
  };
  const rm = await run(multi, async files => {
    check('only profile and direct files are uploaded',
      files.length === 2 && files[0].name === 'farmer.jpg' && files[1].name === 'deed.pdf');
    return [{document_id: 'photo-id'}, {document_id: 'deed-id'}];
  });
  check('mixed uploads persist the correct IDs',
    multi.records[0].record_image_document_id === 'photo-id' &&
    multi.records[0].certificate_storage_id === 'deed-id');
  check('mixed uploads retain document labels',
    rm.labels.join(',') === 'farmer_photo,certificate_storage_id');
  const partial = {section_files: multi.section_files, records: [{first_name: 'Abebe'}]};
  const rp = await run(partial, ok);
  check('partial upload aborts before modifying records',
    rp.out === false && rp.toasts.length === 1 &&
    JSON.stringify(partial.records) === '[{"first_name":"Abebe"}]');
  const rows = {
    section_files: [serializedFile('deed.pdf', '_direct_file', 'certificate_storage_id')],
    records: [{certificate_storage_id: 'existing-id'}, {certificate_storage_id: {__type: 'File'}}],
  };
  await run(rows, ok);
  check('list upload preserves existing certificates and fills the picked row',
    rows.records[0].certificate_storage_id === 'existing-id' &&
    rows.records[1].certificate_storage_id === 'doc-123');

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
