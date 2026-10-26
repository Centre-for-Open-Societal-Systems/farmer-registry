"""Run the production signature verifier over real HTTP to a PM stand-in."""
import asyncio
import hashlib
import json
import os
import time
from copy import deepcopy
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from openg2p_registry_oan_extension.odk.signature import InvalidOdkSignature, verify_odk_signature

URL = os.environ.get('OAN_ODK_PM_SIMULATION_URL')
pytestmark = pytest.mark.skipif(not URL, reason='Requires the local Postman PM-key simulation')


@pytest.mark.parametrize('case', ['valid', 'tampered', 'wrong-message', 'wrong-issuer', 'expired', 'wrong-partner-key', 'pm-unavailable'])
def test_real_http_signature_boundary(case):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    partner = 'test-odk-' + uuid4().hex
    kid = uuid4().hex
    message_id = uuid4().hex
    message = {'payload': {'test_record': uuid4().hex}}
    current = int(time.time())
    claims = {'iss': partner, 'iat': current - 10, 'exp': current + 60,
              'message_id': message_id,
              'body_sha256': hashlib.sha256(json.dumps(message, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()}
    config = {'partner_id': partner, 'kid': kid, 'algorithm': 'RS256', 'public_key': public}
    if case == 'wrong-issuer':
        claims['iss'] = 'different-issuer'
    if case == 'expired':
        claims.update(iat=current - 120, exp=current - 60)
    if case == 'wrong-partner-key':
        config['wrongPartner'] = True
    if case == 'pm-unavailable':
        config['failure'] = True
    response = httpx.post(URL + '/configure', json=config)
    response.raise_for_status()
    signature = jwt.encode(claims, key, algorithm='RS256', headers={'kid': kid})
    envelope = {'body': {'header': {'sender_id': partner, 'message_id': message_id,
                                    'signature_algorithm': 'RS256'}}}
    submitted = deepcopy(message)
    if case == 'tampered':
        submitted['payload']['test_record'] = 'tampered'
    if case == 'wrong-message':
        envelope['body']['header']['message_id'] = uuid4().hex
    operation = verify_odk_signature(partner, signature, submitted, envelope, URL)
    if case == 'valid':
        asyncio.run(operation)
    else:
        with pytest.raises(InvalidOdkSignature, match='Invalid Farmer ODK message signature'):
            asyncio.run(operation)
