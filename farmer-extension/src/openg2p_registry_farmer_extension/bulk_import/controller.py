"""Staff upload routes; authorization follows the installed intake endpoints."""

from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .farmer_import import MAX_FILE_BYTES, RowError, read_rows
from .service import FARMER_REGISTER_ID, import_rows


def envelope(payload, error=None):
    return {
        "response_header": {
            "request_id": "",
            "response_status": "ERROR" if error else "SUCCESS",
            "response_error_code": "BULK_IMPORT_ERROR" if error else "",
            "response_error_message": error or "",
            "response_timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "response_body": {"pagination_response": None, "response_payload": payload},
    }


def register_bulk_import_routes(app):
    from iam_core.user_auth.decorators import get_required_permissions, require_permissions, requires_auth
    from openg2p_fastapi_common.errors.base_exception import BaseAppException
    from openg2p_fastapi_common.context import dbengine
    from openg2p_registry_core.models import G2PIntakeFormDefinition
    from openg2p_registry_core.services import G2PIntakeFormDataService
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    # This extension also loads in partner-api and celery. Only expose this
    # feature where the staff save AND finalize handlers are registered.
    def leaf_routes(routes):
        for route in routes:
            nested = getattr(route, "original_router", None)
            if nested is not None:
                yield from leaf_routes(nested.routes)
            else:
                yield route

    handlers = {}
    for route in leaf_routes(app.routes):
        for operation in ("save_intake_form_submission", "finalize_intake_form_submission"):
            if getattr(route, "path", "").rstrip("/").endswith("/" + operation):
                handlers[operation] = route
    if not handlers:
        return
    if len(handlers) != 2:
        raise RuntimeError("Bulk import requires both staff intake save and finalize routes")
    permissions = set()
    for route in handlers.values():
        required = get_required_permissions(route.endpoint)
        if required is None:
            raise RuntimeError("Staff intake authorization metadata is missing")
        permissions.update(required)
    save_path = handlers["save_intake_form_submission"].path
    # The staff API normally has no global prefix. Retain one if configured.
    prefix = save_path.split("/intake-form", 1)[0] if "/intake-form" in save_path else ""
    router = APIRouter(prefix=prefix + "/farmer/bulk-import", tags=["Farmer bulk import"])

    def sessions():
        return async_sessionmaker(dbengine.get(), expire_on_commit=False)

    @router.get("/forms")
    @requires_auth
    @require_permissions(permissions)
    async def forms(request: Request):
        if not getattr(getattr(request.state, "auth", None), "sub", None):
            raise HTTPException(401, "An authenticated staff session is required")
        async with sessions()() as session:
            forms = (await session.execute(select(G2PIntakeFormDefinition).where(
                G2PIntakeFormDefinition.register_id == FARMER_REGISTER_ID
            ))).scalars().all()
        return envelope([{"form_id": form.form_id, "label": form.form_description or form.form_mnemonic} for form in forms])

    @router.post("")
    @requires_auth
    @require_permissions(permissions)
    async def bulk_import(request: Request, file: UploadFile = File(...), form_id: str = Form(...)):
        principal = getattr(request.state, "auth", None)
        subject = getattr(principal, "sub", None)
        if not subject:
            raise HTTPException(401, "An authenticated staff session is required")
        try:
            content = await file.read(MAX_FILE_BYTES + 1)
            rows = await run_in_threadpool(read_rows, file.filename, content)
            result = await import_rows(
                rows, form_id, subject, subject,
                getattr(principal, "credentials", None),
                G2PIntakeFormDataService.get_component(), sessions(),
            )
            return envelope(result)
        except RowError as error:
            return JSONResponse(envelope({}, str(error)), status_code=400)
        except BaseAppException as error:
            return JSONResponse(envelope({}, error.message), status_code=error.status_code)
        finally:
            await file.close()

    app.include_router(router)
