// Behaviour of docker/staff-ui/assets/farmer-intake-rules.js against DOM
// fixtures shaped like the staff-ui 1.2.1 markup it drives (widget-container /
// data-widget-id, table-cell-field, table-cell-actions, owt-field-error), as
// read off the running portal.
//
// USAGE: needs jsdom, which this repo does not otherwise depend on:
//   npm i --no-save jsdom   (or point NODE_PATH at a node_modules that has it)
//   node --test test/staff-ui/intake-rules.test.js

const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const SCRIPT = fs.readFileSync(
  path.join(__dirname, "..", "..", "docker", "staff-ui", "assets", "farmer-intake-rules.js"),
  "utf8"
);

// Every window is closed after its test: its observer and animation-frame
// loop would otherwise keep the runner alive.
const open = [];
test.afterEach(() => { while (open.length) open.pop().window.close(); });

function page(body) {
  // Errors from a window already closed by afterEach (its observer firing
  // on a torn-down document) are noise; anything else is reported.
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => { if (!dom.window.document) return; console.error(e); });
  const dom = new JSDOM(`<!doctype html><html><head></head><body>${body}</body></html>`, {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    virtualConsole,
  });
  open.push(dom);
  dom.window.eval(SCRIPT);
  return dom;
}

const tick = (dom, ms = 30) => new Promise((r) => dom.window.setTimeout(r, ms));

function type(dom, input, value) {
  const { window } = dom;
  const proto = input instanceof window.HTMLSelectElement ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value").set.call(input, value);
  input.dispatchEvent(new window.Event("input", { bubbles: true }));
  input.dispatchEvent(new window.Event("change", { bubbles: true }));
}

function click(dom, el) {
  el.dispatchEvent(new dom.window.MouseEvent("click", { bubbles: true, cancelable: true }));
}

const widget = (id, inner = '<input type="text" value="">') =>
  `<div class="widget-container" data-widget-id="${id}">${inner}</div>`;

const cell = (control) => `<td><div class="table-cell-field w-full">${control}</div></td>`;

/* ------------------------------------------------------ family size */

test("spreadsheet picker is not cleared by document upload validation", () => {
  const dom = page('<dialog class="farmer-bulk-dialog"><input type="file" accept=".csv,.xlsx"></dialog>');
  const input = dom.window.document.querySelector('input');
  for (const extension of ['csv', 'xlsx']) {
    Object.defineProperty(input, 'files', {configurable:true, value:[new dom.window.File(['data'], `farmers.${extension}`)]});
    let cleared = false, delivered = false;
    Object.defineProperty(input, 'value', {configurable:true, set() { cleared = true; }});
    input.addEventListener('change', () => { delivered = true; }, {once:true});
    input.dispatchEvent(new dom.window.Event('change', {bubbles:true}));
    assert.equal(cleared, false);
    assert.equal(delivered, true);
  }
});

test("Family Size fills from Females alone; children are not added", async () => {
  const dom = page(`<div class="section" data-section-id="farmer_household_information">
    ${widget("number_of_male_members")}${widget("number_of_female_members")}
    ${widget("number_of_children")}${widget("size_of_group")}</div>`);
  const $ = (id) => dom.window.document.querySelector(`[data-widget-id="${id}"] input`);
  type(dom, $("number_of_female_members"), "5");
  await tick(dom);
  type(dom, $("number_of_children"), "4");
  await tick(dom);
  assert.equal($("size_of_group").value, "5");
  type(dom, $("number_of_male_members"), "2");
  await tick(dom);
  assert.equal($("size_of_group").value, "7");
});

test("a Family Size the enumerator typed is never overwritten", async () => {
  const dom = page(`<div class="section" data-section-id="farmer_household_information">
    ${widget("number_of_male_members")}${widget("number_of_female_members")}
    ${widget("number_of_children")}${widget("size_of_group")}</div>`);
  const $ = (id) => dom.window.document.querySelector(`[data-widget-id="${id}"] input`);
  type(dom, $("size_of_group"), "9");
  await tick(dom);
  type(dom, $("number_of_female_members"), "5");
  await tick(dom);
  assert.equal($("size_of_group").value, "9");
});

