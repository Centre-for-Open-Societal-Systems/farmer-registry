// Only the native save/finalize wire contract; not an approval/ingest simulator.
const http = require('http');
const crypto = require('crypto');
let submissions = new Map();
http.createServer((req, res) => {
  const path = new URL(req.url, 'http://fixture.invalid').pathname;
  const send = (code, body) => {res.statusCode=code;res.setHeader('Content-Type','application/json');res.end(JSON.stringify(body));};
  const ok = payload => send(200,{response_header:{response_status:'SUCCESS'},response_body:{response_payload:payload}});
  if (path.endsWith('/health')) return send(200,{ok:true});
  if (path.endsWith('/records')) return ok([...submissions.values()]);
  const b = typeof req.body==='string' ? JSON.parse(req.body) : req.body;
  const p = b?.request_body?.request_payload;
  if (!b?.request_header?.request_id || !p) return send(422,{detail:'Native envelope required'});
  if (path.endsWith('/save_intake_form_submission')) {
    if (!Array.isArray(p.section_payload) || !p.section_id || !p.section_register_id) return send(422,{detail:'Invalid section payload'});
    for (const row of p.section_payload) {
      if (row.prefix && !['MR','MS','MRS','MISS'].includes(row.prefix)) return send(422,{detail:'PREFIX expects a code, not a label'});
    }
    const id = p.submission_id || crypto.randomUUID();
    const rows = p.section_payload.map(row => ({...row,internal_record_id:row.internal_record_id || crypto.randomUUID()}));
    const record=submissions.get(id) || {id,sections:[]};
    record.sections.push({section_id:p.section_id,records:rows});submissions.set(id,record);
    return ok({submission_id:id,section_payloads:[{section_register_id:p.section_register_id,records:rows}]});
  }
  if (path.endsWith('/finalize_intake_form_submission')) {
    const record=submissions.get(p.submission_id);
    if (!record) return send(404,{detail:'Unknown intake'});
    record.finalized=true;return ok({submission_id:p.submission_id});
  }
  return send(501,{detail:'Outside seed intake contract'});
}).listen(process.env.PORT);
