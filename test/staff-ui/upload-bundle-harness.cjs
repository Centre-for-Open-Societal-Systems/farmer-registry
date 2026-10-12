// Execute the upload block and file deserializer from the actual Next.js bundle.
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function walk(dir) {
  return fs.readdirSync(dir, {withFileTypes: true}).flatMap(e => {
    const p = path.join(dir, e.name);
    return e.isDirectory() ? walk(p) : [p.replace(/\\/g, '/')];
  });
}

function loadUploadHarness() {
  const root = (process.env.STAFF_UI_NEXT_ROOT || '/app/.next').replace(/\\/g, '/');
  const allFiles = walk(root);
  const chunks = allFiles.filter(f => f.startsWith(`${root}/static/chunks/`) && f.endsWith('.js'));
  const matches = chunks.filter(f => fs.readFileSync(f, 'utf8').includes('filesToUpload:__fa'));
  if (matches.length !== 1) throw Error(`Expected one patched upload chunk, found ${matches.length}`);
  const chunkPath = matches[0];
  const src = fs.readFileSync(chunkPath, 'utf8');
  new Function(src); // A marker alone does not prove the whole chunk parses.
  const id = '[A-Za-z_$][A-Za-z0-9_$]*';
  const m = new RegExp(String.raw`let\{filesToUpload:__fa,fileLabels:__fl,fileTargets:__ft\}=\(0,(${id})\.YX\)\((${id})\?\.section_files\),.*?\2\.records=__rs\}`).exec(src);
  if (!m) throw Error('Cannot locate the rc.544 upload block');
  const block = m[0];
  const upload = new RegExp(String.raw`let __up=await (${id})\(`).exec(block)?.[1];
  const toast = new RegExp(String.raw`(${id})\.oR\.error\(`).exec(block)?.[1];
  const labels = new RegExp(String.raw`(${id})=__ix\.map\(i=>"_profile"`).exec(block)?.[1];
  const docs = new RegExp(String.raw`(${id})\.push\(\.\.\.__up\)`).exec(block)?.[1];
  if (![upload, toast, labels, docs].every(Boolean)) throw Error('Upload bindings changed');

  // Load webpack registrations without running React or application modules.
  // Execute only the file utility module, using the shipped YX implementation.
  let deserialize;
  for (const f of chunks) {
    const text = fs.readFileSync(f, 'utf8');
    if (!text.includes('fileTargets:') || !text.includes('existingDocuments:')) continue;
    const self = {webpackChunk_N_E: []};
    vm.runInNewContext(text, {self, File, Blob, Uint8Array, atob, console});
    for (const entry of self.webpackChunk_N_E) {
      for (const factory of Object.values(entry[1])) {
        if (!factory.toString().includes('YX:') || !factory.toString().includes('existingDocuments:')) continue;
        const exports = {};
        const requireModule = () => { throw Error('Unexpected dependency in file utility'); };
        requireModule.d = (obj, getters) => {
          for (const [key, get] of Object.entries(getters)) Object.defineProperty(obj, key, {get});
        };
        factory({}, exports, requireModule);
        deserialize = exports.YX;
      }
    }
  }
  if (!deserialize) throw Error('Cannot find the shipped file deserializer');
  const fn = new Function(m[1], m[2], upload, toast,
    `return (async()=>{${block};return {labels:${labels},docs:${docs}}})()`);
  async function run(changes, uploadFile) {
    const toasts = [];
    const out = await fn({YX: deserialize}, changes, uploadFile,
      {oR: {error: message => toasts.push(message)}});
    return {out, toasts, labels: out?.labels || [], docs: out?.docs || []};
  }
  return {root, allFiles, chunkPath, run};
}

function serializedFile(name, tag, field) {
  return {__type: 'File', name, type: 'application/octet-stream', data: 'dGVzdA==',
    lastModified: 0, tag, field, label: field || name};
}

module.exports = {loadUploadHarness, serializedFile};
