from fastapi import Request, Response
from fastapi.responses import JSONResponse
from typing import Dict, Optional
from datetime import datetime
from openg2p_fastapi_common.service import BaseService
from openg2p_fastapi_common.schemas import G2PResponse, G2PResponseHeader, G2PResponseStatus, G2PResponseBody
from openg2p_registry_core.schemas import IngestDataPayload, IngestDataResponse, IngestDataResponseBody
from openg2p_registry_core.errors import G2PRegistryErrorCodes, G2PRegistryException
from openg2p_registry_core.helpers import TemplateHelper

class RequestResponseHelper(BaseService):

    async def construct_http_request(self, request: Request) -> Dict:
        try:
            request_body: Dict = await request.json()
            request_headers: Dict = dict(request.headers)

            http_request: Dict = {
                "headers": request_headers,
                "body": request_body
            }
            return http_request

        except Exception as _:
            raise Exception("Request body is empty or invalid JSON")

    def construct_ingest_data_success_response(
        self,
        ingest_data_payload: IngestDataPayload,
        response_template_store_id: Optional[str],
    ) -> Response:
        g2p_response_header = G2PResponseHeader(
            request_id="",
            response_status=G2PResponseStatus.SUCCESS,
            response_error_code="",
            response_error_message="",
            response_timestamp=datetime.now()
        )
        
        response_body: IngestDataResponseBody = IngestDataResponseBody(
            response_payload=ingest_data_payload
        )

        ingest_data_response: IngestDataResponse = IngestDataResponse(
            response_header=g2p_response_header,
            response_body=response_body
        )
        data_model_response = self._construct_data_model_response(
            response_template_store_id, ingest_data_response
        )
        return data_model_response
    
    def construct_error_response(
        self, error: Exception, response_template_store_id: Optional[str]
    ) -> Response:
        """
        Unified error response constructor that handles both G2PRegistryException and generic exceptions.
        For G2PRegistryException, uses the exception's code and message.
        For other exceptions, returns a generic internal error (full details are logged only).
        g2p_request is optional - if not provided, request_id will be empty string.
        """
        if isinstance(error, G2PRegistryException):
            error_code = error.code
            error_message = error.message
        else:
            error_code = G2PRegistryErrorCodes.UNEXPECTED_ERROR.value[1]
            error_message = G2PRegistryErrorCodes.UNEXPECTED_ERROR.value[0]

        g2p_response_header = G2PResponseHeader(
            request_id="",
            response_status=G2PResponseStatus.ERROR,
            response_error_code=error_code,
            response_error_message=error_message,
            response_timestamp=datetime.now()
        )
        error_response = G2PResponse(
            response_header=g2p_response_header,
            response_body=G2PResponseBody(
                pagination_response=None,
                response_payload=None
            )
        )

        data_model_error_response = self._construct_data_model_response(
            response_template_store_id, error_response
        )
        return data_model_error_response


    def _construct_data_model_response(
        self, response_template_store_id: Optional[str], response: G2PResponse
    ) -> Response:
        if not response_template_store_id:
            return JSONResponse(content=response.model_dump())

        template_helper = TemplateHelper.get_component()

        response_data = response.model_dump()
        response_data = template_helper.render_with_template(
            document_store_id=response_template_store_id,
            data=response_data,
            expand_data=False
        )
        return JSONResponse(content=response_data)
        