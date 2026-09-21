// Step 2 of the upload-seam contract test (see emit_upload_response_fixture.py).
//
// Takes the REAL staff-api upload response -- already passed through the real
// Next.js route transform -- and feeds it to the patch code EXTRACTED VERBATIM
// from the built staff-ui chunk. Neither side is hand-written here, so this
// fails if either drifts:
//
//   * backend renames the payload key or the id field
//   * the route's transform stops matching it
//   * the injected patch stops reading it the same way
//
// Usage (inside the built staff-ui image):
//   node /t/verify-upload-contract.js /tmp/upload.json

const fs = require('fs');

const fixturePath = process.argv[2];
if (!fixturePath) {
  console.error('usage: verify-upload-contract.js <upload-response.json>');
  process.exit(2);
}

// Real backend response, post route-transform.
const uploadResult = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));

// Real shipped patch, lifted out of the built bundle.
const NEXT = '/app/.next/static/chunks';
const MARKER = 'record_image_document_id:__d.document_id';
const chunk = fs
  .readdirSync(NEXT)
  .map((f) => `${NEXT}/${f}`)
  .filter((f) => f.endsWith('.js'))
  .find((f) => fs.readFileSync(f, 'utf8').includes(MARKER));

if (!chunk) {
  console.log('FAIL: no shipped chunk contains the photo-upload patch');
  process.exit(1);
}

const src = fs.readFileSync(chunk, 'utf8');
const m = src.match(/if\([^)]*\)try\{let __u=await .*?\}catch\(__e\)\{[^}]*\}/);
if (!m) {
  console.log('FAIL: could not extract the injected snippet from the shipped chunk');
  process.exit(1);
}

let pass = 0, fail = 0;
const check = (name, cond, detail = '') => {
  if (cond) { pass++; console.log(`PASS  ${name}`); }
  else { fail++; console.log(`FAIL  ${name}${detail ? ' -- ' + detail : ''}`); }
};

(async () => {
  console.log(`backend payload: ${JSON.stringify(uploadResult).slice(0, 120)}...`);

  // Preconditions the patch relies on, stated explicitly so a break is legible.
  check('route transform yields an array', Array.isArray(uploadResult));
  check('first document exposes document_id',
        !!(uploadResult[0] && uploadResult[0].document_id),
        JSON.stringify(uploadResult[0] || null));

  // Run the shipped patch with the REAL upload response as uploadFile's result.
  const i = { image: { name: 'farmer.jpg' }, records: [{ first_name: 'Abebe' }] };
  const h = async () => uploadResult;
  await new Function('i', 'h', `return (async()=>{ ${m[0]} })()`)(i, h);

  const expected = uploadResult[0] && uploadResult[0].document_id;
  const actual = i.records[0].record_image_document_id;
  // Guard against a vacuous pass: if the backend stopped returning
  // document_id, `expected` is undefined and so is `actual`, and a bare
  // equality check would report success while the photo silently vanished.
  check('backend returned a document_id to stamp', !!expected,
        'nothing to stamp - the upload contract is broken');
  check('record stamped with the backend document_id',
        !!expected && actual === expected,
        `got ${JSON.stringify(i.records[0])}`);

  console.log(`\n${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
