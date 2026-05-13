"""Operator query API (T098)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from collectmind.auth.dependencies import authenticated_principal
from collectmind.auth.jwt_verifier import Principal
from collectmind.errors import NotFound

router = APIRouter()


_SAFE_ID = re.compile(r"^[A-Za-z0-9_\-.]{1,256}$")


def _ensure_safe(kind: str, value: str) -> str:
    """Reject path parameters that contain control chars / non-printable bytes.

    Schemathesis fuzzing with binary or NUL bytes would otherwise reach asyncpg
    and surface as 500. Returning a documented 404 keeps the contract honest.
    """
    if not _SAFE_ID.match(value):
        raise NotFound(kind, value)
    return value


@router.get("/api/v1/policies/{policy_id}")
async def get_policy(
    policy_id: str, request: Request, principal: Principal = Depends(authenticated_principal)
) -> JSONResponse:
    policy_id = _ensure_safe("policy", policy_id)
    repo = request.app.state.policy_repo
    found = await repo.get(principal.tenant_id, policy_id)
    if found is None:
        raise NotFound("policy", policy_id)
    return JSONResponse(content=found)


@router.get("/api/v1/policies/{policy_id}/versions")
async def list_policy_versions(
    policy_id: str,
    request: Request,
    principal: Principal = Depends(authenticated_principal),
    limit: int = Query(default=50, ge=1, le=200),
) -> JSONResponse:
    policy_id = _ensure_safe("policy", policy_id)
    repo = request.app.state.policy_repo
    rows = await repo.list_versions(principal.tenant_id, policy_id, limit=limit)
    if not rows:
        raise NotFound("policy", policy_id)
    return JSONResponse(content=rows)


@router.get("/api/v1/vehicle-groups/{group_id}/active-policy")
async def active_policy_for_group(
    group_id: str,
    request: Request,
    principal: Principal = Depends(authenticated_principal),
) -> JSONResponse:
    group_id = _ensure_safe("active_policy", group_id)
    repo = request.app.state.policy_repo
    found = await repo.find_active_for_vehicle(principal.tenant_id, group_id)
    if found is None:
        raise NotFound("active_policy", group_id)
    return JSONResponse(content=found)


@router.get("/api/v1/findings/{finding_id}/outcome")
async def outcome_for_finding(
    finding_id: str,
    request: Request,
    principal: Principal = Depends(authenticated_principal),
) -> JSONResponse:
    finding_id = _ensure_safe("outcome", finding_id)
    repo = request.app.state.outcome_repo
    found = await repo.get_by_finding(principal.tenant_id, finding_id)
    if found is None:
        raise NotFound("outcome", finding_id)
    return JSONResponse(content=found)


@router.get("/api/v1/audit/{correlation_id}")
async def audit_for_correlation(
    correlation_id: str,
    request: Request,
    principal: Principal = Depends(authenticated_principal),
) -> JSONResponse:
    correlation_id = _ensure_safe("correlation_id", correlation_id)
    writer = request.app.state.audit_writer
    events = await writer.list_for_correlation(principal.tenant_id, correlation_id)
    if not events:
        raise NotFound("correlation_id", correlation_id)
    return JSONResponse(content=events)


@router.get("/api/v1/erasure-requests/{request_id}")
async def erasure_request_status(
    request_id: str,
    request: Request,
    principal: Principal = Depends(authenticated_principal),
) -> JSONResponse:
    request_id = _ensure_safe("erasure_request", request_id)
    dispatcher = request.app.state.erasure_dispatcher
    record = await dispatcher.get(principal.tenant_id, request_id)
    if record is None:
        raise NotFound("erasure_request", request_id)
    return JSONResponse(content=record)
