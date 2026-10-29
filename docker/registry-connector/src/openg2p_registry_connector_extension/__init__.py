"""OAN extension of the OpenG2P registry connector.

Adds what the published connector cannot do for an OpenG2P registry, and
nothing else. No OpenG2P file is edited: ``openg2p_registry_connector_extension.pth``
registers an import hook (``startup``): ``install()`` wraps two IngestionService methods
when the connector imports its ingestion service, and ``admin_auth`` guards the API app.

1. Registry signature. The registry partner API checks a detached JWS at the data
   model's signature key path, over its signature payload key path, with the sender
   partner's Partner Management key. The connector sends ``"stub-sig"``. With
   ``sign_registry_payload`` in a connector's source config, the envelope's
   ``header.signature`` becomes a detached JWS over ``message.payload``.
2. WebSub content. The hub delivers the published message as a JSON string in
   ``hub.content``; JMESPath cannot parse a string. With ``websub_content_envelope``
   in a websub connector's source config, that string is parsed before ``data_path``.
3. Admin access. The API and UI have no login. ``admin_auth`` requires an OpenG2P staff
   token with the connector's admin client role on every route except health, metrics
   and webhooks.
"""

from .install import install

__all__ = ["install"]
