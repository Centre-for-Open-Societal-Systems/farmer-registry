// Feed a real backend upload response (after the Next route transform) into
// the upload block extracted from the rc.544 staff-ui bundle.
// Usage: node /t/verify-upload-contract.js /tmp/upload.json
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {loadUploadHarness, serializedFile} = require('./upload-bundle-harness.cjs');

async function main() {
  if (!process.argv[2]) throw Error('usage: verify-upload-contract.js <upload-response.json>');
  const response = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  assert.ok(Array.isArray(response), 'route transform must yield an array');
  assert.equal(response.length, 1, 'fixture must contain one uploaded document');
  const expected = response[0]?.document_id;
  assert.ok(expected, 'backend must expose document_id');
  const {run} = loadUploadHarness();
  const changes = {
    section_files: [serializedFile('farmer.jpg', '_profile')],
    records: [{first_name: 'Abebe'}],
  };
  const result = await run(changes, async () => response);
  assert.notEqual(result.out, false, 'valid upload must permit the save');
  assert.equal(changes.records[0].record_image_document_id, expected);
  assert.equal(result.docs[0].document_id, expected);
  assert.equal(result.labels[0], 'farmer_photo');
  assert.equal(result.toasts.length, 0);
  console.log('PASS: backend document ID persists on the record and attached document');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
