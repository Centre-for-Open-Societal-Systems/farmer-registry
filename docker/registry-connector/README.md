# Farmer Registry — connector image

The connector of this registry runs as the `registryConnector` subchart of the openg2p-registry
chart (rc.601+). That chart runs OpenG2P's published `openg2p/registry-connector-api`; the
subchart's image values point at this image instead:

- `FROM` the published `openg2p/registry-connector-api` (pinned by digest in `Dockerfile`), unmodified.
- Plus `openg2p_registry_connector_extension` (`src/`), loaded by a `.pth` import hook. No OpenG2P
  file is edited, and the entrypoint and roles (api, worker, beat, consumer) are upstream's.

Built and pushed by Jenkins with the other images (`docker/<component>`, build context = repo
root) as `openg2p/farmer-registry/registry-connector:<commit>`. `tests/` runs inside the pushed
image.

The extension adds what OpenG2P's connector documentation specifies, but the published code does
not yet do for an OpenG2P registry. Each is switched per connector in `source_config_json`:

| Switch | Effect |
| --- | --- |
| `sign_registry_payload: true` | `header.signature` becomes a detached JWS over `message.payload` (sorted-key compact JSON, `kid` header): the form the registry partner API verifies at the data model's key paths, with the sender partner's Partner Management key. The published connector sends `"stub-sig"`. |
| `websub_content_envelope: true` (websub connectors) | Parses the hub's `hub.content` JSON string before `data_path`, which JMESPath cannot parse. |

**Signing key.** The key belongs to the connector's sender partner (`g2p_sender_id`), so it is
kept in the connector's write-only `auth_secret_json`. The API never returns that field, and the
source auth strategies ignore this key, so ODK credentials can sit beside it:

```json
{"registry_signature": {"key_pem": "<PEM>", "key_id": "<kid in Partner Management>", "algorithm": "EdDSA"}}
```

`algorithm` is `EdDSA` (default), `ES256` or `RS256`.

- A signing connector with no key fails the delivery, so it never sends an unsigned message.
- The environment variables `CONNECTOR_REGISTRY_SIGNATURE_KEY_PEM`, `_KEY_ID` and `_ALGORITHM` are a fallback. The published chart cannot set them.

**Admin access.** The published API and UI have no login. `admin_auth` follows the OpenG2P
service pattern (Keycloak `staff` realm; a confidential client defines the admin client role;
tokens are validated via JWKS), as the Consent Manager and AWE do:

| Route | Access |
| --- | --- |
| `/health*`, `/metrics`, `/webhook*` | Open. Webhooks are verified by each connector's verifier; the hub delivers in-cluster. |
| `/metadata/admin-auth` | Open: the UI's login settings. |
| Everything else (`/connectors`, `/runs`, `/dlq`, `/metadata`, `/docs`, `/openapi.json`) | Bearer token from the issuer with client role `REGISTRY_CONNECTOR_ADMIN` on client `registry-connector`. No token or an invalid one is 401, no role is 403. |

Settings come from `CONNECTOR_ADMIN_AUTH_ISSUER`, `_JWKS_URL`, `_CLIENT_ID`, `_ROLE` and
`_UI_CLIENT_ID`, else from `admin-auth.json` (baked at
`/etc/openg2p-registry-connector-extension/admin-auth.json`, because the published chart passes
no extra environment). Without an issuer the protected routes answer 503, never open. The
Keycloak clients, the role and its mappings (`admin` user, the client's service account) are
provisioned by keycloak-init in oan-helm.

`docker/registry-connector-ui` is the published UI behind the same login (keycloak-js, public
client `registry-connector-ui`): it signs in, refuses a user without the role, and adds the
bearer token to the UI's API calls. Scripts calling the API use a client-credentials token of
the `registry-connector` service account.

**Shared code.** The same code is in livestock-registry and cropsown-registry under
`docker/registry-connector/`. Change all three together.

**Known upstream limits** (to be raised with OpenG2P, not patched here):

- The chart has no `extraEnv`, so `CONNECTOR_VALIDATE_MAPPED_PAYLOAD` stays off.
- The poll worker advances its watermark past a failed record.
