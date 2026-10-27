// Native Master Data envelope and OAuth client-credentials contracts only.
const http = require('http');
let fixture = {};
http.createServer((req,res) => {
  const path = new URL(req.url,'http://fixture.invalid').pathname;
  const send = (status,body) => { res.statusCode=status; res.setHeader('Content-Type','application/json'); res.end(JSON.stringify(body)); };
  if (path.endsWith('/health')) return send(200,{ok:true});
  if (path.endsWith('/configure') && req.method==='POST') {
    fixture=typeof req.body==='string'?JSON.parse(req.body):req.body;
    return send(200,{ok:true});
  }
  if (path.endsWith('/token') && req.method==='POST') {
    if (fixture.tokenUnavailable) return send(503,{error:'temporarily_unavailable'});
    const body=typeof req.body==='string'?Object.fromEntries(new URLSearchParams(req.body)):req.body;
    if (body.grant_type!=='client_credentials' || body.client_id!==fixture.clientId || body.client_secret!==fixture.clientSecret)
      return send(401,{error:'invalid_client'});
    return send(200,{access_token:fixture.token,token_type:'Bearer',expires_in:60});
  }
  if (path.endsWith('/geo/get_all_geo_levels') && req.method==='POST') {
    if (fixture.unavailable) return send(503,{message:'Synthetic dependency unavailable'});
    if (req.headers.authorization!=='Bearer '+fixture.token) return send(401,{message:'Unauthorized'});
    const body=typeof req.body==='string'?JSON.parse(req.body):req.body;
    if (!body.request_header?.request_id || !body.request_body?.request_payload)
      return send(422,{message:'Native request envelope required'});
    return send(200,{response_header:{response_status:fixture.refused?'FAILURE':'SUCCESS'},response_body:{response_payload:fixture.levels}});
  }
  return send(501,{message:'Call outside the reporting geography contract'});
}).listen(process.env.PORT);
