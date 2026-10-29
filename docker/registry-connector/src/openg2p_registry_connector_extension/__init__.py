"""OAN extension of the OpenG2P registry connector.

Adds the two things the published connector cannot do for an OpenG2P registry, and
nothing else. No OpenG2P file is edited: ``openg2p_registry_connector_extension.pth``
registers an import hook, and ``install()`` wraps two IngestionService methods when the
connector imports its ingestion service.

1. Registry signature. The registry partner API checks a detached JWS at the data
   model's signature key path, over its signature payload key path, with the sender
   partner's Partner Management key. The connector sends ``"stub-sig"``. With
   ``sign_registry_payload`` in a connector's source config, the envelope's
   ``header.signature`` becomes a detached JWS over ``message.payload``.
2. WebSub content. The hub delivers the published message as a JSON string in
   ``hub.content``; JMESPath cannot parse a string. With ``websub_content_envelope``
   in a websub connector's source config, that string is parsed before ``data_path``.
"""

from .install import install

__all__ = ["install"]
