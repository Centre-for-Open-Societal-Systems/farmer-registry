# Jenkins develop build 16: dev release preservation

Build [16](https://jenkins.oanstaging.com/job/Gen2-Package/job/farmer-registry/job/develop/16/)
checked out the PR #110 merge, `c70ed6658e6b`. Validation, image builds and ECR
publication completed. Deployment preparation then rejected the installed
`farmer-registry.development.oanstaging.com` hostname. The release remained at
revision 37; this failure occurred before `helm upgrade`.

Read-only SSH inspection confirmed that exact hostname. Add it to the existing
dev allowlist while preserving the installed hostname. The regression test names
the supported hostnames explicitly instead of deriving them from the allowlist.

A subsequent read-only server render also exposed gateway drift. The installed
UI, staff API, partner API and ID generator VirtualServices use
`istio-system/development`, but saved release values omit the gateway settings.
The pinned chart would render `internal`. Dev preparation now carries each
installed gateway into its owning chart values. Unsupported gateway lists fail
closed, and the full existing VirtualService preservation check remains intact.
Staging preparation is unchanged.

Verification on 2026-10-19:

- Reproduced the hostname rejection before the fix.
- Rendered the actual candidate with live saved values using
  `helm template --is-upgrade --dry-run=server`; the complete deployment
  preservation guard passed after both fixes. Chart and values were supplied
  through in-memory descriptors; no persistent server files were created.
- Offline tests cover all supported hostnames, installed gateway carry-forward,
  unsupported gateway lists, unrelated environment rejection and route drift.
  The full unit suite passed: 555 tests, 7 environment-dependent skips and
  113 passing subtests. Documentation links and diff checks passed.
- The read-only live schema gate passed: all 36 coordinate columns are Float
  compatible and document history supports attachment promotion.

No Helm upgrade, Jenkins rebuild or live data mutation was performed during
this investigation. The Jenkins log also reports a separate GitHub integration
HTTP 403 while publishing commit status. That requires the Jenkins GitHub
integration's status permission to be corrected; it did not cause the deployment
preparation failure.
