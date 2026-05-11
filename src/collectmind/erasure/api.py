"""POST /erasure-requests handler (T099)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import ulid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from collectmind.auth.dependencies import authenticated_principal
from collectmind.auth.jwt_verifier import Principal
from collectmind.models.erasure import ErasureRequest

_DEFAULT_BOUND_DAYS = 30


router = APIRouter()


@router.post("/api/v1/erasure-requests", status_code=202)
async def submit_erasure_request(
    payload: ErasureRequest,
    request: Request,
    principal: Principal = Depends(authenticated_principal),
) -> JSONResponse:
    request_id = str(ulid.new())
    requested_at = datetime.now(tz=UTC)
    target = requested_at + timedelta(days=_DEFAULT_BOUND_DAYS)
    dispatcher = request.app.state.erasure_dispatcher
    await dispatcher.submit(
        request_id=request_id,
        tenant_id=principal.tenant_id,
        requested_by=principal.subject,
        requested_at=requested_at,
        target_completion_at=target,
        payload=payload,
    )
    return JSONResponse(
        status_code=202,
        content={"request_id": request_id, "target_completion_at": target.isoformat()},
    )
