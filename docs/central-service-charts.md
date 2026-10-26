# Farmer dev central service charts

The service coordinator reads [catalogue.yaml](../ci/services/catalogue.yaml),
which preserves the exact previous `cossAddons` object and JSON hash semantics.
Service identities, source repositories, release names, image paths, environment
boundaries and promotion policy remain unchanged.

For dev, embedded dashboard API build/promotion provenance binds the immutable
Farmer chart profile and deployment renderer hash. It does not require local
Chart.yaml or dependency locks. The existing API deployment adapter still
verifies and renders the actual pinned archive, filters setup Jobs, reconciles
installed values and enforces API-only resource changes and revision checks.

The standalone dashboard UI selects addon `farmer-registry-dashboard` version
0.1.2 from the immutable OAN Helm commit in
[dashboard-chart.json](../ci/services/dashboard-chart.json), SHA256
`fcc6601971378fb166df86424c4b96b0831e7f64acf84d17af3dd544ae8f6c79`.
Downloads are bounded to 20 MiB and verified for checksum, chart identity,
version and absence of unresolved dependencies. Helm consumes the verified
archive directly; no extraction, mutable repository lookup or dependency build
occurs. Build and deploy must match package provenance and its hash. The same
verified archive is passed to the existing isolated hook rehearsal. IAM/auth,
image digest, independent release, resource preservation, hook evidence,
initial-install and release-race guards remain in force.

Explicit staging retains its existing local chart path, namespace, overlays and
rehearsal behavior. Environment files and prior staging/recovery evidence were
not moved or changed. Existing build artifacts whose chartHash predates this
dev port require a new build/rehearsal; old evidence is not rewritten.

[chart-cleanup-gate.json](../ci/services/chart-cleanup-gate.json) explicitly says
`retired=false` and lists retained chart sources, remaining staging/operational
consumers and required recovery evidence. Unit checks require these files to
remain present. Retiring them requires reviewed ports, external caller
inventory, updated pin/cleanup contracts and fresh preservation/restore
rehearsals. No chart sources are deleted by this change.

Validation: service coordination and central-package tests cover catalogue hash
identity, missing local charts, provenance drift, corrupt/incorrect packages,
hook binding, image/resource guards and revision races. A read-only download of
the actual pinned archive and Helm rendering passed the unchanged resource
preservation guard against the retained UI chart using an explicit synthetic
existing-Secret reference, with all three hook Jobs present. Offline default
renders generate different random secrets, so they cannot establish credential
preservation. Real server-side lookup, IAM/smoke execution and live deployment
acceptance remain separate gates. No local Docker or live services were used.
