// Run with PLAYWRIGHT_MODULE pointing to an installed Playwright module.
// Creates synthetic drafts only; never edits the operator's existing draft.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const output=path.join(__dirname,'generated');
const base='http://portal.farmer-upstream.localtest.me:3200';
const form='a1a4d25a-1cd4-4356-abac-8782382649';
(async()=>{
 const browser=await chromium.launch({...(process.env.CHROME_PATH?{executablePath:process.env.CHROME_PATH}:{}),headless:true});
 try {
 const context=await browser.newContext(),page=await context.newPage();page.setDefaultTimeout(15000);
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://staff.farmer-upstream.localtest.me:3202');
 await page.locator('#username').fill('staff');await page.locator('#password').fill('staff');await page.locator('#kc-login').click();
 await page.waitForURL('**/en');
 const png=Buffer.from(await page.evaluate(()=>{const c=document.createElement('canvas');c.width=c.height=32;const x=c.getContext('2d');x.fillStyle='#2e8b57';x.fillRect(0,0,32,32);return c.toDataURL('image/png').split(',')[1];}),'base64');
 await page.goto(`${base}/en/intake-form/farmer/new/${form}`);
 const active=()=>page.locator('[data-intake-form-expanded=true]');
 async function step(button='Next'){
  const previous=await active().getAttribute('data-section-id');
  await active().getByRole('button',{name:button,exact:true}).click();
  await page.waitForFunction(old=>{const s=document.querySelector('[data-intake-form-expanded=true]');return s&&s.dataset.sectionId!==old},previous);
 }
 async function gotoSection(id){
  await active().waitFor();
  const sections=await page.locator('.section[data-section-id]').evaluateAll(es=>es.map(e=>e.dataset.sectionId));
  for(let n=0;n<sections.length;n++){
   const current=await active().getAttribute('data-section-id');if(current===id)return;
   await step(sections.indexOf(current)<sections.indexOf(id)?'Next':'Previous');
  }
  throw Error('Cannot reach '+id);
 }
 const input=id=>active().locator(`[data-widget-id="${id}"] input`);
 async function post(endpoint,data){
  return page.evaluate(async({endpoint,data})=>{
   const m=document.cookie.match(/(?:^|; )X-CSRF-Token=([^;]*)/);
   const r=await fetch(endpoint,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':m?decodeURIComponent(m[1]):''},body:JSON.stringify(data)});
   if(!r.ok)throw Error('API '+r.status);return r.json();
  },{endpoint,data});
 }
 const sid=()=>new URL(page.url()).searchParams.get('sid');
 async function records(){const data=await post('/api/intake-form/get-intake-form-submission',{submission_id:sid()});return data.section_payloads.flatMap(s=>s.records||[]);}
 await active().locator('select').first().selectOption('false');await step();await step();await step();
 assert.equal(await active().getAttribute('data-section-id'),'farmer_location');
 const geo=active().locator('[data-widget-id=farmer_geo_hierarchy] select');
 await geo.nth(0).selectOption('region-ET01');await geo.nth(1).selectOption('zone-ET0101');await geo.nth(2).selectOption('woreda-ET010103');await geo.nth(3).selectOption('kebele-ET010103201001');
 assert.equal(await geo.count(),4);await active().screenshot({path:path.join(output,'acceptance-location.png')});
 await geo.nth(0).selectOption('region-ET04');assert.equal(await geo.nth(1).inputValue(),'');assert.equal(await geo.nth(3).inputValue(),'');
 await page.waitForFunction(()=>[...document.querySelectorAll('[data-widget-id=farmer_geo_hierarchy] select')[1].options].some(o=>o.value.startsWith('zone-ET04')));
 await geo.nth(0).selectOption('region-ET01');await geo.nth(1).selectOption('zone-ET0101');await geo.nth(2).selectOption('woreda-ET010103');await geo.nth(3).selectOption('kebele-ET010103201001');
 await step();await input('first_name').fill('Overlayacceptance');await input('last_name').fill('Local');await input('father_first_name').fill('Testfather');await step();
 assert(!/Functional Record|Record Status|Created by|Approved/i.test(await active().innerText()));
 await active().locator('input[type=file]').setInputFiles({name:'photo-a.png',mimeType:'image/png',buffer:png});await step();
 let farmer=(await records()).find(r=>r.first_name==='Overlayacceptance');assert(farmer.record_image_document_id);const originalPhoto=farmer.record_image_document_id;
 assert.equal(farmer.geo_lowest_level_value_id,'kebele-ET010103201001');
 await step('Previous');await active().screenshot({path:path.join(output,'acceptance-photo.png')});
 await active().locator('input[type=file]').setInputFiles({name:'photo-b.png',mimeType:'image/png',buffer:png});
 await page.route('**/api/shared/upload-document',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'Simulated upload failure'})}));
 await active().getByRole('button',{name:'Next',exact:true}).click();await page.getByText('The file could not be uploaded',{exact:false}).waitFor();
 assert.equal((await records()).find(r=>r.first_name==='Overlayacceptance').record_image_document_id,originalPhoto);
 await page.unroute('**/api/shared/upload-document');await step();
 farmer=(await records()).find(r=>r.first_name==='Overlayacceptance');assert.notEqual(farmer.record_image_document_id,originalPhoto);
 await step('Previous');await active().getByRole('button',{name:'Delete',exact:true}).click();await step();
 farmer=(await records()).find(r=>r.first_name==='Overlayacceptance');assert(!farmer.record_image_document_id,'Photo removal must persist');
 await step('Previous');await active().locator('input[type=file]').setInputFiles({name:'photo-final.png',mimeType:'image/png',buffer:png});await step();await step();
 assert((await active().innerText()).includes('Date Of Birth (GC)'));assert((await active().innerText()).includes('Date Of Birth (EC)'));await step();await step();
 assert(!/\((gc|ec)\)/.test(await active().innerText()));await step();
 assert.equal(await active().getAttribute('data-section-id'),'farmer_land_intake');
 async function addLand(id,name){
  await active().getByRole('button',{name:'Add Record',exact:true}).click();
  await page.locator('[data-widget-id$="-land_id"] input').fill(id);
  await page.locator('[data-widget-id$="-certificate_storage_id"] input[type=file]').setInputFiles({name,mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\n'+id+'\n%%EOF')});
  await page.getByRole('button',{name:'Save',exact:true}).click();
  await page.locator('[data-widget-id*="-dlg-"]').first().waitFor({state:'detached'});
 }
 await addLand('OVERLAY-A','certificate-a.pdf');await addLand('OVERLAY-B','certificate-b.pdf');
 let rows=active().locator('tbody tr');assert((await rows.nth(0).innerText()).includes('certificate-a.pdf'));assert((await rows.nth(1).innerText()).includes('certificate-b.pdf'));
 for(const row of await rows.all())assert((await row.innerText()).includes('Yes'));
 assert(!(await active().innerText()).includes('[object Object]'));await step();
 let lands=(await records()).filter(r=>r.land_id?.startsWith('OVERLAY-'));assert.equal(lands.length,2);assert(lands.every(r=>r.certificate_storage_id&&r.certificate_provided));assert.notEqual(lands[0].certificate_storage_id,lands[1].certificate_storage_id);
 for(const land of lands){
  const [doc]=await post('/api/shared/get-documents',{document_ids:[land.certificate_storage_id]});
  assert.equal(doc.source_filename,land.land_id==='OVERLAY-A'?'certificate-a.pdf':'certificate-b.pdf');
  const download=await context.request.get(doc.presigned_url);assert(download.ok());assert((await download.text()).includes(land.land_id));
 }
 await page.reload();await gotoSection('farmer_photo');
 await active().locator('.hdr-avatar').waitFor();
 await page.waitForFunction(()=>{const img=document.querySelector('[data-intake-form-expanded=true] .hdr-avatar');return img?.complete&&img.naturalWidth>0});
 await gotoSection('farmer_land_intake');
 await page.getByRole('link',{name:'certificate-a.pdf'}).waitFor();
 await active().screenshot({path:path.join(output,'acceptance-certificates.png')});
 const landRow=id=>rows.filter({has:page.getByText(id,{exact:true})});
 await landRow('OVERLAY-A').getByRole('button',{name:'Edit',exact:true}).click();
 const certificate=()=>page.locator('[data-widget-id$="-certificate_storage_id"]');
 await certificate().getByRole('link',{name:'certificate-a.pdf'}).waitFor();
 await certificate().getByRole('button',{name:'Remove',exact:true}).click();
 await certificate().locator('input[type=file]').setInputFiles({name:'cancelled.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nCancelled\n%%EOF')});
 await page.getByRole('button',{name:'Cancel',exact:true}).first().click();
 assert((await landRow('OVERLAY-A').innerText()).includes('certificate-a.pdf'));
 const originalCertificate=lands.find(r=>r.land_id==='OVERLAY-A').certificate_storage_id;
 await landRow('OVERLAY-A').getByRole('button',{name:'Edit',exact:true}).click();
 await certificate().getByRole('button',{name:'Remove',exact:true}).click();
 await certificate().locator('input[type=file]').setInputFiles({name:'replacement.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4\nReplacement\n%%EOF')});
 await page.getByRole('button',{name:'Save',exact:true}).click();
 await page.route('**/api/intake-form/save-intake-form-submission',route=>route.fulfill({status:500,contentType:'application/json',body:JSON.stringify({error:'Simulated certificate save failure'})}));
 await active().getByRole('button',{name:'Next',exact:true}).click();
 await page.waitForTimeout(600);
 assert.equal((await records()).find(r=>r.land_id==='OVERLAY-A').certificate_storage_id,originalCertificate);
 assert.equal(await active().getAttribute('data-section-id'),'farmer_land_intake');
 await page.unroute('**/api/intake-form/save-intake-form-submission');await step();
 lands=(await records()).filter(r=>r.land_id?.startsWith('OVERLAY-'));
 assert.notEqual(lands.find(r=>r.land_id==='OVERLAY-A').certificate_storage_id,originalCertificate);
 assert(lands.every(r=>r.certificate_provided));
 await page.reload();await gotoSection('farmer_land_intake');
 await page.getByRole('link',{name:'replacement.pdf'}).waitFor();
 await landRow('OVERLAY-A').getByRole('button',{name:'Edit',exact:true}).click();
 await certificate().getByRole('button',{name:'Remove',exact:true}).click();
 await page.getByRole('button',{name:'Save',exact:true}).click();
 assert((await landRow('OVERLAY-A').innerText()).includes('No'));assert((await landRow('OVERLAY-B').innerText()).includes('Yes'));
 await step();lands=(await records()).filter(r=>r.land_id?.startsWith('OVERLAY-'));
 assert(!lands.find(r=>r.land_id==='OVERLAY-A').certificate_storage_id);assert.equal(lands.find(r=>r.land_id==='OVERLAY-A').certificate_provided,false);
 assert(lands.find(r=>r.land_id==='OVERLAY-B').certificate_storage_id);assert.equal(lands.find(r=>r.land_id==='OVERLAY-B').certificate_provided,true);
 assert.equal(errors.length,0,errors.join('\n'));
 fs.writeFileSync(path.join(output,'browser-acceptance.json'),JSON.stringify({submission_id:sid(),checks:'photo upload/replace/failure/remove/reload; geo cascade/readback; labels; two certificate rows/save/reload/replace/cancel/failure/remove',errors},null,2));
 console.log('PASS',sid());
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
