#!/usr/bin/env node
/* Extend the existing multipart document route, preserving its normal POST.
 * Reuse the built Next route rather than fabricating a route manifest/module.
 * Fail closed if a platform upgrade changes the route/module shape. */
const fs = require('fs');
const path = require('path');
const ROOT = process.env.STAFF_UI_NEXT_ROOT || '/app/.next';
const PUBLIC = process.env.STAFF_UI_BULK_SCRIPT || '/app/public/farmer-bulk-upload.js';
const PROXY = process.env.STAFF_UI_BULK_PROXY || '/app/farmer-bulk-proxy.cjs';

const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, 'server/app-paths-manifest.json'), 'utf8'));
const routes = Object.entries(manifest).filter(([key]) => /^\/api\//.test(key) && /upload/i.test(key) && /document/i.test(key));
if (routes.length !== 1) throw new Error(`Expected one document upload API route, found ${routes.length}`);
const [route, file] = routes[0];
const target = path.join(ROOT, 'server', file);
const source = fs.readFileSync(target, 'utf8');
const userland = /userland:([A-Za-z_$][A-Za-z0-9_$]*)/g;
const matches = [...source.matchAll(userland)];
if (matches.length !== 1 || !source.includes('AppRouteRouteModule')) {
  throw new Error('Upload route must contain exactly one AppRouteRouteModule userland binding');
}
const patched = source.replace(userland, (_, binding) =>
  `userland:{...${binding},POST:async(...__bulkArgs)=>new URL(__bulkArgs[0].url).searchParams.has("farmer_bulk_import")?require(${JSON.stringify(PROXY)}).POST(...__bulkArgs):${binding}.POST(...__bulkArgs)}`);
new Function(patched); // refuse to ship a syntax error
fs.writeFileSync(target, patched);
const script = fs.readFileSync(PUBLIC, 'utf8');
if (!script.includes('"__FARMER_BULK_UPLOAD_ROUTE__"')) throw new Error('Bulk UI route placeholder is missing');
fs.writeFileSync(PUBLIC, script.replace('"__FARMER_BULK_UPLOAD_ROUTE__"', JSON.stringify(route.replace(/\/route$/, ''))));
console.log(`Farmer bulk import uses ${route.replace(/\/route$/, '')}`);

// Render the entry inside React's existing Import from file group, on both
// server and client. No body-level button or DOM mutation during hydration.
function patchMenu(source) {
  const marker = 'case"IMPORT_FILE":';
  const at = source.indexOf(marker);
  const end = source.indexOf('case"VERIFIABLE_CREDENTIAL":', at);
  if (at < 0 || end < 0 || source.indexOf(marker, at + 1) !== -1) throw new Error('Intake import switch changed');
  const before = source.slice(0, at);
  const id = '[A-Za-z_$][A-Za-z0-9_$]*';
  const register = [...before.matchAll(new RegExp(`,(${id})=${id}\\?\\.register_id,`, 'g'))].at(-1)?.[1];
  const options = [...before.matchAll(new RegExp(`\\{importFileOptions:(${id}),`, 'g'))].at(-1)?.[1];
  const original = source.slice(at + marker.length, end);
  const jsx = original.match(new RegExp(`\\(0,(${id})\\.jsx\\)`))?.[1];
  if (!register || !options || !jsx) throw new Error('Intake import bindings changed');
  const button = `(0,${jsx}.jsx)("button",{type:"button",id:"farmer-bulk-open",className:"w-full text-left px-4 py-1 font-medium hover:bg-secondary-second cursor-pointer text-[16px]",onClick:()=>window.dispatchEvent(new Event("farmer-bulk-upload")),children:"Bulk upload farmers (CSV / XLSX)"})`;
  const entry = `if(${register}==="a1a4d25a-1cd4-4356-abac-985a0b3c6bcd")return (0,${jsx}.jsxs)("div",{children:[${button},${options}?.length?(()=>{${original}})():null]});`;
  return before + marker + entry + source.slice(at + marker.length);
}
let menus = 0;
function walk(directory) {
  for (const entry of fs.readdirSync(directory, {withFileTypes:true})) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) { walk(file); continue; }
    if (!file.endsWith('.js')) continue;
    const original = fs.readFileSync(file, 'utf8');
    if (!original.includes('viewStorageKey:"intakeFormView"')) continue;
    const result = patchMenu(original);
    new Function(result);
    fs.writeFileSync(file, result); menus++;
  }
}
walk(ROOT);
if (menus < 2) throw new Error(`Expected server and client intake menus, found ${menus}`);
console.log(`Farmer bulk upload added to ${menus} intake menus`);
