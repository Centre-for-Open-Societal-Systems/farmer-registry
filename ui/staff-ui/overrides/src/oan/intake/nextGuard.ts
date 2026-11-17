import {
    getWidgetValue,
    isWidgetValueEmpty,
    setError,
    setTouched,
    shouldEnableWidget,
    shouldRequireWidget,
    shouldShowWidget,
    validateWidget,
} from '@openg2p/registry-widgets';
import { toast } from 'react-toastify';
import { widgetConfig, type WidgetConfig } from './widgetConfigs';

// Mandatory means mandatory on Next.
//
// The widget library saves an intake section on Next with its required checks
// off (executeSectionSave with skipRequired: true), so an empty mandatory field
// let the officer move on; mandatory was checked only on Submit. This guard
// runs first, on the click of the open section's Next button, with the
// library's own exported rules (validateWidget, shouldShowWidget,
// shouldRequireWidget, the table rule of validateTableLikeWidget) and the
// required checks on. A field that fails gets the library's standard field
// error (touched + error in the store: the red message under the field), the
// first one is scrolled into view, one notification lists them all, and the
// click stops there. A section that passes goes on to the library's Next as
// before, which still runs the format checks and the save.
//
// Only what the officer can see is checked: hidden and disabled widgets are
// skipped, as the library skips them on Submit.

type Store = {
    getState: () => { widget: { values: Record<string, unknown> } };
    dispatch: (action: unknown) => unknown;
};
type Translate = (key: string) => string;

export type Problem = { widgetId: string; label: string; reason: string; element: Element };

const NEXT_BUTTON = '.intake-form-save-btn';
const SECTION_CONTENT = '.intake-form-accordion-content';
const WIDGET = '[data-widget-id]';

export function label(config: WidgetConfig, t: Translate): string {
    const raw = config['widget-label'];
    const key = typeof raw === 'string' && raw ? raw : String(config['widget-id'] ?? '');
    return t(key);
}

function isTable(config: WidgetConfig): boolean {
    const kind = config.widget;
    return kind === 'table' || kind === 'dialog-table' || Array.isArray(config['widget-data-columns']);
}

/** The first problem of one widget, by the library's rules with mandatory on. */
export function widgetProblem(config: WidgetConfig, values: Record<string, unknown>, t: Translate): string | null {
    const options = config['widget-data-options'] as never;
    if (!shouldShowWidget(options, values) || !shouldEnableWidget(options, values)) return null;
    if (config['widget-readonly']) return null;
    const id = String(config['widget-id'] ?? '');
    const value = getWidgetValue(values, config['widget-data-path'] as never, id);
    if (isTable(config)) {
        const rows = (Array.isArray(value) ? value : []).filter(
            (row: Record<string, unknown>) => row?.edit_action !== 'DELETE');
        if (config['widget-required'] && rows.length === 0) return t('oan_intake_add_one_row');
        const columns = (config['widget-data-columns'] as WidgetConfig[]) || [];
        for (let index = 0; index < rows.length; index++) {
            for (const column of columns) {
                const key = column['column-key'];
                if (column['widget-readonly'] || typeof key !== 'string') continue;
                const validation = column['widget-data-validation'] as Record<string, unknown> | undefined;
                const required = !!(column['widget-required'] || validation?.required);
                const errors = validateWidget(rows[index][key], validation as never, required);
                if (errors.length > 0) {
                    const reason = required && isWidgetValueEmpty(rows[index][key]) ? t('oan_intake_required') : errors[0];
                    return `${t('oan_intake_row')} ${index + 1}, ${label(column, t)}: ${reason}`;
                }
            }
        }
        return null;
    }
    const required = shouldRequireWidget(options, values, Boolean(config['widget-required']));
    const errors = validateWidget(value, config['widget-data-validation'] as never, required);
    if (errors.length === 0) return null;
    return required && isWidgetValueEmpty(value) ? t('oan_intake_required') : errors[0];
}

/** Every problem of the widgets shown in one open section, in screen order. */
export function sectionProblems(content: Element, values: Record<string, unknown>, t: Translate): Problem[] {
    const problems: Problem[] = [];
    const seen = new Set<string>();
    for (const element of Array.from(content.querySelectorAll(WIDGET))) {
        const widgetId = element.getAttribute('data-widget-id') || '';
        if (!widgetId || seen.has(widgetId)) continue;
        seen.add(widgetId);
        const config = widgetConfig(widgetId);
        if (!config) continue;
        const reason = widgetProblem(config, values, t);
        if (reason) problems.push({ widgetId, label: label(config, t), reason, element });
    }
    return problems;
}

/** "2 fields need attention: Fayda ID (Enter a 12-digit FIN …), Kebele (required)". */
export function summary(problems: Problem[], t: Translate): string {
    const items = problems.map((p) => `${p.label} (${p.reason})`);
    if (items.length === 1) return `${t('oan_intake_one_field')}: ${items[0]}`;
    return `${items.length} ${t('oan_intake_fields')}: ${items.join(', ')}`;
}

export function showProblems(store: Store, problems: Problem[], t: Translate): void {
    for (const p of problems) {
        store.dispatch(setTouched({ widgetId: p.widgetId, touched: true }));
        store.dispatch(setError({ widgetId: p.widgetId, errors: [p.reason] }));
    }
    const first = problems[0]?.element as HTMLElement | undefined;
    if (first) {
        first.scrollIntoView({ behavior: 'smooth', block: 'center' });
        first.querySelector<HTMLElement>('input, select, textarea, button')?.focus({ preventScroll: true });
    }
    toast.error(summary(problems, t), { position: 'top-right', autoClose: 8000, toastId: 'oan-intake-next' });
}

/**
 * Listen, in the capture phase, for the Next button of an intake section inside
 * `root`, and stop the click when the open section has a problem. Returns the
 * function that removes the listener.
 */
export function installNextGuard(root: Element, store: Store, t: Translate): () => void {
    const onClick = (event: Event) => {
        const target = event.target as Element | null;
        const button = target?.closest?.(NEXT_BUTTON);
        if (!button || !root.contains(button)) return;
        const content = button.closest(SECTION_CONTENT);
        if (!content) return;
        const problems = sectionProblems(content, store.getState().widget.values, t);
        if (problems.length === 0) return;
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
        showProblems(store, problems, t);
    };
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
}
