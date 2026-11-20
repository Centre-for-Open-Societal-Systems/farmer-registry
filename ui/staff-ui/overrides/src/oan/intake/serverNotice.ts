import { setError, setTouched } from '@openg2p/registry-widgets';
import { toast } from 'react-toastify';
import { widgetConfig } from './widgetConfigs';
import { label } from './nextGuard';

// A refusal from the server, said the way the Next guard says its own.
//
// The staff UI's fetch hook (upstream src/shared/hooks/useFetch.ts) shows every
// failed request as `${code} - ${message}`, e.g. "REQ-VAL-001 - Personal
// information: First name (English) is required. Fill it in before pressing
// Next.; Personal information: Gender is required. …". This keeps that
// notification and its call site, and only changes what it says: the error
// code is dropped, a message listing several problems becomes "N fields need
// attention: …", and each field the message names that is on screen gets the
// standard field error, so the officer sees it at the field too.

type Store = { dispatch: (action: unknown) => unknown };
type Translate = (key: string) => string;

const CODE_PREFIX = /^[A-Z][A-Z0-9]*(?:[-_][A-Z0-9]+)+\s+-\s+/;

export function plainMessage(message: string): string {
    return message.replace(CODE_PREFIX, '').trim();
}

/** "Personal information: First name (English) is required. Fill it in before pressing Next." →
 *  "First name (English) is required" */
export function part(message: string): string {
    const withoutSection = message.replace(/^[^:]{1,80}:\s+/, '');
    return withoutSection.split(/\.\s/)[0].replace(/\.$/, '').trim();
}

export function plainSummary(message: string, t: Translate): string {
    const parts = plainMessage(message).split(/;\s+/).map((p) => p.trim()).filter(Boolean);
    if (parts.length <= 1) return parts[0] ?? '';
    return `${parts.length} ${t('oan_intake_fields')}: ${parts.map(part).join('; ')}`;
}

/** The on-screen widgets whose label a refusal names, with the sentence that names each. */
export function namedWidgets(message: string, t: Translate): { widgetId: string; reason: string }[] {
    const parts = plainMessage(message).split(/;\s+/);
    const found: { widgetId: string; reason: string }[] = [];
    for (const element of Array.from(document.querySelectorAll('.intake-form-accordion-content [data-widget-id]'))) {
        const widgetId = element.getAttribute('data-widget-id') || '';
        const config = widgetConfig(widgetId);
        if (!config) continue;
        const name = label(config, t);
        if (!name) continue;
        const hit = parts.find((p) => p.includes(name));
        if (hit && !found.some((f) => f.widgetId === widgetId)) found.push({ widgetId, reason: part(hit) });
    }
    return found;
}

let installed = false;

/** Reword the error notifications once for the page, and mark the fields they name in `getStore()`'s form. */
export function installServerNotice(getStore: () => Store | null, t: () => Translate): void {
    if (installed) return;
    installed = true;
    const original = toast.error.bind(toast);
    const reworded = ((content: unknown, options?: unknown) => {
        if (typeof content !== 'string' || !CODE_PREFIX.test(content)) {
            return original(content as never, options as never);
        }
        const translate = t();
        const store = getStore();
        if (store) {
            for (const { widgetId, reason } of namedWidgets(content, translate)) {
                store.dispatch(setTouched({ widgetId, touched: true }));
                store.dispatch(setError({ widgetId, errors: [reason] }));
            }
        }
        return original(plainSummary(content, translate) as never, { autoClose: 8000, ...(options as object) } as never);
    }) as typeof toast.error;
    (toast as unknown as { error: typeof toast.error }).error = reworded;
}
