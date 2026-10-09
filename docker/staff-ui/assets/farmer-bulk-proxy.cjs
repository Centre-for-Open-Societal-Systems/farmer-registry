/* Server-only relay. Authentication, CSRF and permissions are enforced by the
 * staff API. Never accept a backend URL or identity from the uploaded file. */
const MAX_BODY = 10 * 1024 * 1024 + 64 * 1024;

async function readBody(request) {
  const chunks = [];
  let size = 0;
  if (!request.body) return Buffer.alloc(0);
  const reader = request.body.getReader();
  try {
    for (;;) {
      const {value, done} = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BODY) {
        await reader.cancel();
        throw new RangeError('File exceeds the 10 MB limit');
      }
      chunks.push(Buffer.from(value));
    }
  } finally { reader.releaseLock(); }
  return Buffer.concat(chunks);
}

async function POST(request) {
  const operation = new URL(request.url).searchParams.get('farmer_bulk_import');
  if (!['forms', 'import'].includes(operation)) return Response.json({error: 'Unknown operation'}, {status: 400});
  const base = process.env.BACKEND_API_URL;
  if (!base) return Response.json({error: 'Staff API is not configured'}, {status: 503});
  const headers = new Headers();
  for (const key of ['cookie', 'authorization', 'x-csrf-token', 'content-type']) {
    const value = request.headers.get(key);
    if (value) headers.set(key, value);
  }
  if (operation === 'import' && !headers.get('content-type')?.startsWith('multipart/form-data;')) {
    return Response.json({error: 'A multipart upload is required'}, {status: 400});
  }
  try {
    const body = operation === 'import' ? await readBody(request) : undefined;
    const upstream = await fetch(base.replace(/\/$/, '') + '/farmer/bulk-import' + (operation === 'forms' ? '/forms' : ''), {
      method: operation === 'forms' ? 'GET' : 'POST', headers, body,
      cache: 'no-store', redirect: 'manual',
    });
    const responseHeaders = new Headers({'content-type': upstream.headers.get('content-type') || 'application/json', 'cache-control': 'no-store'});
    for (const cookie of upstream.headers.getSetCookie()) responseHeaders.append('set-cookie', cookie);
    return new Response(upstream.body, {status: upstream.status, headers: responseHeaders});
  } catch (error) {
    return Response.json({error: error instanceof RangeError ? error.message :
      'The server connection failed. Check intake submissions before retrying; some rows may have completed.'},
    {status: error instanceof RangeError ? 413 : 502});
  }
}
module.exports = {POST};
