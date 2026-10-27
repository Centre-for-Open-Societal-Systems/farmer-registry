// Stand-in for the native PM active-key endpoint. Configure accepts only
// synthetic test public keys; private signing material stays in test memory.
const http = require('http');
let config = {};
http.createServer((req, res) => {
  const path = new URL(req.url, 'http://fixture.invalid').pathname;
  const send = (status, body) => {
    res.statusCode = status;
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify(body));
  };
  if (path.endsWith('/health')) return send(200, {ok: true});
  if (path.endsWith('/configure') && req.method === 'POST') {
    config = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
    return send(200, {ok: true});
  }
  const match = path.match(/\/keys\/([^/]+)\/([^/]+)$/);
  if (match && req.method === 'GET') {
    if (config.failure) return send(503, {message: 'Synthetic PM unavailable'});
    if (decodeURIComponent(match[1]) !== config.partner_id || decodeURIComponent(match[2]) !== config.kid)
      return send(404, {message: 'Active key not found'});
    return send(200, {...config, partner_id: config.wrongPartner ? 'different-partner' : config.partner_id});
  }
  return send(501, {message: 'Call outside the PM key contract'});
}).listen(process.env.PORT);
