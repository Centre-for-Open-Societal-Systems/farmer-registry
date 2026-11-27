# OpenG2P Registry Farmer Extension

In this repository OpenG2P's Farmer extension is a pinned dependency
(`openg2p_registry_farmer_extension`, built from the OpenG2P/farmer-registry commit in
`farmer-extension/pyproject.toml`), with the OpenAgriNet layer,
`openg2p_registry_oan_farmer_extension`, on top ([farmer-extension/README.md](../../farmer-extension/README.md));
`sample-farmer-extension/` is the extension as OpenG2P publishes it. The rest of
this page describes OpenG2P's Farmer domain.

Extension package for the [OpenG2P Registry Platform](https://github.com/OpenG2P/openg2p-registry-gen2-core) that implements the domain of a **Farmer Registry** — a registry of farmers, their households, lands, crops, livestock, farm inputs and membership details, used to target, enrol and deliver agricultural and social-protection programmes.

Follows the same layout as [`openg2p-registry-nsr-extension`](https://github.com/OpenG2P/national-social-registry/tree/develop/nsr-extension).

## Registers

| Mnemonic | Table | Extends |
|---|---|---|
| `Farmer` | `g2p_register_farmers` | `G2PRegister`, `G2PPerson`, `G2PGeo` |
| `Household` | `g2p_register_households` | `G2PRegister`, `G2PGeo` |
| `HouseholdMember` | `g2p_register_household_members` | `G2PRegister`, `G2PPerson` |

## Supporting Tables

| Mnemonic | Table | Parent (via `link_internal_record_id`) |
|---|---|---|
| `PovertyScore` | `g2p_register_poverty_scores` | Household |
| `MembershipDetails` | `g2p_register_membership_details` | Farmer |
| `Land` | `g2p_register_lands` | Farmer |
| `Crop` | `g2p_register_crops` | Land |
| `FarmInputs` | `g2p_register_farm_inputs` | Farmer |
| `Livestock` | `g2p_register_livestocks` | Farmer |

Every register and supporting table has a `*_history` twin for version snapshots.

> Verification / audit trail is provided by the registry-core platform itself (`g2p_register_verifications`); we do not duplicate it here.

## Install (from source)

OpenG2P's Farmer extension first, from the commit `farmer-extension/pyproject.toml` pins
(`[tool.oan.upstream-farmer-extension]`), then the OAN layer, as the Dockerfiles do:

```bash
pip install "git+https://github.com/OpenG2P/farmer-registry.git@19597f7c15e13adf93ce85a630bede8a8826b84e#subdirectory=farmer-extension"
pip install farmer-extension/
```
