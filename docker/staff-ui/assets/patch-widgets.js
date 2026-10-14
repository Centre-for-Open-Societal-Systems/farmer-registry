// Guarded adapters for rc.544's bundled widget library. No global DOM rewriting.
const fs = require('fs'), path = require('path');
const root = process.env.STAFF_UI_NEXT_ROOT || '/app/.next';
function files(dir) { return fs.readdirSync(dir,{withFileTypes:true}).flatMap(e => e.isDirectory()?files(path.join(dir,e.name)):e.name.endsWith('.js')?[path.join(dir,e.name)]:[]); }
let matched = 0;
for (const file of files(path.join(root,'static'))) {
 let s = fs.readFileSync(file,'utf8');
 if (!s.includes('function tS(e){let t=e.trim()')) continue;
 const replacements = [
  ['Y=(0,R.useCallback)(()=>{A.imageUrl&&(m(null),r(P($({...a},A.imageUrl,null))))},[A.imageUrl,a,r])',
   'Y=(0,R.useCallback)(()=>{if(A.imageUrl){m(null);let e=$({...a},A.imageUrl,null);"farmer-photo"===t["widget-id"]&&A.image&&(e=$(e,A.image,null));r(P(e))}},[A.imageUrl,A.image,a,r,t])'],
  ['function tS(e){let t=e.trim().replace(/[_-]+/g," ").replace(/\\s+/g," ");return t?t.split(" ").map(e=>e.charAt(0).toUpperCase()+e.slice(1).toLowerCase()).join(" "):""}',
   'function tS(e){let t=e.trim().replace(/[_-]+/g," ").replace(/\\s+/g," ");return t?t.split(" ").map(e=>e.charAt(0).toUpperCase()+e.slice(1).toLowerCase()).join(" ").replace(/\\b(gc|ec)\\b/gi,e=>e.toUpperCase()):""}'],
  ['let r=X(e,t["column-key"]),l=t.widget||"text";return null==r',
   'let r=X(e,t["column-key"]),l=t.widget||"text";if("certificate_provided"===t["column-key"]){let f=X(e,"certificate_storage_id");return f&&("object"!==typeof f||f.document_id||f.name)?"Yes":"No"}if("certificate_storage_id"===t["column-key"]&&r&&"object"===typeof r)return r.source_filename||r.name||"Attached file";return null==r'],
  ['let r=t.widget||"text",i=K(e,t);if("select"===r',
   'let r=t.widget||"text",i=K(e,t);if("certificate_storage_id"===l&&a)return eF.jsx("span",{"data-coss-document-id":"string"===typeof a?a:a.document_id||"",children:i});if("select"===r'],
  ['let i=r["column-key"],a=r.widget||"text",o=X(t,r);if("select"===a',
   'let i=r["column-key"],a=r.widget||"text",o=X(t,r);if("certificate_provided"===i){let f=e?.certificate_storage_id;o=f&&("object"!==typeof f||f.document_id||f.name)?"Yes":"No"}if("certificate_storage_id"===i&&e?.[i]){let f=e[i];return eF.jsx("td",{className:"px-4 py-3 whitespace-nowrap",children:eF.jsx("span",{"data-coss-document-id":"string"===typeof f?f:f.document_id||"",style:l,children:"object"===typeof f?f.source_filename||f.name||"Attached file":f})},i)}if("select"===a'],
 ];
 for(const [before,after] of replacements){
  if(s.split(before).length!==2) throw Error('RC widget integration changed: '+before.slice(0,80));
  s=s.replace(before,after);
 }
 fs.writeFileSync(file,s); matched++;
}
if(matched!==1) throw Error('Expected one RC widget bundle, found '+matched);
