/* COSS presentation only; filenames and flags are derived from each row by
 * the guarded widget adapter. Existing document access uses the stock API. */
(() => {
 if (window.__cossIntake) return;
 window.__cossIntake = true;
 const style = document.createElement('style');
 style.textContent = `
 .header-section-widget-farmer-photo .hdr-info,
 .header-section-widget-farmer-photo .hdr-right {display:none!important}
 .header-section-widget-farmer-photo {padding-top:8px!important}
 [data-coss-document-id][role=link] {cursor:pointer;text-decoration:underline}
 `;
 document.head.appendChild(style);
 const cache = new Map();
 function token(){const m=document.cookie.match(/(?:^|; )X-CSRF-Token=([^;]*)/);return m?decodeURIComponent(m[1]):'';}
 async function refresh(){
  const ids=[...new Set([...document.querySelectorAll('[data-coss-document-id]')].map(e=>e.dataset.cossDocumentId).filter(id=>/^[0-9a-f-]{36}$/i.test(id)&&!cache.has(id)))];
  if(ids.length){
   ids.forEach(id=>cache.set(id,null));
   try{
    const response=await fetch('/api/shared/get-documents',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':token()},body:JSON.stringify({document_ids:ids})});
    if(!response.ok) throw Error('Document lookup failed');
    const docs=await response.json();
    for(const doc of Array.isArray(docs)?docs:[])cache.set(doc.document_id,doc);
   }catch{/* Leave the document reference visible; do not invent a link. */}
  }
  document.querySelectorAll('[data-coss-document-id]').forEach(el=>{
   const doc=cache.get(el.dataset.cossDocumentId);if(!doc)return;
   const name=doc.source_filename||'View document';
   // Keep React's text node, so replacing/removing a row is safe.
   if(el.childNodes.length===1&&el.firstChild.nodeType===3&&el.firstChild.nodeValue!==name)el.firstChild.nodeValue=name;
   if(doc.presigned_url){el.setAttribute('role','link');el.tabIndex=0;el.title='Open '+name;}
  });
 }
 async function open(el){
  const response=await fetch('/api/shared/get-documents',{method:'POST',credentials:'include',headers:{'Content-Type':'application/json','X-CSRF-Token':token()},body:JSON.stringify({document_ids:[el.dataset.cossDocumentId]})});
  if(!response.ok)return;
  const docs=await response.json(),doc=Array.isArray(docs)&&docs[0];if(!doc?.presigned_url)return;
  const url=new URL(doc.presigned_url,location.origin);
  if(!['http:','https:'].includes(url.protocol))return;
  window.open(url.href,'_blank','noopener,noreferrer');
 }
 document.addEventListener('click',e=>{const el=e.target.closest?.('[data-coss-document-id][role=link]');if(el)open(el);});
 document.addEventListener('keydown',e=>{if(e.key==='Enter'&&e.target.matches('[data-coss-document-id][role=link]')){e.preventDefault();open(e.target);}});
 let queued=false;
 new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(()=>{queued=false;refresh();});}}).observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['data-coss-document-id']});
 refresh();
})();
