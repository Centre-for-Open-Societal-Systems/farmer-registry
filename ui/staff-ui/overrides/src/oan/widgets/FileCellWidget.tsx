'use client';

import { useCallback, useRef, useState } from 'react';
import { isStoredDocumentRef, useWidgetContext } from '@openg2p/registry-widgets';
import { accepts, acceptedTypes, isSerializedFile, serializeFile } from './files';

type Config = Record<string, any>;

type Props = {
    config: Config;
    value?: unknown;
    onChange?: (value: unknown) => void;
    onBlur?: () => void;
    isEnabled?: boolean;
};

const LABELS: Record<string, string> = {
    documents_file_attached: 'Attached',
    documents_upload: 'Upload',
    documents_replace: 'Replace',
    documents_remove: 'Remove',
    documents_too_large: 'The file is larger than {size} MB. Choose a smaller file, or scan it again at a lower resolution.',
    documents_bad_type: '{name} cannot be attached here. Choose a {types} file.',
};

/**
 * A file in a table cell, such as a land's certificate. The table hides every
 * label inside its cells, and the widget package's file widget is a label, so
 * this is a button over a hidden file input instead.
 *
 * The cell saves what the package's file widget saves for a new file, the file
 * itself, base64 encoded; the register's domain service stores it as a document
 * when the row is saved and keeps its document id in the cell.
 *
 * Section metadata (a table column):
 *   widget: "oan-file-cell"
 *   widget-data-options: {accept, maxSize (bytes)} (optional)
 */
export function FileCellWidget({ config, value, onChange, onBlur, isEnabled = true }: Props) {
    const { t } = useWidgetContext();
    const input = useRef<HTMLInputElement>(null);
    const [error, setError] = useState<string | null>(null);
    const accept = config['widget-data-options']?.accept as string | undefined;
    const maxSize = Number(config['widget-data-options']?.maxSize ?? 0);
    const enabled = isEnabled && config['widget-readonly'] !== true;

    const label = useCallback(
        (key: string, params?: Record<string, unknown>) => {
            const fallback = LABELS[key] ?? key;
            const text = t ? t(key, { defaultValue: fallback }) : fallback;
            const shown = !text || text === key ? fallback : text;
            return params ? shown.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? '')) : shown;
        },
        [t],
    );

    // A saved row holds the document id, which says nothing to a reader.
    const name = isSerializedFile(value)
        ? value.name
        : isStoredDocumentRef(value)
          ? value.source_filename || value.label || label('documents_file_attached')
          : typeof value === 'string' && value
            ? label('documents_file_attached')
            : '';
    const hasFile = name !== '';

    const pick = async (file: File | undefined) => {
        if (!file) return;
        setError(null);
        if (!accepts(file, accept)) {
            setError(label('documents_bad_type', { name: file.name, types: acceptedTypes(accept) }));
            return;
        }
        if (maxSize && file.size > maxSize) {
            setError(label('documents_too_large', { size: Math.round(maxSize / 1048576) }));
            return;
        }
        onChange?.(await serializeFile(file));
        onBlur?.();
    };

    return (
        <div className="oan-file-cell">
            <style>{`
                .oan-file-cell { display: flex; align-items: center; gap: 6px; min-width: 160px; }
                .oan-file-cell button {
                    padding: 2px 10px; font-size: 12px; cursor: pointer; white-space: nowrap;
                    background: var(--owt-btn-secondary-bg, #fff);
                    color: var(--owt-btn-secondary-color, #374151);
                    border: 1px solid var(--owt-color-primary-dark, #d1d5db);
                }
                .oan-file-cell button:disabled { opacity: 0.5; cursor: default; }
                .oan-file-cell-name {
                    font-size: 12px; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
                }
                .oan-file-cell-error { font-size: 11px; color: var(--owt-widget-error-color, #dc2626); }
            `}</style>
            {name && (
                <span className="oan-file-cell-name" title={name}>
                    {name}
                </span>
            )}
            <button type="button" disabled={!enabled} onClick={() => input.current?.click()}>
                {label(hasFile ? 'documents_replace' : 'documents_upload')}
            </button>
            {hasFile && (
                <button
                    type="button"
                    disabled={!enabled}
                    onClick={() => {
                        setError(null);
                        onChange?.(null);
                    }}
                >
                    {label('documents_remove')}
                </button>
            )}
            {error && (
                <span className="oan-file-cell-error" role="alert">
                    {error}
                </span>
            )}
            <input
                ref={input}
                type="file"
                accept={accept}
                hidden
                onChange={(event) => {
                    void pick(event.target.files?.[0]);
                    event.target.value = '';
                }}
            />
        </div>
    );
}
