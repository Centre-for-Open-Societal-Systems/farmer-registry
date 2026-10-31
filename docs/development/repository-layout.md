# Repository layout and ownership

Maintained guides live in `docs/`; the root and package README files are entrypoints.
Chart descriptions and portal-rendered Markdown remain beside their consumers
because they are application/build inputs.

Repository tests live in `test/` (`unit`, `integration`, `runtime`, `sanity`);
the extension's own tests stay in `farmer-extension/tests/`. Runtime tests execute
in built application images and the sanity suite in the sanity-tests image.
Ordinary pytest runs only the offline unit tests. Performance tooling lives only
under `performance-testing/`; its run outputs are not committed.

The root Jenkinsfile loads `ci/pipelines/dev.groovy` or
`ci/pipelines/staging.groovy`. Shared helpers remain under `ci/`.
`helm/environments/<environment>/delivery.yaml` describes the environment boundary;
it is CI metadata, not an applyable Helm overlay.

The connector application remains upstream-owned. Farmer runtime adapters live in
`integrations/registry-connector/`, and operator recovery tools in
`scripts/operations/connector/`. The chart's component catalogue includes only
Farmer dashboard, Farmer dashboard API and Registry connector. Dashboard API
resources retain Registry Helm ownership.

Farmer cleanup and deployment must preserve Commons, Crop, Livestock, and shared
dashboard ownership.
