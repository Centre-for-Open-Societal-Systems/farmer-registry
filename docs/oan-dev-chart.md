# Pinned OAN Farmer dev deployments

Dev uses the exact package in [the approved profile](../ci/deploy/oan-chart.json),
published by COSS oan-helm. The package SHA256, chart version and bundled
platform version are checked before lint, render, upgrade or install. No
dependency resolution or local-chart fallback runs for dev. Staging retains its
local chart, namespace `far` and existing evidence gates.

Jenkins' six recorded ECR digests select application images, including both
Celery workloads, db-seed, sanity and analytics. Saved values do not override
these pins. Installed environments, Secret references and dashboard settings
are reconciled through supported values (`ci/deploy/deployment.py prepare`).
The `ci/deploy/oan-renderer.sh` post-renderer omits the packaged environment
defaults that the prepared values explicitly null.

Moving dev to a new chart version is a reviewed change to `oan-chart.json`
(repository commit, version, SHA-256) followed by `deploy`; a change that needs
an empty database uses `fresh-install` (see [New Dev delivery](NEW_DEV_FARMER_FIRST.md)).
