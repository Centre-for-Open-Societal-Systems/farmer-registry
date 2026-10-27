import React from 'react';
import {createRoot} from 'react-dom/client';
import {Provider} from 'react-redux';
import {createWidgetStore, setValues} from 'real-registry-widgets';
import {IdentityVerificationWidget} from '../../overrides/src/oan/widgets/IdentityVerificationWidget';
import {collectFaydaFin} from '../../overrides/src/oan/widgets/faydaPopup';
const test = window as any;
test.requests = [];
test.mode = 'success';
test.store = createWidgetStore();
test.seed = (value: any) => test.store.dispatch(setValues(value));
test.collectFaydaFin = collectFaydaFin;
test.testContext = {t: (key: string, opts: any) => opts?.defaultValue ?? key, schemaData: {}, dataSourceRequestHandler: async (...args: any[]) => {
    test.requests.push(args);
    if (test.mode === 'throw') throw new Error('Fixture unavailable');
    if (args[1].endsWith('/start')) {
        if (test.mode === 'no-url') return null;
        return {verification_id: 'v-1', authorization_url: location.origin+'/authorization.html'};
    }
    return {verification_id: 'v-1', status: test.mode === 'close' ? 'PENDING' : test.mode === 'failure' ? 'FAILURE' : 'SUCCESS', message: 'Provider rejected fixture', foundational_id: '001234567890', values: {}};
}};
const config = {'widget-id':'test-fayda','widget-label':'Fayda verification',
    'widget-data-path':{foundationalId:'farmer.fin',verificationId:'farmer.proof',status:'farmer.status',verifiedOn:'farmer.date',expiresOn:'farmer.expiry'},
    'widget-data-options':{registerId:'test-register',foundationalIdPath:'farmer.fin',fieldPrefix:'farmer'}};
createRoot(document.getElementById('root')!).render(<Provider store={test.store}><IdentityVerificationWidget config={config}/></Provider>);
