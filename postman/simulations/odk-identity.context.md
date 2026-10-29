# ODK signature HTTP simulation

The production OAN signature verifier calls the native PM active-key contract
`GET /keys/{partner_id}/{kid}` using real HTTP. The stand-in returns the same
partner/key/algorithm/public-key shape as the native PM helper. Other calls
return501; `/configure` is a local test-control endpoint only.

Start with `postman simulation run postman/simulations/odk-identity.sim.yaml
--port49216 --output ndjson`; use the listening event's URL. Run
`OAN_ODK_PM_SIMULATION_URL=http://127.0.0.1:49216/pm python -m pytest
farmer-extension/tests/test_odk_signature_http.py`. The Docker client uses
`host.docker.internal` in place of localhost.

Keys, partner IDs and message IDs are generated in test memory. No existing
partner, credentials or Farmer payload is reused. This verifies signature
binding and PM failure handling against a stand-in, not live PM provisioning,
connector delivery or an approved Farmer intake. The owner-mock search was
attempted on25October2026 but the CLI was signed out; no workspace was created
or published. Local runs do not require sign-in. Simulation logs stay outside Git.
