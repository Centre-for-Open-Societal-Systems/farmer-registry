'use client';

import { useEffect, useMemo, useRef, type ComponentProps } from 'react';
import { WidgetProvider } from '@openg2p/registry-widgets';
import { useTranslations } from 'next-intl';
import { useRuntimeConfig } from '@/context/RuntimeConfigContext';
import { dataSourceRequestHandler } from '@/shared/services';
import { brandingToWidgetTheme } from './brandingToWidgetTheme';
// OAN: registers the OAN widgets once, after the package's defaults, wherever
// registry widgets render.
import '@/oan/widgets/register';
// OAN: the intake form's Next guard and server-refusal notification
// (src/oan/intake/). Everything else in this file is upstream's.
import { installNextGuard } from '@/oan/intake/nextGuard';
import { installServerNotice } from '@/oan/intake/serverNotice';
import { installSubmitOnce } from '@/oan/intake/submitOnce';
import { intakeText } from '@/oan/intake/text';

type RegistryWidgetProviderProps = ComponentProps<typeof WidgetProvider>;
type Store = Parameters<typeof installNextGuard>[1];

// The form whose fields a server refusal marks: the provider mounted last.
let currentStore: Store | null = null;

export function RegistryWidgetProvider({
  t,
  theme,
  dataSourceRequestHandler: handler,
  children,
  ...props
}: RegistryWidgetProviderProps) {
  const translations = useTranslations();
  const { config } = useRuntimeConfig();
  const brandingTheme = useMemo(
    () => brandingToWidgetTheme(config.branding),
    [config.branding],
  );

  // OAN: the guard listens for this provider's Next buttons only.
  const rootRef = useRef<HTMLDivElement>(null);
  const store = (props as { store?: Store }).store;
  const translate = useMemo(() => intakeText(translations as never), [translations]);
  const translateRef = useRef(translate);
  translateRef.current = translate;
  useEffect(() => {
    if (!store || !rootRef.current) return undefined;
    currentStore = store;
    installServerNotice(() => currentStore, () => translateRef.current);
    installSubmitOnce();
    const remove = installNextGuard(rootRef.current, store, (key) => translateRef.current(key));
    return () => {
      remove();
      if (currentStore === store) currentStore = null;
    };
  }, [store]);

  return (
    <WidgetProvider
      {...props}
      t={t ?? translations}
      theme={theme ?? brandingTheme}
      dataSourceRequestHandler={handler ?? dataSourceRequestHandler}
    >
      <div ref={rootRef} style={{ display: 'contents' }}>
        {children}
      </div>
    </WidgetProvider>
  );
}
