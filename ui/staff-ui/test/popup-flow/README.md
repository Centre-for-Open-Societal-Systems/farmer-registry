# Fayda popup browser checks

The production React widget/helper runs with the actual pinned platform Redux
store and data-path actions. Only HTTP request outcomes are fixtures. This
checks popup-only FIN entry, leading zeros, invalid input, same-window navigation,
close/timeout, text escaping, and preserved verified/unverified data boundaries.
It does not establish a real eSignet token exchange or deployed metadata.

Materialize/install the pinned staff UI with `npm install --prefix ui/staff-ui`.
Run `uv run --with playwright python ui/staff-ui/test/popup-flow/run_browser.py
--node-modules ui/staff-ui/.app/node_modules` from the registry root. The default
uses installed Chrome. CI pins Playwright 1.56.0, installs its Chromium and adds
`--chromium`; esbuild is pinned to 0.28.2. Optional `--output` writes a JSON report.

The tests confirm that popup input alone never creates SUCCESS, verification
proof, an approved Farmer reference or domain activation. An unverified form
retains only its typed FIN when the provider fails, preserving optional native
verification. A previously verified FIN and its proof remain unchanged until a
successful server result. Native PostgreSQL metadata checks separately verify
that all bound main-form FIN widgets are read-only and occur once per section.
