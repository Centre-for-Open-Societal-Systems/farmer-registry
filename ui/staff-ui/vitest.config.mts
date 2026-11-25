// Client tests of the OAN overrides (tests/). They run inside the materialized
// .app/ so the pinned upstream packages are the ones under test:
//   npm run test:client
// Plain object, no `vitest/config` import: this file sits outside .app/, where
// the test tools are installed.
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const app = path.join(here, '.app');

export default {
    root: app,
    esbuild: { jsx: 'automatic' },
    resolve: {
        // The overrides and the tests live outside .app/; one copy of each
        // package, the one the app builds with.
        alias: [
            {
                find: /^(@openg2p\/registry-widgets|@testing-library\/react|@testing-library\/dom|react|react-dom|react-redux|@reduxjs\/toolkit|react-toastify)(\/.*)?$/,
                replacement: `${app.replace(/\\/g, '/')}/node_modules/$1$2`,
            },
        ],
    },
    server: { fs: { strict: false } },
    test: {
        environment: 'jsdom',
        include: [`${path.join(here, 'tests').replace(/\\/g, '/')}/**/*.test.tsx`],
        server: { deps: { inline: [/@openg2p\/registry-widgets/] } },
    },
};
