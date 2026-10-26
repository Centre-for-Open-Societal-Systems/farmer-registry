# Upstream Ethiopian calendar components

Repository: https://github.com/OpenG2P/registry-platform

Commit: `0620eb26f2c0189f8f7fe71947ee8d16149d0ad4` (develop). Vendored byte-identical; no local edits.

These files are deleted once the platform pin reaches a release that ships them.
The OAN widget adapter lives separately in `src/oan/widgets/`.

Ordinary date widgets select the adapter with `widget-variant: "ethiopian"`.
Native `TableWidget` hardcodes `widget: "date"` to `TableCellDate`, bypassing the
widget registry. Table date columns therefore use the registered
`oan-ethiopian-date-input` alias for the same adapter and unchanged upstream
component. The native `WidgetRenderer` context carries changes back through the
table's row callback; no table implementation is copied or patched.

`DATE-INVENTORY.json` lists the date paths found in the source metadata. Entered
dates are Farmer birth date, household-member birth date, planted date, and
collected date (including register and intake table forms). The enumerator's
read-only `data_collection_date` stays a native date display. Stored Gregorian
values and server-derived Ethiopian twins remain unchanged; `birth_date_ec`
still supplies lists/report metadata and retains its translation.

## Known upstream behaviour

The unchanged input commits newly entered EC dates only when the year is greater
than 1900. Partly entered EC dates stay in its local draft until valid; they do
not update the stored Gregorian field. The calendar toggle is retained. No local
workaround or conversion changes are applied.

| Upstream path | SHA-256 |
| --- | --- |
| `ui/staff-ui/src/features/activity/components/EthiopianDateInput.tsx` | `1c4f40e569e78945af9ecda6d955d961d37eb7d1c07e953a5b61900a0731a8c8` |
| `ui/staff-ui/src/features/activity/utils/ethiopianCalendar.ts` | `20445c685b8af2277ce2efe533b36aae0124646044fe5a54ed691b279ae5b89c` |
