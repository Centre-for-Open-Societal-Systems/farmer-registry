# Explicit land links in the unpublished ATI candidate

The v3 candidate now adds `crop_land_id` inside each crop repeat,
`livestock_land_id` inside each livestock repeat and a root `farm_input_land_id`
for the existing root input/water/machinery/finance groups. The business questions,
choices, group paths and original v2 workbook are retained.

Each selection follows [ODK's documented repeat-derived select pattern](https://docs.getodk.org/form-logic/#generating-select-ones-from-repeats)
using `select_one ${land_id}`. The compiled XForm stores the **Parcel ID** as its
value; it does not store a repeat index. Tests inspect the actual compiled itemset
and required binding. `odk/tools/build_v3.py` reconstructs the candidate from v2.
The current workbook SHA-256 is `1ba7e8968c5c7c82cc339da0aa85ec01451d0e5309e33b9db03161fc4d6ab02a`.

The mapper resolves each selected parcel against that submission's native land
IDs. Missing selections with multiple lands, removed/foreign parcels, ambiguous
duplicate parcels and conflicting source/native parent IDs are rejected. A sole
existing land remains compatible with earlier submissions. No answer is attached
to an arbitrary first land. The root input selection scopes the one native
FarmInputs row containing the source's root sibling answers; a landless submission
with such land-owned children still needs an explicit supported domain design.

Verification on 26 October: 14 source/form/mapper checks passed, including actual
XForm compilation, preservation of original question/choice names and separate
crop, livestock and finance parent links. pyxform 3.1.0 plus ODK Validate accepted
the complete candidate with zero warnings. This form has not been published to
Central or exercised in Collect; native section save, approval and ingestion on
this exact candidate remain acceptance requirements.

This is a follow-up to the [original 102-question audit](ATI-MAPPER-AUDIT-20261026.md),
whose earlier workbook hash and findings are preserved. It addresses main-form
multiland collection and pure mapping only. Complete additional-Farmer repeats,
existing-member household changes, consent events, translations, optional email,
and the other audit gaps remain blockers. See the
[native household contract assessment](ATI-HOUSEHOLD-NATIVE-CONTRACT-20261026.md).
