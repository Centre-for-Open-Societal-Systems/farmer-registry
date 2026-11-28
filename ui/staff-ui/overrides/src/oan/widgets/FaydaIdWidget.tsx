'use client';

import { useId } from 'react';
import { owtFieldInputClass, useBaseWidget, useWidgetContext, type BaseWidgetConfig } from '@openg2p/registry-widgets';

export const FAYDA_ID_WIDGET = 'oan-fayda-id';

/**
 * The Fayda ID (FIN, 12 digits, or FAN, 16 digits) text field. It is the
 * widget library's text input, as that input renders it, with one difference:
 * the whitespace around what staff typed or pasted is taken off before the
 * library stores and validates the value.
 *
 * Why a widget of its own: the library's text input stores what it is given
 * and validates it against the field's pattern, and it has no trim option
 * (characterType, mask, currency and caseControl only; a character filter
 * would also drop whitespace inside the ID, which must stay refused). The
 * pattern stays as the section metadata has it. Whitespace inside the ID, a
 * wrong digit or a wrong length still fail it.
 *
 * Section metadata (site-configuration/12_form_sections.sql), unchanged but for the type:
 *   widget: "oan-fayda-id"
 *   widget-label, widget-required, widget-readonly, widget-data-path,
 *   widget-data-placeholder, widget-data-helptext, widget-data-tooltip,
 *   widget-data-validation, widget-data-options (show, require, disable)
 */
export function FaydaIdWidget({ config }: { config: BaseWidgetConfig }) {
    const { value, error, touched, isEnabled, isRequired, onChange, onBlur } = useBaseWidget({ config });
    const { t } = useWidgetContext();
    const id = useId();
    const say = (key?: string) => (key ? (t ? t(key, { defaultValue: key }) : key) : '');
    const label = say(config['widget-label']);
    const help = say(config['widget-data-helptext']);
    const shown = value === null || value === undefined ? '' : String(value);

    if (config['widget-readonly']) {
        return (
            <div className="mb-[10px] TextDisplayWidget flex flex-col sm:flex-row sm:items-start">
                {label && (
                    <div className="text-base owt-field-label font-medium md:min-w-[120px] sm:pr-4 mb-1 sm:mb-0" title={label}>
                        {label}:
                    </div>
                )}
                <div className="flex-1">
                    <div className="text-base owt-text font-medium" title={shown}>
                        {shown}
                    </div>
                </div>
            </div>
        );
    }

    const showError = touched && error.length > 0;
    const invalid = showError || (config['widget-required'] && shown === '');
    const describedBy = [help ? `${id}-help` : '', showError ? `${id}-error` : ''].filter(Boolean).join(' ') || undefined;

    return (
        <div className="mb-[10px]">
            <div className="flex flex-col sm:flex-row sm:items-start">
                <label
                    htmlFor={id}
                    className="flex items-baseline min-w-0 max-w-full owt-field-label text-base font-medium md:min-w-[120px] sm:pr-4 sm:pt-1 mb-1 sm:mb-0"
                    style={{ fontFamily: 'Roboto, sans-serif' }}
                    title={label}
                >
                    <span className="min-w-0 truncate">{label}</span>
                    {isRequired && (
                        <span className="ml-1 shrink-0 owt-field-required" aria-hidden="true">
                            *
                        </span>
                    )}
                </label>
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                        <input
                            id={id}
                            type="text"
                            inputMode="numeric"
                            autoComplete="off"
                            value={shown}
                            // Trim before the library validates: its onChange stores the value and
                            // validates it in the same call, so the trimmed text is what both see.
                            onChange={(event) => {
                                const text = event.target.value.trim();
                                onChange(text === '' ? null : text);
                            }}
                            onBlur={onBlur}
                            disabled={!isEnabled}
                            aria-required={isRequired || undefined}
                            aria-invalid={invalid || undefined}
                            aria-describedby={describedBy}
                            placeholder={shown ? undefined : say(config['widget-data-placeholder'])}
                            maxLength={config['widget-data-validation']?.maxLength ?? 200}
                            title={say(config['widget-data-tooltip'])}
                            className={owtFieldInputClass({
                                error: Boolean(invalid),
                                disabled: !isEnabled,
                                className: 'w-full sm:w-[180px] max-w-full h-[30px] px-3 owt-shadow-sm',
                            })}
                            style={{ borderRadius: '10px' }}
                        />
                    </div>
                    {help && (
                        <p id={`${id}-help`} className="owt-field-help text-xs mt-1">
                            {help}
                        </p>
                    )}
                    {showError && (
                        <p id={`${id}-error`} className="owt-field-error text-sm mt-1" role="alert">
                            {error[0]}
                        </p>
                    )}
                </div>
            </div>
        </div>
    );
}