/* ------------------------------------------------------ required fields */

const PERSONAL = `<div class="section" data-section-id="farmer_personal_information">
  <div class="widget-container" data-widget-id="first_name">
    <input class="owt-field-input owt-field-input-error" type="text" value="">
    <p class="owt-field-error text-sm mt-1">This field is required</p></div>
  <div class="widget-container" data-widget-id="last_name">
    <input class="owt-field-input owt-field-input-error" type="text" value="Ab1">
    <p class="owt-field-error text-sm mt-1">Use letters only</p></div>
  <button type="button">Next →</button></div>`;

test("'required' stays hidden until Next, format errors do not", async () => {
  const dom = page(PERSONAL);
  const doc = dom.window.document;
  await tick(dom);
  const [required, format] = doc.querySelectorAll("p.owt-field-error");
  const visible = (el) => dom.window.getComputedStyle(el).display !== "none";
  assert.equal(visible(required), false, "required message shown before Next");
  assert.equal(visible(format), true, "format message must show as they type");
  const emptyInput = doc.querySelector('[data-widget-id="first_name"] input');
  assert.notEqual(dom.window.getComputedStyle(emptyInput).borderColor, "red");
  assert.equal(emptyInput.dataset.farEmpty, "1");

  click(dom, doc.querySelector("button"));
  await tick(dom);
  assert.equal(visible(required), true, "required message hidden after Next");
  assert.ok(doc.querySelector(".section").hasAttribute("data-far-tried"));
});

// As the portal draws it: a red asterisk in the label marks a required field.
const REQUIRED_SECTION = `<div class="section" data-section-id="farmer_personal_information">
  <div class="widget-container" data-widget-id="first_name">
    <label><span>First Name (English)</span><span class="owt-field-required">*</span></label>
    <input class="owt-field-input owt-field-input-error" type="text" value=""></div>
  <div class="widget-container" data-widget-id="middle_name">
    <label><span>Middle Name (English)</span></label><input type="text" value=""></div>
  <button type="button">Next →</button></div>`;

test("Next is held while a required field is blank, and says why", async () => {
  const dom = page(REQUIRED_SECTION);
  const doc = dom.window.document;
  await tick(dom);
  const first = doc.querySelector('[data-widget-id="first_name"] input');
  const notes = () => [...doc.querySelectorAll(".far-rule-error")].map((p) => p.textContent);

  assert.equal(saveReaches(dom, doc.querySelector("button")), false, "Next went through with First Name blank");
  assert.deepEqual(notes(), ["This field is required"], "only the required field is flagged");
  assert.equal(doc.activeElement, first);

  type(dom, first, "Abebe");
  await tick(dom);
  assert.deepEqual(notes(), [], "the note stays after the field is filled");
  assert.equal(saveReaches(dom, doc.querySelector("button")), true, "Next held with every required field filled");
});

test("Previous is never held", async () => {
  const dom = page(REQUIRED_SECTION.replace("Next →", "← Previous"));
  assert.equal(saveReaches(dom, dom.window.document.querySelector("button")), true);
});

test("a message the widget draws later is tagged in the same frame", async () => {
  const dom = page(`<div class="section" data-section-id="farmer_personal_information">
    <div class="widget-container" data-widget-id="first_name"><input type="text" value=""></div></div>`);
  const doc = dom.window.document;
  const p = doc.createElement("p");
  p.className = "owt-field-error";
  p.textContent = "This field is required";
  doc.querySelector(".widget-container").appendChild(p);
  await Promise.resolve(); // MutationObserver microtask, before any frame
  assert.equal(p.dataset.farRequired, "1");
});

/* ------------------------------------------- registrant IDs */

