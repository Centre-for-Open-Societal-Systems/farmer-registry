'use client';

import { useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { getValueByPath, setValueByPath, setValues, type WidgetRootState } from '@openg2p/registry-widgets';

type Config = Record<string, any>;

/**
 * Where the enumerator is while filling the form: the device's position, taken
 * once, if the browser is allowed to give it. Nothing is shown and nothing is
 * asked of the enumerator beyond the browser's own permission prompt; a
 * position already on the record is kept.
 *
 * Section metadata:
 *   widget: "oan-enumerator-position"
 *   widget-data-path: {latitude, longitude, altitude, accuracy}
 */
export function EnumeratorPositionWidget({ config }: { config: Config }) {
    const dispatch = useDispatch();
    const values = useSelector((state: WidgetRootState) => state.widget.values);
    const paths = (config['widget-data-path'] ?? {}) as Record<string, string>;
    const asked = useRef(false);
    const known = paths.latitude ? getValueByPath(values, paths.latitude) : null;

    useEffect(() => {
        if (asked.current || config['widget-readonly'] === true) return;
        if (known !== null && known !== undefined && known !== '') return;
        if (typeof navigator === 'undefined' || !navigator.geolocation) return;
        asked.current = true;
        navigator.geolocation.getCurrentPosition(
            ({ coords }) => {
                const found: Record<string, number | null> = {
                    latitude: Number(coords.latitude.toFixed(7)),
                    longitude: Number(coords.longitude.toFixed(7)),
                    altitude: coords.altitude === null ? null : Number(coords.altitude.toFixed(2)),
                    accuracy: Number(coords.accuracy.toFixed(2)),
                };
                let patch: Record<string, unknown> = {};
                for (const [key, value] of Object.entries(found)) {
                    if (paths[key]) patch = setValueByPath(patch, paths[key], value);
                }
                dispatch(setValues(patch as never));
            },
            () => undefined, // refused or unavailable: the record has no enumerator position
            { enableHighAccuracy: true, timeout: 20000, maximumAge: 60000 },
        );
    }, [config, dispatch, known, paths]);

    return null;
}
