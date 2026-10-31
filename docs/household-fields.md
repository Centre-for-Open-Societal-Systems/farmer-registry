# Household fields in the native extension

The three fields requested for verification remain present under their original
names. They are not part of the identity/contact/location profile projected into
Crop or Livestock; they belong to the authoritative Farmer/Household domain.

| Field | Native owner | Screen binding |
| --- | --- | --- |
| `is_household_head` | Farmer live/history/intake schema | `farmer_household_lookup`, the native household lookup plus an OAN select widget |
| `number_of_male_members` | Household live/history/intake schema | `household_information`, second layout row |
| `number_of_female_members` | Household live/history/intake schema | `household_information`, second layout row |

The OAN sections replace the corresponding native bindings through
`meta_data/20_layout.sql`; their fields are declared in `10_sections.sql` and
`12_form_sections.sql`. The household information section remains on the native
Household form and the Farmer intake's new-household flow. A Farmer joining an
approved existing household uses its native lookup; changing that household/head
requires its own approved change rather than silently rewriting it.

Source ODK maps the household-head answer to the Farmer link and derives male and
female counts from the submitted roster, retaining member relationships. Native
household validation checks the roster and counts before finalization. Complete
additional-Farmer registration remains a separate known gap; a member summary is
not a fully registered Farmer.

Seed preflight explicitly requires all three widgets. The disposable native
metadata rehearsal checks both actual widget paths and registered/intake binding
presence after each full seed pass. These guards prevent an unbound section from
being mistaken for a visible field. Source and hosted metadata evidence remain
separate from the locally running UI, which has not been rebuilt during the
Docker control hold. See [candidate status](refactor-candidate.md).