function regIds(dom) {
  return dom.window.document.querySelector('[data-section-id="farmer_reg_ids"]');
}

const REG_IDS = `<div class="section" data-section-id="farmer_reg_ids"><div class="table-widget-container"><table>
  <thead><tr><th title="Id Type">Id Type</th><th title="Value">Value</th><th title="Status">Status</th>
  <th title="Expiry Date (GC)">Expiry Date (GC)</th><th>Actions</th></tr></thead>
  <tbody><tr>
    ${cell('<select><option value="">Select</option><option value="UID">UID</option><option value="RID">RID</option></select>')}
    ${cell('<input type="text" value="">')}
    ${cell('<select><option value="">Select</option><option value="VALID">VALID</option><option value="INVALID">INVALID</option></select>')}
    ${cell('<input type="text" value="">')}
    <td><div class="table-cell-actions"><button type="button">Save</button><button type="button">Cancel</button></div></td>
  </tr></tbody></table></div></div>`;

function regRow(dom) {
  const tr = regIds(dom).querySelector("tbody tr");
  const [type, value, status, expiry] = tr.querySelectorAll("select, input");
  const save = tr.querySelector(".table-cell-actions button");
  const errors = () => [...tr.querySelectorAll(".far-rule-error")].map((p) => p.textContent);
  return { type, value, status, expiry, save, errors };
}

function saveReaches(dom, button) {
  let reached = false;
  dom.window.document.body.addEventListener("click", () => { reached = true; });
  click(dom, button);
  return reached;
}

test("a UID Value of spaces says why and holds the row Save", async () => {
  const dom = page(REG_IDS);
  const r = regRow(dom);
  type(dom, r.type, "UID");
  type(dom, r.value, "   ");
  await tick(dom);
  assert.deepEqual(r.errors(), ["ID Value is required"]);
  assert.equal(saveReaches(dom, r.save), false);
});

test("a 12-digit UID is refused as an RID, a 29-digit RID is not", async () => {
  const dom = page(REG_IDS);
  const r = regRow(dom);
  type(dom, r.type, "RID");
  type(dom, r.value, "123456789012");
  await tick(dom);
  assert.match(r.errors()[0], /Not a valid RID/);
  assert.equal(saveReaches(dom, r.save), false);

  type(dom, r.value, "1".repeat(29));
  await tick(dom);
  assert.deepEqual(r.errors(), []);
  assert.equal(saveReaches(dom, r.save), true);
});

test("ET-NID-100001 is explained as not a UID, not silently refused", async () => {
  const dom = page(REG_IDS);
  const r = regRow(dom);
  type(dom, r.type, "UID");
  type(dom, r.value, "ET-NID-100001");
  await tick(dom);
  assert.match(r.errors()[0], /12-digit FIN or the 16-digit FAN/);
});

test("an expired ID cannot be saved as Valid", async () => {
  const dom = page(REG_IDS);
  const r = regRow(dom);
  type(dom, r.type, "UID");
  type(dom, r.value, "123456789012");
  type(dom, r.status, "VALID");
  type(dom, r.expiry, "2018-09-26");
  await tick(dom);
  assert.deepEqual(r.errors(), ["This ID has expired, so its Status cannot be Valid"]);
  assert.equal(saveReaches(dom, r.save), false);
  type(dom, r.status, "INVALID");
  await tick(dom);
  assert.deepEqual(r.errors(), []);
});

/* ------------------------------------------------------ crop rows */

