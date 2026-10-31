# OpenG2P default approvals

Farmer uses the published native Farmer example configuration under OAN's own
`.default` policy keys: two sequential AWE stages with `on_empty=block`. Since
28 October 2026 each stage is completed by one decision (`mode=any-n`,
`mode_value=1`) from either the named officer or `admin`: stage 1 lists
`alex.carter` and `admin`, stage 2 lists `nina.patel` and `admin`. Native
self/repeat restrictions stay `false`, so `admin` may decide both stages. The
same shape is seeded in the Crop Sown and Livestock registries, including their
Farmer-reference policies, so every registry approves the same way.

The restored database contains extra rules on the old native policy keys;
ordinary insert-only seeding would retain them. OAN therefore publishes the
default stages under the `.default` keys and resets the four stable
future-request binding IDs. Old policies/rules and pending tasks remain.
The seed image replaces only the three example-policy SQL files with OAN's
default metadata; native callback registration and seeding machinery remain.

Databases seeded before 28 October hold the eight `.default` stages with
`mode=all`. `50_either_officer_or_admin.sql` moves exactly those stages, by
id, to `any-n`/1 in place and adds the `admin` rules through the ordinary
insert-only rule file; policy keys, stage ids, rule ids and bindings do not
change, and the statement is a no-op once applied. Open tasks keep their
policy.

No geographic AWE service, upstream source, user/role grant, existing
request/task or decision is changed. Domain and Farmer-reference dependency
approvals in the receiving registries remain separate; this does not enable
automatic approval. The source check (`test/unit/test_default_approvals.py`)
verifies the configuration directly.

## No approval outside a task

Core also exposes two staff calls that apply a change on one user's say-so,
without an approval task: `/intake-form-data/approve_intake_form_submission`
(`intakeSubmission:approve`, held by Intake Validator and Technical
Administrator) and `/change-requests/approve_change_request` plus
`/change-requests/approve_change_request_for_core_data`
(`changeRequest:approve`, held by Technical Administrator). The role catalog
is registered by the platform chart and is not changed here, so
`direct_approval.py` (in the OAN package) refuses both service calls for every caller, `admin`
included. Decisions made in an approval task are unaffected: the workflow
engine's signed decision reaches `approve_submission_with_session` and
`approve_change_request_from_awe_webhook`, which the guard does not touch.
`reject` calls and the verification calls stay available.
