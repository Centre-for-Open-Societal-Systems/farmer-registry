import { createElement, useEffect } from 'react';
import { widgetRegistry } from '@openg2p/registry-widgets';

// The config of every widget on screen, by widget id. The intake Next guard
// (nextGuard.ts) validates the open section from it: the widget library keeps
// values, errors and touched state in its store, but not the configs, and the
// page passes the section configs only to the library's own components.
//
// Each registered widget component is wrapped once, after the package's
// defaults and OAN's own widgets are registered (register.ts), by a component
// that records its config while it is mounted and renders the original
// unchanged. The library renders a widget only while it is visible, so the map
// holds the widgets the officer can see.
export type WidgetConfig = Record<string, unknown>;

const mounted = new Map<string, WidgetConfig>();

export function widgetConfig(widgetId: string): WidgetConfig | undefined {
    return mounted.get(widgetId);
}

type Props = { config: WidgetConfig } & Record<string, unknown>;
type Component = (props: Props) => unknown;

const WRAPPED = Symbol.for('oan.widgetConfigRecorder');

function recorder(original: Component): Component {
    function Recorded(props: Props) {
        const id = props.config?.['widget-id'];
        const config = props.config;
        useEffect(() => {
            if (typeof id !== 'string') return undefined;
            mounted.set(id, config);
            return () => {
                if (mounted.get(id) === config) mounted.delete(id);
            };
        }, [id, config]);
        return createElement(original as never, props as never);
    }
    (Recorded as unknown as Record<symbol, boolean>)[WRAPPED] = true;
    return Recorded;
}

export function recordWidgetConfigs(): void {
    for (const entry of widgetRegistry.getAll()) {
        const component = entry.component as unknown as Component & Record<symbol, boolean>;
        if (!component || component[WRAPPED]) continue;
        widgetRegistry.register({ ...entry, component: recorder(component) as never });
    }
}