test("a crop row with no Commodity or Season is held with reasons", async () => {
  const dom = page(`<div class="section" data-section-id="farmer_crops"><div class="table-widget-container"><table>
    <thead><tr><th title="Commodity">Commodity</th><th title="Season">Season</th><th>Actions</th></tr></thead>
    <tbody><tr>
      ${cell('<select><option value="">Select</option><option value="TEFF">TEFF</option></select>')}
      ${cell('<select><option value="">Select</option><option value="MEHER">MEHER</option></select>')}
      <td><div class="table-cell-actions"><button type="button">Save</button></div></td>
    </tr></tbody></table></div></div>`);
  const tr = dom.window.document.querySelector("tbody tr");
  const save = tr.querySelector(".table-cell-actions button");
  assert.equal(saveReaches(dom, save), false);
  const errors = [...tr.querySelectorAll(".far-rule-error")].map((p) => p.textContent);
  assert.deepEqual(errors, ["Commodity is required", "Season is required"]);
  const [commodity, season] = tr.querySelectorAll("select");
  type(dom, commodity, "TEFF");
  type(dom, season, "MEHER");
  await tick(dom);
  assert.equal(saveReaches(dom, save), true);
});

/* ------------------------------------------------------ dialog-table file names */

test("a certificate re-picked in Edit shows its own name in that row", async () => {
  const dom = page(`<div class="section" data-section-id="farmer_land_intake">
    <button type="button">Add Record</button>
    <div class="table-widget-container"><table>
      <thead><tr><th title="Land Id">Land Id</th><th title="Land Certificate">Land Certificate</th><th>Actions</th></tr></thead>
      <tbody>
        <tr><td>LAN-001</td><td>[object Object]</td><td><button type="button">Edit</button></td></tr>
        <tr><td>LAN-002</td><td>[object Object]</td><td><button type="button">Edit</button></td></tr>
      </tbody></table></div></div>
    <div id="dialog"></div>`);
  const { window } = dom;
  const doc = window.document;
  const rows = () => [...doc.querySelectorAll("tbody tr")].map((tr) => tr.children[1].textContent);

  function openDialog(n) {
    doc.getElementById("dialog").innerHTML =
      `<div class="widget-container" data-widget-id="lands_table-dlg-${n}-certificate_storage_id">
         <div class="flex-1"><input type="file"></div></div><button type="button" id="dlg-save">Save</button>`;
  }
  function pick(name) {
    const input = doc.querySelector('#dialog input[type="file"]');
    const file = new window.File(["x"], name, { type: "image/jpeg" });
    Object.defineProperty(input, "files", { value: [file], configurable: true });
    input.dispatchEvent(new window.Event("change", { bubbles: true }));
  }

  // Row 1 was saved with cert-one.jpg; now Edit it and pick cert-two.jpg.
  click(dom, doc.querySelectorAll("tbody tr")[0].querySelector("button"));
  openDialog(3);
  pick("cert-two.jpg");
  click(dom, doc.getElementById("dlg-save"));
  doc.getElementById("dialog").innerHTML = "";
  await tick(dom, 60);
  assert.equal(rows()[0], "cert-two.jpg");

  // A different row is not given that name.
  click(dom, doc.querySelectorAll("tbody tr")[1].querySelector("button"));
  openDialog(4);
  pick("deed-b.pdf");
  click(dom, doc.getElementById("dlg-save"));
  doc.getElementById("dialog").innerHTML = "";
  await tick(dom, 60);
  assert.deepEqual(rows(), ["cert-two.jpg", "deed-b.pdf"]);
});

test("once React writes the saved document id, the cell is React's again", async () => {
  const dom = page(`<div class="section" data-section-id="farmer_land_intake"><div class="table-widget-container"><table>
    <thead><tr><th title="Land Certificate">Land Certificate</th></tr></thead>
    <tbody><tr><td>[object Object]</td></tr></tbody></table></div></div>`);
  const td = dom.window.document.querySelector("tbody td");
  const reactNode = td.firstChild;
  await tick(dom, 60);
  assert.notEqual(td.textContent, "[object Object]");
  assert.equal(td.firstChild, reactNode, "the text node React owns must be kept, not replaced");
  reactNode.nodeValue = "not-a-uuid-but-a-real-value"; // what React does on re-render
  await tick(dom, 60);
  assert.equal(td.textContent, "not-a-uuid-but-a-real-value");
});
