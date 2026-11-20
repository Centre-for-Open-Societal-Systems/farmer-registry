// The words of the intake Next guard and server notice. A key present in the
// registry's translations wins (so Amharic and Afaan Oromo can be added there);
// these English texts are the fallback, so a missing translation never shows a
// key.
const ENGLISH: Record<string, string> = {
    oan_intake_required: 'required',
    oan_intake_row: 'Row',
    oan_intake_add_one_row: 'add at least one row',
    oan_intake_one_field: '1 field needs attention',
    oan_intake_fields: 'fields need attention',
    // The household roster (roster.ts), in the server's words (upstream_messages.py).
    oan_roster_none: 'Household members: none are entered{expected}. Add every member, including the head, before submitting.',
    oan_roster_expected: ' ({size} expected)',
    oan_roster_count:
        'Household members: {entered} entered, but the household size is {size}. Add or remove members, or correct the household size, so they match.',
    oan_roster_no_head: 'Household members: no member is marked as the head. Tick Head of household for the head.',
    oan_roster_two_heads:
        'Household members: more than one member is marked as the head. Tick Head of household for one member only.',
    oan_roster_relationship:
        'Relationship to the head: missing for a member who is not the head. Pick it for every other member.',
    oan_roster_genders:
        "Household members: {male} male and {female} female are entered, but the household says {expectedMale} male and {expectedFemale} female. Correct the members' gender or the household's counts so they match.",
};

type Translations = ((key: string) => string) & { has?: (key: string) => boolean };

/** A translate function that never shows a raw key: translation, else English, else the text itself. */
export function intakeText(translations: Translations): (key: string) => string {
    return (key: string) => {
        if (!key) return '';
        try {
            if (translations.has?.(key)) return translations(key);
        } catch {
            // next-intl throws for some malformed keys (a label with a dot or colon); fall through.
        }
        return ENGLISH[key] ?? key;
    };
}
