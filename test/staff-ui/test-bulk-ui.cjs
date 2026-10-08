/* Execute the shipped browser script against a small DOM fixture. This checks
 * behavior without substituting for a browser run against the built image. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

function fixture(fetch) {
  const nodes = [];
  class Node {
    constructor(tag) { this.tag = tag; this.children = []; this.listeners = {}; nodes.push(this); }
    appendChild(child) { this.children.push(child); child.parent = this; }
    prepend(child) { this.children.unshift(child); child.parent = this; }
    setAttribute(key, value) { this[key] = value; }
    addEventListener(key, fn) { this.listeners[key] = fn; }
    showModal() { this.open = true; }
    close() { this.open = false; this.listeners.close?.(); }
    remove() { if (this.parent) this.parent.children = this.parent.children.filter(x => x !== this); }
    replaceChildren() { this.children = []; }
    focus() {}
    click() { return this.onclick?.(); }
  }
  const body = new Node('body'), head = new Node('head'), main = new Node('main'); body.appendChild(main);
  const document = {body, head, cookie: 'X-CSRF-Token=csrf', activeElement: main,
    createElement: tag => new Node(tag), createTextNode: text => ({textContent: text}),
    getElementById: id => nodes.find(n => n.id === id), querySelector: () => main};
  const window = {addEventListener() {}};
  const context = {document, window, location:{pathname:'/intake-form/farmer'}, MutationObserver: class {observe() {}},
    fetch, FormData, Blob, URL, setTimeout};
  vm.runInNewContext(fs.readFileSync('docker/staff-ui/assets/farmer-bulk-upload.js','utf8'), context);
  return {nodes, document};
}
const payload = value => Response.json({response_body:{response_payload:value}});

test('templates, mixed results and double-click prevention', async () => {
  let importCalls = 0, release;
  const gate = new Promise(resolve => { release = resolve; });
  const {nodes, document} = fixture(async (url, options) => {
    assert.equal(options.headers['X-CSRF-Token'], 'csrf');
    if (url.endsWith('=forms')) return payload([{form_id:'form',label:'Farmer Registration'}]);
    importCalls++;
    await gate;
    return payload({total:2,successful:1,failed:1,results:[{row:2,ok:true,submission_id:'id'},{row:3,ok:false,errors:['Bad date']}]});
  });
  await document.getElementById('farmer-bulk-open').click();
  assert.equal(nodes.filter(n => n.tag === 'a' && n.href?.includes('farmer-import-template')).length, 2);
  const input = nodes.find(n => n.type === 'file');
  input.files = [new Blob(['first_name,father_first_name\nA,B'])]; input.files[0].name='farmers.csv';
  nodes.find(n => n.tag === 'select').value='form';
  const button = nodes.find(n => n.textContent === 'Import and submit');
  const pending = button.click(); await button.click();
  assert.equal(importCalls, 1); assert.equal(button.disabled, true);
  release(); await pending;
  assert(nodes.some(n => n.textContent === '1 submitted for approval; 1 failed out of 2.'));
  assert(nodes.some(n => n.textContent === 'Bad date'));
  assert(nodes.some(n => n.href === '/tasks/intake-form/farmer/id'));
  assert(nodes.some(n => n.textContent === 'Download error report'));
  assert.equal(input.value, ''); assert.equal(button.disabled, false);
});

test('network failure clears selection and tells staff to check existing submissions', async () => {
  const {nodes, document} = fixture(async url => {
    if (url.endsWith('=forms')) return payload([{form_id:'form',label:'Farmer'}]);
    throw new TypeError('Failed to fetch');
  });
  await document.getElementById('farmer-bulk-open').click();
  const input=nodes.find(n=>n.type==='file'); input.files=[new Blob(['x'])]; input.files[0].name='a.csv';
  await nodes.find(n=>n.textContent==='Import and submit').click();
  assert.equal(input.value,'');
  assert.match(nodes.find(n=>n.role==='status').textContent,/Check intake submissions/);
});
