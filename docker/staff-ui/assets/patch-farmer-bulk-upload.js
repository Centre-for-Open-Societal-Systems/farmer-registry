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
