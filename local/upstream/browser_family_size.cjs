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
   if(!r.ok)throw Error('API '+r.status+': '+await r.text());return r.json();
  },{endpoint,data});
 }
 const sid=()=>new URL(page.url()).searchParams.get('sid');
 async function records(){const data=await post('/api/intake-form/get-intake-form-submission',{submission_id:sid()});return data.section_payloads.flatMap(s=>s.records||[]);}

 await active().locator('select').first().selectOption('true');await step();
 assert.equal(await active().getAttribute('data-section-id'),'farmer_household_information');
 assert.equal(await active().locator('[data-widget-id=size_of_group]').count(),0);
 await input('number_of_male_members').fill('2');await input('number_of_female_members').fill('3');await input('number_of_children').fill('1');
 await step();
 await step();await step();
 await input('first_name').fill('Familysizeacceptance');await input('last_name').fill('Local');await input('father_first_name').fill('Testfather');await step();
 await page.waitForURL('**/*?sid=*');
 let household=(await records()).find(r=>r.number_of_male_members===2);
 assert(household);assert.equal(household.size_of_group,5);
 await gotoSection('farmer_household_information');await input('number_of_female_members').fill('4');await step();
 household=(await records()).find(r=>r.number_of_male_members===2);assert.equal(household.size_of_group,6);
 await page.reload();await gotoSection('farmer_household_information');
 assert.equal(await active().locator('[data-widget-id=size_of_group]').count(),0);
 assert.equal(await input('number_of_male_members').inputValue(),'2');assert.equal(await input('number_of_female_members').inputValue(),'4');
 assert.equal((await records()).find(r=>r.number_of_male_members===2).size_of_group,6);
 assert.deepEqual(errors,[]);
 console.log('PASS derived Family Size',sid());
 fs.writeFileSync(path.join(output,'family-size-acceptance.json'),JSON.stringify({submission_id:sid(),size_of_group:6,checks:'Family Size hidden; 2 + 3 = 5; changed to 2 + 4 = 6; reload persisted counts'},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
