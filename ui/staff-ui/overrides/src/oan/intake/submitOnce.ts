// One Submit per confirmation.
//
// The intake form asks "Are you sure?" before it submits (upstream
// useIntakeFormSectionAction: ActionModal with onConfirm). The dialog closes
// only after React re-renders, so a quick second click on its Submit button
// started a second finalize; the server now refuses that one ("Already
// submitted on ..."), and this stops the click before it is sent. The first
// click on a dialog's confirm button goes through; another click on the same
// button while the dialog still asks the same question is dropped. The next
// dialog (the success notice, or a new confirmation) has a new title or a new
// button, so it is not affected.

const DIALOG = '.fixed.inset-0';
const ACTIONS = 'div.flex.gap-4.w-full.justify-center';
const INTAKE_FORM = '.intake-form-accordion-content';

const answered = new WeakMap<Element, string>();
let installed = false;

/** The confirm button of an open dialog on an intake form page, or null. */
export function confirmButton(target: Element | null): Element | null {
    const button = target?.closest?.('button') ?? null;
    if (!button || !document.querySelector(INTAKE_FORM)) return null;
    const actions = button.parentElement;
    if (!actions?.matches(ACTIONS) || actions.lastElementChild !== button) return null;
    return button.closest(DIALOG) ? button : null;
}

/** True for a repeat click on a confirm button already clicked for the same question. */
export function isRepeat(button: Element): boolean {
    const question = button.closest(DIALOG)?.querySelector('h2')?.textContent ?? '';
    if (answered.get(button) === question) return true;
    answered.set(button, question);
    return false;
}

export function installSubmitOnce(): void {
    if (installed) return;
    installed = true;
    document.addEventListener(
        'click',
        (event) => {
            const button = confirmButton(event.target as Element | null);
            if (!button || !isRepeat(button)) return;
            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();
        },
        true,
    );
}
