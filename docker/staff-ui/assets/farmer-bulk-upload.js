/* Farmer intake CSV/XLSX import. No record data is saved in browser storage. */
(function () {
  'use strict';
  const API = "__FARMER_BULK_UPLOAD_ROUTE__";
  let busy = false;
  let dialog;
  let lastFocus;

  function element(tag, text, parent) {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    if (parent) parent.appendChild(node);
    return node;
  }
  function csrf() {
    const cookies = document.cookie.split(';').map(v => v.trim().split('='));
    const token = cookies.find(([key]) => key === 'X-CSRF-Token') || cookies.find(([key]) => key.endsWith('X-CSRF-Token'));
    return token ? decodeURIComponent(token.slice(1).join('=')) : '';
  }
  async function call(operation, body) {
    let response;
    try {
      response = await fetch(API + '?farmer_bulk_import=' + operation, {
        method: 'POST', credentials: 'same-origin', headers: {'X-CSRF-Token': csrf()}, body,
      });
    } catch (_) {
      throw new Error('Connection lost. Check intake submissions before retrying; some rows may have completed.');
    }
    let data;
    try { data = await response.json(); } catch (_) {
      throw new Error('The server returned an unreadable response. Check intake submissions before retrying.');
    }
    if (!response.ok || data.response_header?.response_status === 'ERROR') {
      throw new Error(data.response_header?.response_error_message || data.error || data.detail ||
        `Upload failed (${response.status}). Check intake submissions before retrying.`);
    }
    const payload = data.response_body?.response_payload;
    if (payload == null) throw new Error('No import result was returned. Check intake submissions before retrying.');
    return payload;
  }
  function downloadErrors(results) {
    const quote = value => '"' + String(value).replace(/^[=+@\-\t\r]/, "'$&").replace(/"/g, '""') + '"';
    const text = '\ufeffrow,error\r\n' + results.filter(r => !r.ok)
      .map(r => [r.row, (r.errors || []).join('; ')].map(quote).join(',')).join('\r\n');
    const url = URL.createObjectURL(new Blob([text], {type: 'text/csv;charset=utf-8'}));
    const link = element('a'); link.href = url; link.download = 'farmer-import-errors.csv'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function open() {
    if (dialog?.open) return;
    lastFocus = document.activeElement;
    dialog = element('dialog', '', document.body);
    dialog.className = 'farmer-bulk-dialog';
    dialog.setAttribute('aria-labelledby', 'farmer-bulk-title');
    element('h2', 'Bulk upload farmers', dialog).id = 'farmer-bulk-title';
    element('p', 'Upload one farmer per row. Valid rows are submitted for approval; failed rows are reported separately. Maximum 1,000 rows and 10 MB.', dialog);
    const links = element('p', '', dialog);
    for (const type of ['csv', 'xlsx']) {
      const link = element('a', `Download ${type.toUpperCase()} template`, links);
      link.href = `/farmer-import-template.${type}`; link.download = '';
      links.appendChild(document.createTextNode('  '));
    }
    const formLabel = element('label', 'Intake form ', dialog);
    const forms = element('select', '', formLabel); forms.disabled = true;
    const fileLabel = element('label', 'Spreadsheet ', dialog);
    const file = element('input', '', fileLabel); file.type = 'file'; file.accept = '.csv,.xlsx';
    const status = element('p', 'Loading intake forms…', dialog); status.setAttribute('role', 'status');
    const results = element('div', '', dialog);
    const actions = element('div', '', dialog);
    const upload = element('button', 'Import and submit', actions); upload.disabled = true;
    const close = element('button', 'Close', actions);
    close.onclick = () => { if (!busy) dialog.close(); };
    dialog.addEventListener('cancel', event => { if (busy) event.preventDefault(); });
    dialog.addEventListener('close', () => { dialog.remove(); lastFocus?.focus(); });
    dialog.showModal();
    upload.onclick = async () => {
      if (busy) return;
      const selected = file.files[0];
      if (!selected || !/\.(csv|xlsx)$/i.test(selected.name)) { status.textContent = 'Choose a CSV or XLSX file.'; return; }
      if (selected.size > 10 * 1024 * 1024) { status.textContent = 'File exceeds the 10 MB limit.'; return; }
      busy = true; upload.disabled = close.disabled = file.disabled = forms.disabled = true;
      results.replaceChildren(); status.textContent = 'Importing and submitting rows… Keep this page open.';
      try {
        const body = new FormData(); body.append('file', selected); body.append('form_id', forms.value);
        const result = await call('import', body);
        if (!Array.isArray(result.results)) throw new Error('The result is incomplete. Check intake submissions before retrying.');
        status.textContent = `${result.successful} submitted for approval; ${result.failed} failed out of ${result.total}.`;
        const table = element('table', '', results);
        const head = element('tr', '', element('thead', '', table));
        ['Row', 'Result'].forEach(label => element('th', label, head));
        const tbody = element('tbody', '', table);
        for (const row of result.results) {
          const tr = element('tr', '', tbody); element('td', String(row.row), tr);
          const td = element('td', '', tr);
          if (row.ok && row.submission_id) {
            const link = element('a', 'Submitted — view intake', td);
            const prefix = location.pathname.split('/intake-form/')[0];
            link.href = prefix + '/tasks/intake-form/farmer/' + encodeURIComponent(row.submission_id);
          } else { td.textContent = (row.errors || ['Import failed']).join('; '); }
        }
        if (result.failed) {
          const download = element('button', 'Download error report', results);
          download.onclick = () => downloadErrors(result.results);
          element('p', 'Correct the failed rows in your original file and upload only those rows.', results);
        }
        // Clear selection to prevent accidentally submitting the successful rows again.
        file.value = '';
      } catch (error) {
        status.textContent = error.message || 'Connection lost. Check intake submissions before retrying; some rows may have completed.';
        file.value = '';
      } finally { busy = false; upload.disabled = close.disabled = file.disabled = forms.disabled = false; }
    };
    try {
      const available = await call('forms');
      for (const form of available) { const option = element('option', form.label, forms); option.value = form.form_id; }
      forms.disabled = upload.disabled = !available.length;
      status.textContent = available.length ? 'Choose a file to begin.' : 'No farmer intake form is configured.';
    } catch (error) { status.textContent = error.message; }
  }
  const css = element('link', '', document.head); css.rel = 'stylesheet'; css.href = '/farmer-bulk-upload.css';
  window.addEventListener('farmer-bulk-upload', () => {
    if (/^(?:\/[a-z]{2}(?:-[a-z]{2})?)?\/intake-form\/farmer\/?$/i.test(location.pathname)) return open();
  });
  window.addEventListener('beforeunload', event => { if (busy) { event.preventDefault(); event.returnValue = ''; } });
})();
