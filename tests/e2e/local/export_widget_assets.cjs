// Run inside the pinned staff-ui image with /evidence mounted to a scratch dir.
// Copies public assets only; does not alter the image or include runtime config.
const fs = require('node:fs');
fs.cpSync('/app/.next/static', '/evidence/static', {recursive: true});
console.log('Public widget assets copied');
