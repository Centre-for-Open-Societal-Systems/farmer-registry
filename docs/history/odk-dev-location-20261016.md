# Farmer dev ODK location update ? 16 October 2026

At `https://odk.commons-dev.oanstaging.com`, project `1`, `farmer_profile`
now publishes version **1.0.5**, using the same checked-in XLSForm and all four
CSV media files as staging. Kebele is a cascading dropdown; Zone and Woreda are
external lists; map placement is explicit. The canonical seed supplies every
real place and its parent. The established Other-answer policy is preserved.

Version 1.0.4 and both existing submissions remain. Their XML and attachments
were compared byte for byte after publication; every published media file
matches the repository. The existing draft was identical to the published
form before replacement. Backups of the XLSForm, XML, media, version metadata,
submissions and attachments are checksum verified on the dev host at
`/var/backups/farmer-dev-odk-location-20261016/` (26 files), with a protected
second archive in the operator workspace.

The existing connector account can read submissions but cannot manage drafts.
A temporary publisher was created, scoped to Farmer project 1, used for the
update, and deleted afterward. The permanent collector account, connector
pipeline identity and checkpoint were retained. No new submission was created
or approved by this form-update check.

Authenticated Enketo draft and published-form checks verified all canonical
choices on the largest branch (79 Kebeles), clearing stale child selections,
manual map selection, and controlled GPS callback handling. Mobile viewport
checks confirmed map selection with a permission-denied GPS callback. There
were no JavaScript errors or failed map-tile requests. Native Android Collect
and physical GPS were not available for testing.

Dev timings varied: synchronous Woreda-change work measured 253 ms before,
343 ms in one desktop draft run, 253 ms in the mobile draft run, and 271 ms
on the published form. Initial readiness was about 2.9?4.1 seconds. These dev
samples do not establish a speed improvement; the compact form model and
functional behavior are verified. The staging measurements in the
[staging report](odk-staging-location-20261016.md) are separate observations.

Reload the web form or download the new blank form in Collect. Existing
submissions and form history should never be deleted to refresh clients.
