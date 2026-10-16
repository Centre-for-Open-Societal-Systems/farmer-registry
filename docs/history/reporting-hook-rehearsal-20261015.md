> Historical evidence. Use [current operations](../operations/README.md) for maintenance; recorded commands and job links describe past rollouts.

# Reporting hook recovery — build 6

Read-only inspection confirmed that revision 6 deployed the new application pods,
and both db-seed and sanity completed. Helm failed at the later reporting-views
hook. Its failed pod had already been deleted, so the exact pod log was unavailable.

The hook command reproduced two blockers on the isolated repaired-dev database:

1. The maintained SQL referenced `g2p_register_farmers.main_crops`, absent from the
   COSS schema. Optional JSON lookup now supports both absent and present columns;
   it does not infer declared main crops from seasonal crop records.
2. The pinned rc.544 image has no `/seed/generate_reporting_views.py`. Automatic
   generation is now disabled in chart defaults and prepared Jenkins values.
   Maintained SQL reports and the refresh CronJob remain enabled.

The SQL runs in one transaction so a later DDL failure cannot commit earlier
view replacements. Reporting uses `restartPolicy: Never` to retain failed-pod
logs instead of losing them when the in-pod retry limit is reached.

Validation: built the seed image and executed the reporting hook's exact command
from the rendered candidate twice against the isolated database; both runs
exited zero. PostgreSQL integration tests cover absent, empty, populated and
malformed optional crop values using the actual SQL projection. All four seed/
reporting transaction tests and 39 deployment guard tests passed. Rendering
against freshly read revision-6 values passed the resource-preservation guard.

No server writes or Jenkins rebuilds were performed during this fix. New-dev
Helm remains failed until a successful upgrade. Disabling the unsupported
generator does not provide new automatically generated reporting views.
