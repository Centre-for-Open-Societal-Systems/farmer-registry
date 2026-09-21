"""Proof for the global.minioHost guidance in the farmer chart.

The chart comment claims two things about record-image (farmer photo) URLs:

  1. the pre-signed URL the API hands the browser is built from the MinIO
     ENDPOINT the API was configured with, so an in-cluster Service name
     (commons-minio:9000) produces a URL no browser can resolve; and
  2. the signature covers the Host header, so you cannot "fix" it by widening
     the CSP or by rewriting the host at a proxy -- the signer and the browser
     must use the SAME name.

Claim 2 is the load-bearing one. If it were false, the cheap fix (leave the
endpoint alone and just allow the host in CSP) would work, and the chart
guidance -- which asks operators to set a real external hostname -- would be
wrong. So rather than assert it, this exercises the same MinIO client the
platform's MinioClient.get_url uses, against a real MinIO server, and observes
what actually comes back.

Stdlib only: the staff-api image ships `minio` but not `requests`.

Run with a live MinIO reachable as $MINIO_ENDPOINT (host:port). The "public"
hostname used below must also resolve, because presigning performs a region
lookup against the endpoint it is given:

  docker run -d --name miniotest \
    -e MINIO_ROOT_USER=admin -e MINIO_ROOT_PASSWORD=adminsecret \
    minio/minio:latest server /data
  docker run --rm --link miniotest:minio \
    --add-host minio.example.org:<miniotest-ip> \
    -e MINIO_ENDPOINT=minio:9000 --entrypoint python <staff-api-image> \
    /t/test_minio_presigned_host.py
"""

import io
import os
import unittest
import urllib.error
import urllib.request
from datetime import timedelta
from urllib.parse import urlparse

ENDPOINT = os.environ.get("MINIO_ENDPOINT")
ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "admin")
SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "adminsecret")
BUCKET = "documents"
OBJECT = "farmer-photo-test.txt"
CONTENT = b"farmer photo bytes"


@unittest.skipUnless(ENDPOINT, "set MINIO_ENDPOINT to run")
class TestPresignedUrlCarriesTheConfiguredHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from minio import Minio

        cls.client = Minio(
            endpoint=ENDPOINT, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=False
        )
        if not cls.client.bucket_exists(BUCKET):
            cls.client.make_bucket(BUCKET)
        cls.client.put_object(
            BUCKET,
            OBJECT,
            io.BytesIO(CONTENT),
            length=len(CONTENT),
            content_type="text/plain",
        )

    @staticmethod
    def _presign(endpoint):
        """Presign exactly as MinioClient.get_url does, for a given endpoint."""
        from minio import Minio

        return Minio(
            endpoint=endpoint, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=False
        ).presigned_get_object(BUCKET, OBJECT, expires=timedelta(hours=1))

    @staticmethod
    def _fetch(url, host=None):
        req = urllib.request.Request(url)
        if host:
            req.add_header("Host", host)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    # Claim 1: the URL handed to the browser embeds the CONFIGURED endpoint.
    # This is why pointing the API at an in-cluster name is not a cosmetic
    # detail -- that name is what the browser is told to fetch.
    def test_presigned_url_embeds_the_configured_endpoint(self):
        url = self._presign(ENDPOINT)
        self.assertEqual(
            urlparse(url).netloc,
            ENDPOINT,
            "presigned URL does not carry the configured endpoint",
        )

    # Sanity: a correctly-signed URL really does serve the object, so the
    # failure below is attributable to the host change and nothing else.
    def test_correctly_signed_url_downloads(self):
        status, body = self._fetch(self._presign(ENDPOINT))
        self.assertEqual(status, 200, body[:300])
        self.assertEqual(body, CONTENT)

    # Claim 2: serving an already-signed URL under a different Host invalidates
    # it. This is what rules out "leave the endpoint, just widen the CSP".
    def test_rewriting_the_host_breaks_the_signature(self):
        signed = self._presign(ENDPOINT)
        other_host = "minio.example.org:9000"
        self.assertNotEqual(urlparse(signed).netloc, other_host)

        status, body = self._fetch(signed, host=other_host)
        text = body.decode(errors="replace")

        self.assertNotEqual(
            status,
            200,
            "signature survived a Host change -- the chart guidance would be wrong",
        )
        self.assertIn(
            "SignatureDoesNotMatch",
            text,
            f"expected a signature failure, got {status}: {text[:300]}",
        )

    # And the positive form of the same rule: signing FOR the public name
    # produces a URL whose signature matches that name, which is exactly what
    # setting global.minioHost to the external hostname achieves.
    def test_signing_for_the_public_host_matches_that_host(self):
        public = "minio.example.org:9000"
        signed_for_public = self._presign(public)
        self.assertEqual(urlparse(signed_for_public).netloc, public)

        # Replay it against the real server while presenting the public Host:
        # the signature is now correct for that name, so MinIO accepts it.
        real = signed_for_public.replace(f"//{public}/", f"//{ENDPOINT}/")
        status, body = self._fetch(real, host=public)
        self.assertEqual(
            status,
            200,
            f"signing for the public host should validate under it: {body[:300]}",
        )
        self.assertEqual(body, CONTENT)


if __name__ == "__main__":
    unittest.main(verbosity=2)
