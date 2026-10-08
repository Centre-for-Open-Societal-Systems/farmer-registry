const {test} = require('node:test');
const assert = require('node:assert/strict');
const {POST} = require('../../docker/staff-ui/assets/farmer-bulk-proxy.cjs');

test('relays multipart, session and CSRF without accepting a client backend', async () => {
  process.env.BACKEND_API_URL = 'http://staff-api:8000';
  const old = global.fetch;
  global.fetch = async (url, options) => {
    assert.equal(url, 'http://staff-api:8000/farmer/bulk-import');
    assert.equal(options.headers.get('cookie'), 'X-Access-Token=test');
    assert.equal(options.headers.get('x-csrf-token'), 'csrf');
    assert.equal(options.redirect, 'manual');
    assert.match(options.body.toString(), /first_name/);
    return Response.json({response_body: {response_payload: {successful: 1}}}, {headers: {'set-cookie': 'refreshed=yes; HttpOnly'}});
  };
  try {
    const form = new FormData(); form.append('file', new Blob(['first_name,father_first_name\nA,B']), 'farmers.csv'); form.append('form_id', 'form');
    const response = await POST(new Request('http://portal/api/upload?farmer_bulk_import=import', {method: 'POST', body: form, headers: {'cookie':'X-Access-Token=test', 'x-csrf-token':'csrf'}}));
    assert.equal(response.status, 200);
    assert.match(response.headers.get('set-cookie'), /refreshed=yes/);
  } finally { global.fetch = old; }
});

test('oversize files are rejected before contacting the API', async () => {
  const old = global.fetch; let called = false;
  global.fetch = async () => { called = true; };
  try {
    const response = await POST(new Request('http://portal/api/upload?farmer_bulk_import=import', {method:'POST', body: 'x'.repeat(11 * 1024 * 1024), headers:{'content-type':'multipart/form-data; boundary=x'}}));
    assert.equal(response.status, 413); assert.equal(called, false);
  } finally { global.fetch = old; }
});

test('network failure does not retry or announce failure of all rows', async () => {
  const old = global.fetch; let calls = 0;
  global.fetch = async () => { calls++; throw new Error('network'); };
  try {
    const response = await POST(new Request('http://portal/api/upload?farmer_bulk_import=import', {method:'POST', body:'body', headers:{'content-type':'multipart/form-data; boundary=x'}}));
    assert.equal(response.status, 502); assert.equal(calls, 1);
    assert.match((await response.json()).error, /some rows may have completed/);
  } finally { global.fetch = old; }
});
