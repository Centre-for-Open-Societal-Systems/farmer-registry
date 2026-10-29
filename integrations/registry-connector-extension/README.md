# Registry connector extension

The image every OAN registry runs as its connector: OpenG2P's published
`openg2p/registry-connector-api` (pinned by digest in `Dockerfile`), unmodified, plus
`openg2p_registry_connector_extension`. Deployment uses OpenG2P's published
`registry-connector` chart (`https://openg2p.github.io/openg2p-helm`). Only the image
changes, with one repository and digest for api, worker, beat and consumer.

The extension adds the two things the published connector cannot do for an OpenG2P
registry. Nothing else changes, and no OpenG2P file is edited: a `.pth` file registers an
import hook, and the hook wraps two `IngestionService` methods when the connector imports
them.

| Switch (connector `source_config_json`) | Effect |
| --- | --- |
| `sign_registry_payload: true` | `header.signature` becomes a detached JWS over `message.payload` (sorted-key compact JSON, `kid` header). The registry partner API verifies this at the data model's key paths, with the sender partner's Partner Management key. Without the switch the published `"stub-sig"` stays. |
| `websub_content_envelope: true` (websub connectors) | The hub's `hub.content` JSON string is parsed before `data_path` and the mapper. JMESPath cannot parse a string. |

Signing key: the key belongs to the connector's sender partner (`g2p_sender_id`), so each
signing connector stores it in its own write-only auth secrets. The connector API never
returns `auth_secret_json`, and source auth strategies read only their own keys, so ODK
credentials can sit beside it:

```json
{"email": "...", "password": "...",
 "registry_signature": {"key_pem": "<sender partner private key, PEM>", "key_id": "<kid in Partner Management>", "algorithm": "EdDSA"}}
```

`algorithm` is `EdDSA` (default), `ES256` or `RS256`. The published chart sets no extra
environment. Where a deployment can set environment variables,
`CONNECTOR_REGISTRY_SIGNATURE_KEY_PEM`, `_KEY_ID` and `_ALGORITHM` are the fallback, and a
stored key always wins.

A signing connector fails the delivery when the key is missing, so it never sends an
unsigned message.

Build and test: `ci/build/images.sh` builds `coss-ci/registry-connector-extension` and runs
`tests/` inside it. The Jenkins `develop` publish pushes it to
`openg2p/farmer-registry/registry-connector-extension:<commit>`. Crop and livestock pin that
image by digest in their oan-helm connector values; the plan is W21.

Published chart limits: it sets a fixed list of `CONNECTOR_*` variables and has no
`extraEnv`/`envFrom`. So `CONNECTOR_VALIDATE_MAPPED_PAYLOAD` stays at its default (off), and
the connectors' `validation_schema_json` is not enforced; the registry validates on
ingest. Adding the extension point belongs upstream.

Not here: upstream's poll worker advances its watermark past a failed record. The fix
belongs in OpenG2P/registry-connector, not in an image patch.
