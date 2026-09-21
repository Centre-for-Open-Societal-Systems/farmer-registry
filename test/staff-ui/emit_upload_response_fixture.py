"""Contract test across the upload seam: real backend response -> real shipped patch.

Everything else verified the two sides separately. This joins them.

The injected browser patch consumes whatever `uploadFile` resolves to:

    let __u = await h([i.image]);
    let __d = Array.isArray(__u) ? __u[0] : null;
    __d && __d.document_id && (... record_image_document_id: __d.document_id ...)

so it depends on three things being simultaneously true:
  * the staff-api upload response payload carries a LIST, and
  * the Next.js proxy transform picks that list out under the right key, and
  * each element exposes `document_id`.

Any one of those drifting silently reverts the photo fix -- the upload would
succeed and nothing would be stamped. None of it is expressible in the browser
bundle, so it is asserted here against the REAL response schema the staff-api
ships (DocumentsData / DocumentData).

Step 1 (this file) emits the real payload as JSON.
Step 2 (verify-upload-contract.js) feeds it to the snippet extracted verbatim
from the built staff-ui chunk and checks the record really gets stamped.

Run:  python test/staff-ui/emit_upload_response_fixture.py > /tmp/upload.json
"""

import json
from datetime import datetime


def build_real_upload_response() -> dict:
    """Serialize a genuine staff-api upload_documents response payload."""
    from openg2p_registry_core.schemas.file_payload import DocumentData, DocumentsData

    payload = DocumentsData(
        documents=[
            DocumentData(
                document_id="doc-123",
                document_store_id="store-abc",
                bucket="documents",
                source_filename="farmer.jpg",
                created_by="tester",
                created_at=datetime(2026, 1, 1, 12, 0, 0),
                presigned_url="http://minio:9000/documents/store-abc?X-Amz-Signature=x",
            )
        ]
    )
    return json.loads(payload.model_dump_json())


def apply_next_route_transform(response_payload: dict):
    """Mirror ui/staff-ui/src/app/api/shared/upload-document/route.ts exactly:

        payload.uploaded_documents ?? payload.documents ?? []
    """
    if response_payload.get("uploaded_documents") is not None:
        return response_payload["uploaded_documents"]
    if response_payload.get("documents") is not None:
        return response_payload["documents"]
    return []


if __name__ == "__main__":
    payload = build_real_upload_response()
    print(json.dumps(apply_next_route_transform(payload)))
