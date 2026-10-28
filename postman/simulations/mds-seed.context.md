# Farmer seed HTTP contract

The member models this repository's existing save/finalize envelope and section
responses. It does not model AWE, IAM permissions, Celery or registry persistence.
The owner-mock search was attempted on 2026-10-28; Postman was signed out.

Run `postman simulation run postman/simulations/mds-seed.sim.yaml --port 49218 --output ndjson`,
then set `OAN_SEED_SIMULATION_URL=http://127.0.0.1:49218/farmer` and run
`python -m pytest tests/unit/test_mds_seed_http.py`.
MDS is a PostgreSQL dependency, tested separately, not a simulation member.

Local verification on 2026-10-28: real HTTP save/finalize requests for household
and farmer succeeded; the mock rejected the legacy `Mr` prefix with HTTP 422.
The PostgreSQL contract check consumed 21 sample people and six households,
ignored draft/future list versions and rejected a retired code. These checks
do not establish live AWE approval or Celery ingestion acceptance.
