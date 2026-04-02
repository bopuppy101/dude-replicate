"""Endpoint management routes."""

import asyncio
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import get_current_user, require_admin
from server.models.user import User
from server.schemas.endpoint import (
    EndpointCreate, EndpointUpdate, EndpointOut,
    TestConnectionRequest, TestConnectionResponse,
)
from server.services.endpoint_service import (
    list_endpoints, get_endpoint, create_endpoint, update_endpoint,
    delete_endpoint, test_connection_sync,
)
from server.services.audit_service import log_audit

router = APIRouter(prefix="/api/endpoints", tags=["endpoints"])

VALID_DB_TYPES = {"sqlserver", "oracle", "postgresql"}


@router.get("", response_model=list[EndpointOut])
async def list_all(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await list_endpoints(db)


@router.post("", response_model=EndpointOut, status_code=status.HTTP_201_CREATED)
async def create(
    body: EndpointCreate, request: Request,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    if body.db_type not in VALID_DB_TYPES:
        raise HTTPException(status_code=400, detail=f"db_type must be one of: {VALID_DB_TYPES}")

    result = await create_endpoint(db, body, admin.id)

    await log_audit(
        db, user_id=admin.id, user_email=admin.email,
        action="endpoint.create", resource_type="endpoint", resource_id=result["id"],
        detail={"name": body.name, "db_type": body.db_type, "host": body.host},
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.get("/{endpoint_id}", response_model=EndpointOut)
async def get_one(endpoint_id: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await get_endpoint(db, endpoint_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")
    return result


@router.put("/{endpoint_id}", response_model=EndpointOut)
async def update(
    endpoint_id: int, body: EndpointUpdate, request: Request,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    result = await update_endpoint(db, endpoint_id, body)
    if result is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    await log_audit(
        db, user_id=admin.id, user_email=admin.email,
        action="endpoint.update", resource_type="endpoint", resource_id=endpoint_id,
        detail=body.model_dump(exclude_none=True, exclude={"password", "oracle_sys_password"}),
        ip_address=request.client.host if request.client else None,
    )
    return result


@router.delete("/{endpoint_id}")
async def delete(
    endpoint_id: int, request: Request,
    admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    deleted = await delete_endpoint(db, endpoint_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    await log_audit(
        db, user_id=admin.id, user_email=admin.email,
        action="endpoint.delete", resource_type="endpoint", resource_id=endpoint_id,
        ip_address=request.client.host if request.client else None,
    )
    return {"message": "Endpoint deleted"}


@router.post("/{endpoint_id}/test", response_model=TestConnectionResponse)
async def test_existing(
    endpoint_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test connection for an existing endpoint."""
    from server.services.endpoint_service import get_decrypted_credentials
    creds = await get_decrypted_credentials(db, endpoint_id)
    if creds is None:
        raise HTTPException(status_code=404, detail="Endpoint not found")

    loop = asyncio.get_event_loop()
    success, message, latency = await loop.run_in_executor(
        None, lambda: test_connection_sync(
            db_type=creds["db_type"], host=creds["host"], port=creds["port"],
            username=creds["username"], password=creds["password"],
            database_name=creds["database_name"], oracle_dsn=creds["oracle_dsn"],
        )
    )
    return TestConnectionResponse(success=success, message=message, latency_ms=latency)


@router.post("/test", response_model=TestConnectionResponse)
async def test_presave(body: TestConnectionRequest):
    """Test connection before saving (with plaintext credentials in body)."""
    if body.db_type not in VALID_DB_TYPES:
        raise HTTPException(status_code=400, detail=f"db_type must be one of: {VALID_DB_TYPES}")

    loop = asyncio.get_event_loop()
    success, message, latency = await loop.run_in_executor(
        None, lambda: test_connection_sync(
            db_type=body.db_type, host=body.host, port=body.port,
            username=body.username, password=body.password,
            database_name=body.database_name, oracle_dsn=body.oracle_dsn,
        )
    )
    return TestConnectionResponse(success=success, message=message, latency_ms=latency)
