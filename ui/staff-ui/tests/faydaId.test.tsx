// G2R-595: the Fayda ID (FIN or FAN) field takes the whitespace around a typed
// or pasted ID off before the widget library validates and stores it.
//
// The widget is found the way the staff UI finds it: the section metadata
// (12_form_sections.sql) names the widget, the widget registry (register.ts)
// holds it. The ID is typed with a real change event on the rendered input.
// Synthetic values only.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { createElement } from 'react';
import { Provider } from 'react-redux';
import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import {
    WidgetProvider,
    createWidgetStore,
    setValues,
    widgetRegistry,
    type WidgetStore,
} from '@openg2p/registry-widgets';
import '../overrides/src/oan/widgets/register';

const SQL = path.join(
    __dirname,
    '../../../farmer-extension/src/openg2p_registry_farmer_extension/meta_data/site-configuration/12_form_sections.sql',
);
const FARMER = 'a1a4d25a-1cd4-4356-abac-985a0b3c6bcd';

/** The Fayda ID widget exactly as the section metadata stores it. */
function metadataConfig(): Record<string, any> {
    const sql = readFileSync(SQL, 'utf8');
    const at = sql.indexOf('"widget-id": "foundational_id"');
    const from = sql.lastIndexOf("'{", at) + 1;
    const to = sql.indexOf("}'),", at) + 1;
    return JSON.parse(sql.slice(from, to));
}

const translate = (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key;

function mount(config: Record<string, any>, values: Record<string, unknown> = {}) {
    const store: WidgetStore = createWidgetStore();
    store.dispatch(setValues({ [FARMER]: { has_national_id: true, ...values } } as never));
    const entry = widgetRegistry.get(config.widget);
    if (!entry) throw new Error(`no widget registered for "${config.widget}"`);
    render(
        createElement(
            Provider as never,
            { store },
            createElement(WidgetProvider as never, { store, t: translate }, createElement(entry.component as never, { config })),
        ),
    );
    return store;
}

const saved = (store: WidgetStore) => (store.getState().widget.values as any)[FARMER]?.foundational_id;
const errors = (store: WidgetStore) => (store.getState().widget.errors as any).foundational_id ?? [];
const input = () => screen.getByRole('textbox') as HTMLInputElement;
const type = (value: string) => fireEvent.change(input(), { target: { value } });

afterEach(cleanup);

describe('Fayda ID field', () => {
    it('is routed by its metadata to an OAN widget and keeps the pattern', () => {
        const config = metadataConfig();
        expect(config['widget-id']).toBe('foundational_id');
        expect(config.widget).toBe('oan-fayda-id');
        expect(widgetRegistry.has('oan-fayda-id')).toBe(true);
        expect(config['widget-data-validation'].pattern).toBe('^([0-9]{12}|[0-9]{16})$');
    });

    it.each([
        ['  123456789012', '123456789012'],
        ['123456789012 \t', '123456789012'],
        ['\n0123456789012345\r\n', '0123456789012345'],
        [' 012345678901 ', '012345678901'],
    ])('stores %j as %j and validates the trimmed value', (typed, kept) => {
        const store = mount(metadataConfig());
        type(typed);
        expect(saved(store)).toBe(kept);
        expect(errors(store)).toEqual([]);
        expect(input().value).toBe(kept);
    });

    it.each(['1234 56789012', ' 1234 56789012 ', '12345678901', '1234567890123', '12345678901a', '12345678901234567'])(
        'still refuses %j',
        (typed) => {
            const store = mount(metadataConfig());
            type(typed);
            expect(saved(store)).toBe(typed.trim());
            expect(errors(store).length).toBeGreaterThan(0);
            fireEvent.blur(input());
            expect(screen.getByText(errors(store)[0])).toBeTruthy();
        },
    );

    it('clears the value when the field is emptied, also when only whitespace is left', () => {
        const store = mount(metadataConfig(), { foundational_id: '123456789012' });
        type('   ');
        expect(saved(store) ?? null).toBeNull();
        expect(errors(store)).toEqual(['This field is required']);
    });

    it('is a labelled, required text input', () => {
        mount(metadataConfig());
        const field = screen.getByLabelText(/Fayda/i, { selector: 'input' }) as HTMLInputElement;
        expect(field).toBe(input());
        expect(field.disabled).toBe(false);
        expect(screen.getByText('*')).toBeTruthy();
    });

    it('is disabled once Fayda has verified the ID, and shows the ID only when read-only', () => {
        mount(metadataConfig(), { last_authentication_status: 'SUCCESS', foundational_id: '123456789012' });
        expect(input().disabled).toBe(true);
        cleanup();
        mount({ ...metadataConfig(), 'widget-readonly': true }, { foundational_id: '123456789012' });
        expect(screen.queryByRole('textbox')).toBeNull();
        expect(screen.getByText('123456789012')).toBeTruthy();
    });
});
