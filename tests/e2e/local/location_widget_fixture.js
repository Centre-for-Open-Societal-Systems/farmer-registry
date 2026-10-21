// Exercise the actual rc.544 exports without Next login or a deployed backend.
// Export keys/module IDs deliberately fail when the pinned UI bundle changes.
window.mount = function(kind, readonly, record) {
  window.store = widgets.Q8(); window.saved = []; window.calls = []; window.advanced = false;
  const section = JSON.parse(JSON.stringify(schemas[kind]));
  window.widgetRoot?.unmount(); window.widgetRoot = dom.createRoot(document.getElementById('root'));
  const register = kind === 'livestock' ? '4bcb88a3-fc5e-44d2-abc6-e2c68670c5bb' : 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';
  const schemaData = {[register]: record || {}};
  const handler = async(service, endpoint, method, body) => {
    calls.push({service, endpoint, body});
    const response = await fetch('/fixture/' + endpoint, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
    });
    if (!response.ok) throw Error('Geography lookup failed: ' + response.status);
    return await response.json();
  };
  const props = {section, mode:'IntakeForm', isDraft:!readonly, hideEditButton:readonly,
    sectionIndex:0, sectionCount:2, expandedSectionIndex:0, sectionRegisterId:register, schemaData,
    dataSourceRequestHandler:handler, onSectionSave:async changes => {saved.push(changes)},
    onSectionSaveSuccess:() => {window.advanced = true}};
  widgetRoot.render(React.createElement(widgets.q_, {
    store, schemaData, dataSourceRequestHandler:handler, t:k=>k
  }, React.createElement(widgets.pR, props)));
};
