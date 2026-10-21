# Dashboard hook rehearsal

Registry CI runs `rehearse.py` after publishing the pinned Farmer dashboard image. It renders the registry-owned UI chart and executes its IAM setup/registration and chart-smoke programs from that exact image. It also executes the rendered ECR hook shell programs using the coordinator's AWS CLI and a Kubernetes transport shim.

The HTTP fixture implements only the IAM, Keycloak, chart and ECR operations used by those programs. It uses three independent in-memory SQLite stores. Unknown operations return 501. The Kubernetes shim accepts only the dashboard's namespace-local image-pull Secret and stores it in the isolated fixture. It does not contact Kubernetes. No live credentials or staff grants are used.

All fixture containers have external networking disabled. Client containers share the fixture's loopback network namespace; they cannot contact the production URLs. The checks require recovery after ECR and registration failures, idempotent reruns, rejection of anonymous/invalid chart requests, and smoke failure/recovery when service authentication is broken. Changed hook programs, extra hook jobs, or named-user grants fail closed and require extending the rehearsal.

Successful build artifacts bind this evidence to the application commit/image digest, registry-owned chart hash, environment values and rehearsal source hash. The deployment coordinator verifies those bindings before running hooks. Existing file-based rehearsal records remain required for other optional services and staging.

This rehearsal proves the hook programs against isolated HTTP contracts and the Kubernetes transport shim. It does not establish real cluster RBAC, node ECR permissions, Keycloak policy or dashboard data correctness. Normal Helm deployment and authenticated smoke hooks remain required. The fixture contracts come from the executed hook clients and rendered Job commands; no owning-team Postman mock was available. Postman CLI was unavailable in the managed local environment, so the fixture uses Node HTTP and SQLite directly.
