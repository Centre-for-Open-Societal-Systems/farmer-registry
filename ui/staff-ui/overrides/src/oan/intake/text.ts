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
