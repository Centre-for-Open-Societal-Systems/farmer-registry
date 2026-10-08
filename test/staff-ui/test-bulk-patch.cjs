const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

test('patch delegates bulk requests and preserves original document uploads', async () => {
  const root = path.resolve('.cache/bulk-patch-test');
  fs.mkdirSync(path.join(root,'server/app/api/documents/upload_documents'),{recursive:true});
  fs.writeFileSync(path.join(root,'server/app-paths-manifest.json'),JSON.stringify({'/api/documents/upload_documents/route':'app/api/documents/upload_documents/route.js'}));
  const route=path.join(root,'server/app/api/documents/upload_documents/route.js');
  fs.writeFileSync(route, 'const original={POST:async()=>"original"};const AppRouteRouteModule=class{constructor(config){this.userland=config.userland;}};module.exports=new AppRouteRouteModule({userland:original});');
  const script=path.join(root,'bulk.js'); fs.writeFileSync(script,'const API="__FARMER_BULK_UPLOAD_ROUTE__";');
  const env={STAFF_UI_NEXT_ROOT:root,STAFF_UI_BULK_SCRIPT:script,STAFF_UI_BULK_PROXY:'/app/farmer-bulk-proxy.cjs'};
  vm.runInNewContext(fs.readFileSync('docker/staff-ui/assets/patch-farmer-bulk-upload.js','utf8'),{require,process:{env},console});
  const exports={};
  vm.runInNewContext(fs.readFileSync(route,'utf8'), {module:exports,URL,require:()=>({POST:async()=> 'bulk'})});
  assert.equal(await exports.exports.userland.POST(new Request('http://portal/api/documents/upload_documents')), 'original');
  assert.equal(await exports.exports.userland.POST(new Request('http://portal/api/documents/upload_documents?farmer_bulk_import=import')), 'bulk');
  assert.equal(fs.readFileSync(script,'utf8'),'const API="/api/documents/upload_documents";');
});
