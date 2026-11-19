import { getWidgetValue } from '@openg2p/registry-widgets';
import { widgetConfig } from './widgetConfigs';

// The household roster on the members section's Next, not only on Submit.
//
// The server checks the roster when the submission is finalized
// (household_submission_validation.validate_household_roster): members entered,
// as many as the household size, exactly one head, a relationship for every
// other member, and the male/female counts. Those rules span two sections
// (Household information and Household members), so no field rule catches them
// and the officer used to learn of them only on Submit. The same rules run here,
// in the same order, with the same words the officer sees from the server
// (upstream_messages.py), so Next on the members section stops on the spot.

type Translate = (key: string) => string;

export const MEMBERS_WIDGET = 'members_table';
// Household information of the intake form (the Household register's fields).
const HOUSEHOLD = '9055ab43-c85d-4833-bd00-ca657bb72644';
const COUNT_FIELDS = {
    size: 'size_of_group',
    male: 'number_of_male_members',
    female: 'number_of_female_members',
} as const;

type Row = Record<string, unknown>;

function count(values: Record<string, unknown>, field: string): number | null {
    const config = widgetConfig(field);
    const path = (config?.['widget-data-path'] as string | undefined) ?? `${HOUSEHOLD}.${field}`;
    const value = getWidgetValue(values, path as never, field);
    if (value === null || value === undefined || value === '') return null;
    const number = Number(value);
    return Number.isInteger(number) ? number : null;
}

function isTrue(value: unknown): boolean {
    return value === true || value === 1 || (typeof value === 'string' && ['true', 'yes', '1'].includes(value.toLowerCase()));
}

function blank(value: unknown): boolean {
    return value === null || value === undefined || (typeof value === 'string' && value.trim() === '');
}

function fill(template: string, params: Record<string, string | number>): string {
    return template.replace(/\{(\w+)\}/g, (_, key: string) => String(params[key] ?? ''));
}

/** The members rows the officer has entered (rows marked for deletion left out). */
export function memberRows(values: Record<string, unknown>): Row[] {
    const config = widgetConfig(MEMBERS_WIDGET);
    if (!config) return [];
    const rows = getWidgetValue(values, config['widget-data-path'] as never, MEMBERS_WIDGET);
    return (Array.isArray(rows) ? rows : []).filter((row: Row) => row && row.edit_action !== 'DELETE');
}

/** The first roster problem, worded as the server words it, or null. */
export function rosterProblem(values: Record<string, unknown>, t: Translate): string | null {
    const members = memberRows(values);
    const size = count(values, COUNT_FIELDS.size);
    if (members.length === 0) {
        return fill(t('oan_roster_none'), { expected: size ? fill(t('oan_roster_expected'), { size }) : '' });
    }
    if (size !== null && members.length !== size) {
        return fill(t('oan_roster_count'), { entered: members.length, size });
    }
    const heads = members.filter((row) => isTrue(row.is_head)).length;
    if (heads === 0) return t('oan_roster_no_head');
    if (heads > 1) return t('oan_roster_two_heads');
    if (members.some((row) => !isTrue(row.is_head) && blank(row.relationship_to_the_head))) {
        return t('oan_roster_relationship');
    }
    const expectedMale = count(values, COUNT_FIELDS.male);
    const expectedFemale = count(values, COUNT_FIELDS.female);
    if (expectedMale === null || expectedFemale === null) return null;
    const gender = (row: Row) => String(row.gender ?? '').toUpperCase();
    const male = members.filter((row) => gender(row) === 'MALE').length;
    const female = members.filter((row) => gender(row) === 'FEMALE').length;
    if (male !== expectedMale || female !== expectedFemale) {
        return fill(t('oan_roster_genders'), { male, female, expectedMale, expectedFemale });
    }
    return null;
}
