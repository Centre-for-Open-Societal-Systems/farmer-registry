'use client';

import { useCallback, useRef, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import {
    getValueByPath,
    isStoredDocumentRef,
    setValueByPath,
    setValues,
    useBaseWidget,
    useWidgetContext,
    type WidgetRootState,
} from '@openg2p/registry-widgets';
import { accepts, acceptedTypes, isSerializedFile, openSerializedFile, serializeFile } from './files';

type Config = Record<string, any>;

export const DOCUMENTS_VARIANT = 'oan-documents';
export const DOCUMENT_SLOT_VARIANT = 'oan-document-slot';

const LABELS: Record<string, string> = {
    oan_docs_add: 'Add file',
    oan_docs_none: 'No files',
    oan_docs_full: 'Up to {count} files can be attached here. Remove one to add another.',
    oan_docs_view: 'View',
    oan_file_remove: 'Remove',
    oan_file_too_large: 'The file is larger than {size} MB. Choose a smaller file, or scan it again at a lower resolution.',
    oan_file_bad_type: '{name} cannot be attached here. Choose a {types} file.',
};

/**
 * One documents category, such as the identity document, with several files.
 *
 * The staff UI saves each file widget's file as a document under the widget's
 * label, and on reload puts the document back at documents.<label>: one file
 * per label. So a category is a set of upstream file widgets ("slots"), and
 * this widget, shown for the first of them, lists the files in all of them and
 * adds a file to the first free slot. A new file moves up when one before it
 * is removed; a saved document keeps its slot. A required category requires
 * its first slot, the one the first file goes to. The other slots render
 * nothing. Upload, storage and reload stay upstream's.
 *
 * Section metadata (the first slot; the others have
 * "widget-variant": "oan-document-slot"):
 *   widget: "file", widget-variant: "oan-documents"
 *   widget-data-options: {title, slots: [data path, ...], accept, maxSize (bytes)}
 */
export function DocumentsWidget({ config }: { config: Config }) {
    const dispatch = useDispatch();
    const { t, schemaData } = useWidgetContext();
    const values = useSelector((state: WidgetRootState) => state.widget.values);
    const base = useBaseWidget({ config: config as never });
    const options = (config['widget-data-options'] ?? {}) as {
        title?: string;
        slots?: string[];
        accept?: string;
        maxSize?: number;
    };
    const slots = Array.isArray(options.slots) ? options.slots : [String(config['widget-data-path'])];
    const maxSize = Number(options.maxSize ?? 0);
    const readonly = config['widget-readonly'] === true;
    const enabled = !readonly && base.isEnabled;
    const input = useRef<HTMLInputElement>(null);
    const [message, setMessage] = useState<string | null>(null);

    const label = useCallback(
        (key: string, params?: Record<string, unknown>) => {
            const fallback = LABELS[key] ?? key;
            const text = t ? t(key, { defaultValue: fallback }) : fallback;
            const shown = !text || text === key ? fallback : text;
            return params ? shown.replace(/\{(\w+)\}/g, (_, name) => String(params[name] ?? '')) : shown;
        },
        [t],
    );

    // The form's value when it has one (null once removed), else the record's.
    const read = (path: string) => {
        const value = getValueByPath(values, path);
        return value !== undefined ? value : getValueByPath(schemaData ?? {}, path);
    };
    const current = slots.map((path) => read(path) || null);
    const files = slots.map((path, i) => ({ path, index: i, value: current[i] })).filter(({ value }) => !!value);

    // New files fill the free slots in order. A saved document stays in its
    // slot: it is stored under that slot's label and comes back there.
    const write = (next: unknown[]) => {
        const kept = next.map((value) => (isSerializedFile(value) ? null : value));
        const fresh = next.filter(isSerializedFile);
        let k = 0;
        let patch: Record<string, unknown> = {};
        slots.forEach((path, i) => (patch = setValueByPath(patch, path, kept[i] ?? fresh[k++] ?? null)));
        dispatch(setValues(patch as never));
        base.onBlur?.();
    };

    const add = async (picked: File[]) => {
        setMessage(null);
        const wrong = picked.find((file) => !accepts(file, options.accept));
        const typed = picked.filter((file) => accepts(file, options.accept));
        const fits = typed.filter((file) => !maxSize || file.size <= maxSize);
        if (wrong) setMessage(label('oan_file_bad_type', { name: wrong.name, types: acceptedTypes(options.accept) }));
        else if (fits.length < typed.length) setMessage(label('oan_file_too_large', { size: Math.round(maxSize / 1048576) }));
        const room = slots.length - files.length;
        if (fits.length > room) setMessage(label('oan_docs_full', { count: slots.length }));
        const added = await Promise.all(fits.slice(0, room).map(serializeFile));
        if (added.length) write([...current, ...added]);
    };

    const remove = (index: number) => {
        setMessage(null);
        write(current.map((value, i) => (i === index ? null : value)));
    };

    const nameOf = (value: unknown) =>
        isSerializedFile(value) ? value.name
        : isStoredDocumentRef(value) ? value.source_filename || value.label
        : String(value);
    const view = (value: unknown) => {
        if (isSerializedFile(value)) openSerializedFile(value);
        else if (isStoredDocumentRef(value) && value.presigned_url) window.open(value.presigned_url, '_blank', 'noopener');
    };

    const title = label(String(options.title ?? config['widget-label'] ?? ''));
    const showError = base.touched && base.error.length > 0;

    return (
        <div className="mb-[10px] oan-docs">
            <style>{`
                .oan-docs-title { font-weight: 500; margin-bottom: 6px; color: var(--owt-color-text, #111827); }
                .oan-docs-title .req { color: var(--owt-widget-error-color, #dc2626); margin-left: 2px; }
                .oan-docs-list { display: flex; flex-direction: column; gap: 4px; margin-bottom: 6px; }
                .oan-docs-file {
                    display: flex; align-items: center; gap: 6px; padding: 4px 8px; font-size: 13px;
                    border: 1px solid var(--owt-color-border, #d1d5db); border-radius: 8px;
                }
                .oan-docs-file span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
                .oan-docs button {
                    padding: 2px 10px; font-size: 12px; cursor: pointer; white-space: nowrap;
                    background: var(--owt-btn-secondary-bg, #fff); color: var(--owt-btn-secondary-color, #374151);
                    border: 1px solid var(--owt-color-primary-dark, #d1d5db); border-radius: 6px;
                }
                .oan-docs button:disabled { opacity: 0.5; cursor: default; }
                .oan-docs-add { border-style: dashed !important; }
                .oan-docs-note { font-size: 12px; color: var(--owt-widget-helptext-color, #6b7280); margin-top: 4px; }
                .oan-docs-error { font-size: 12px; color: var(--owt-widget-error-color, #dc2626); margin-top: 4px; }
            `}</style>
            {title && (
                <div className="oan-docs-title owt-field-label">
                    {title}
                    {base.isRequired && <span className="req">*</span>}
                </div>
            )}
            <div className="oan-docs-list">
                {files.length === 0 && readonly && <span className="oan-docs-note">{label('oan_docs_none')}</span>}
                {files.map(({ path, value, index }) => (
                    <div key={path} className="oan-docs-file" title={nameOf(value)}>
                        <span>{nameOf(value)}</span>
                        <button type="button" onClick={() => view(value)}>{label('oan_docs_view')}</button>
                        {enabled && (
                            <button type="button" onClick={() => remove(index)}>{label('oan_file_remove')}</button>
                        )}
                    </div>
                ))}
            </div>
            {enabled && (
                <>
                    <button type="button" className="oan-docs-add" disabled={files.length >= slots.length}
                            onClick={() => input.current?.click()}>
                        + {label('oan_docs_add')}
                    </button>
                    <div className="oan-docs-note">{label('oan_docs_full', { count: slots.length })}</div>
                    <input
                        ref={input}
                        type="file"
                        multiple
                        accept={options.accept}
                        hidden
                        onChange={(event) => {
                            void add(Array.from(event.target.files ?? []));
                            event.target.value = '';
                        }}
                    />
                </>
            )}
            {message && <div className="oan-docs-error" role="alert">{message}</div>}
            {showError && files.length === 0 && <div className="oan-docs-error">{base.error[0]}</div>}
        </div>
    );
}
