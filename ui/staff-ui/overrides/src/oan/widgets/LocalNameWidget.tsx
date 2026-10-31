'use client';

import { useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { getValueByPath, setValueByPath, setValues, type WidgetRootState } from '@openg2p/registry-widgets';

type Config = Record<string, any>;

/**
 * Keeps the farmer's own-language name in step with their language. Renders
 * nothing.
 *
 * Fayda gives the name in Amharic. The server fills it in as the farmer's
 * own-language name when that language is Amharic or not chosen yet, and
 * marks it as Fayda's, which locks the name fields. When the staff then choose
 * another language, Fayda's Amharic name is not the farmer's name in that
 * language: this clears it and the mark, so the fields open for typing.
 *
 * It sits in the Name section, with the language, so it runs whenever the
 * language can change; its object data path saves the mark with the section.
 *
 * Section metadata:
 *   widget: "oan-local-name"
 *   widget-data-path: {marker}  (the "name is Fayda's" field)
 *   widget-data-options: {languagePath, language (Fayda's), fields (the name paths)}
 */
export function LocalNameWidget({ config }: { config: Config }) {
    const dispatch = useDispatch();
    const values = useSelector((state: WidgetRootState) => state.widget.values);
    const marker = String((config['widget-data-path'] ?? {}).marker ?? '');
    const options = (config['widget-data-options'] ?? {}) as Record<string, any>;
    const language = getValueByPath(values, String(options.languagePath ?? '')) as string | undefined;
    const fromFayda = marker ? getValueByPath(values, marker) === true : false;

    useEffect(() => {
        if (!marker || !fromFayda || !language || language === options.language) return;
        let patch: Record<string, unknown> = setValueByPath({}, marker, false);
        for (const path of (options.fields ?? []) as string[]) patch = setValueByPath(patch, path, null);
        dispatch(setValues(patch as never));
    }, [dispatch, fromFayda, language, marker, options.fields, options.language]);

    return null;
}
