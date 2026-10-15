// The published hub enforces HTTPS in its build-time CSP. Local Compose uses
// HTTP. Preserve every other directive, and start the original image server.
const fs = require('fs');
const path = '/app/.next/routes-manifest.json';
const manifest = JSON.parse(fs.readFileSync(path, 'utf8'));
for (const route of manifest.headers || []) {
  for (const header of route.headers || []) {
    if (header.key.toLowerCase() === 'content-security-policy') {
      header.value = header.value.replace(/upgrade-insecure-requests;?/g, '');
    }
  }
}
fs.writeFileSync(path, JSON.stringify(manifest));
require('/app/server.js');
