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

**Shared code.** The same code is in livestock-registry and cropsown-registry under
`docker/registry-connector/`. Change all three together.

**Known upstream limits** (to be raised with OpenG2P, not patched here):

- The chart has no `extraEnv`, so `CONNECTOR_VALIDATE_MAPPED_PAYLOAD` stays off.
- The poll worker advances its watermark past a failed record.
