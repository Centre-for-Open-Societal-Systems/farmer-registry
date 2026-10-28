// Derived from the installed Master Data OpenAPI and measured CSRF responses.
const http = require('http');
http.createServer(async (req, res) => {
  const reply = (status, body) => {
    res.writeHead(status, {'content-type': 'application/json'});
    res.end(JSON.stringify(body));
  };
  let body = req.body;
  if (typeof body === 'string') {
    try { body = JSON.parse(body); } catch { body = Object.fromEntries(new URLSearchParams(body)); }
  } else if (!body) {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const text = Buffer.concat(chunks).toString();
    try { body = JSON.parse(text); } catch { body = Object.fromEntries(new URLSearchParams(text)); }
  }
  if (req.method === 'POST' && req.url === '/token') {
    if (body.client_id !== 'farmer-test' || body.client_secret !== 'synthetic-secret') return reply(401, {error: 'invalid_client'});
    return reply(200, {access_token: 'synthetic-token', expires_in: 300});
  }
  if (req.method !== 'POST' || !['/geo/get_all_geo_levels', '/geo/get_geo_level_values', '/denied', '/refresh-once'].includes(req.url)) return reply(501, {error: 'Outside measured Master Data contract'});
  if (req.headers.authorization !== 'Bearer synthetic-token') return reply(401, {error: 'Unauthorized'});
  const csrf = req.headers['x-csrf-token'];
  if (!csrf || !(req.headers.cookie || '').split(';').map(x => x.trim()).includes('X-CSRF-Token=' + csrf)) return reply(403, {error: 'CSRF token missing or invalid'});
  if (req.url === '/denied') return reply(403, {error: 'Read access denied'});
  if (req.url === '/refresh-once' && !req.headers['x-test-retried']) {
    // The caller retry is tracked in the mock's state, never by changed client headers.
    const key = 'farmer-mds.refresh-once';
    if (!pm.state.get(key)) { pm.state.set(key, true); return reply(401, {error: 'Expired token'}); }
  }
  const levels = ['region', 'zone', 'woreda', 'kebele'];
  let payload;
  if (req.url === '/geo/get_all_geo_levels') payload = levels.map((name, i) => ({level_id: 'level-' + name, level_mnemonic: name, parent_level_id: i ? 'level-' + levels[i-1] : null}));
  else if (req.url === '/geo/get_geo_level_values') {
    const name = body.request_body.request_payload.level_id.replace('level-', '');
    const i = levels.indexOf(name);
    if (i < 0) return reply(400, {error: 'Unknown level'});
    payload = [{level_id: 'level-' + name, level_value_id: name + '-TEST', level_value_mnemonic: 'Synthetic ' + name, parent_level_value_id: i ? levels[i-1] + '-TEST' : null}];
  } else payload = {ok: true};
  return reply(200, {response_header: {response_status: 'SUCCESS'}, response_body: {response_payload: payload}});
}).listen(process.env.PORT || 4923);
