# OAN Farmer Registry

OpenAgriNet (OAN) application developed in the Centre for Open Societal Systems
(COSS) repositories. This chart reuses the pinned OpenG2P registry platform.

| Source | GitHub repository |
| --- | --- |
| OAN application | [farmer-registry](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry) |
| OAN Helm sources | [oan-helm](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/tree/main/charts/openg2p-farmer-registry) |
| OAN dashboard component | [farmer-registry-dashboard-api](https://github.com/Centre-for-Open-Societal-Systems/farmer-registry-dashboard-api) |
| OAN dashboard component | [oan_farmerregistry_dashboard](https://github.com/Centre-for-Open-Societal-Systems/oan_farmerregistry_dashboard) |

The Helm chart name retains its `openg2p-` prefix to preserve the existing release
and resource names. It does not identify the application source owner. The
OpenG2P dependency repository contains reused platform templates; application
images and provenance are configured by this OAN chart.

Use chart version **1.0.0-dev.5** and upgrade the current release in its current
namespace. Review private values, image digests and namespace-local Secret
references before applying changes. Optional dashboard components remain at
their explicit enablement settings; DA workloads await verified images/config.

See [included services](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/blob/main/docs/service-catalog.md),
[readiness](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/blob/main/docs/readiness.md) and
[Rancher instructions](https://github.com/Centre-for-Open-Societal-Systems/oan-helm/blob/main/docs/rancher-dev.md).

Dev URLs use `<service>.development.oanstaging.com`. The environment-owned
wildcard DNS/TLS and `istio-system/development` Gateway must be prepared first.
See the service onboarding and enablement guide in `docs/service-onboarding.md`.

## Registrant authentication (Fayda through eSignet)

`registrantAuth` configures core's registrant authentication for the farmer
register from values: a post-install/post-upgrade hook writes the provider row
in this registry's database and the shared `oan-registry-intake` OIDC client in
eSignet's database, adding this registry's Staff API callback to the client's
redirect URIs. The client's RSA key is generated into the `registrantAuth.keySecret`
Secret the first time and reused afterwards; it never appears in values, logs or
Git. Set `esignetBaseUrl` (the public eSignet URL) and `callbackUrl`
(`https://<staff api host>/registrant-auth/callback`) per environment. The
register must have `requires_registrant_authentication` set in its metadata, which
the OAN seed does. See `docs/registry-esignet-onboarding.md`.

## DCI response signing

`dciSigning` gives the partner API a stable RSA key for signing its DCI search
responses, which consuming registries (Crop Sown's Farmer reference) pin. A
pre-install/pre-upgrade hook generates the key the first time into the
`dciSigning.keySecret` Secret (`signing.p12`, `password`, `public-key.pem`,
`kid`) and reuses it afterwards; the private key never appears in values, logs
or Git. The public key is printed in the hook log and published in ConfigMap
`<release>-dci-signing-public`. Mount the Secret on the partner API and set
`REGISTRY_PARTNER_API_CRYPTO_SIGNING_KEY_PATH` (the bundle),
`REGISTRY_PARTNER_API_CRYPTO_SIGNING_KEY_PASSWORD` (from the Secret) and
`REGISTRY_PARTNER_API_CRYPTO_SIGNING_KEY_KID` (`dciSigning.kid`) through
`registry.partnerApi` per environment.
