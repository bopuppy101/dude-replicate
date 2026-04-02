"""Audit log routes (admin only)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import require_admin
from server.models.user import User
from server.models.audit_log import AuditLog

router = APIRouter(prefix="/api/audit-log", tags=["audit"])


@router.get("")
async def list_audit_log(
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    resource_type: str | None = None,
    action: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    query = select(AuditLog).order_by(AuditLog.created_at.desc())

    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if action:
        query = query.where(AuditLog.action.ilike(f"%{action}%"))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    entries = result.scalars().all()

    # Get total count
    count_query = select(func.count(AuditLog.id))
    if resource_type:
        count_query = count_query.where(AuditLog.resource_type == resource_type)
    if action:
        count_query = count_query.where(AuditLog.action.ilike(f"%{action}%"))
    total = (await db.execute(count_query)).scalar()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "entries": [
            {
                "id": e.id,
                "user_id": e.user_id,
                "user_email": e.user_email,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "detail": e.detail,
                "ip_address": e.ip_address,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in entries
        ],
    }
