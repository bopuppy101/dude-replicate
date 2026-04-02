"""Audit logging service."""

from sqlalchemy.ext.asyncio import AsyncSession

from server.models.audit_log import AuditLog


async def log_audit(
    db: AsyncSession,
    *,
    user_id: int | None = None,
    user_email: str | None = None,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    detail: dict | None = None,
    ip_address: str | None = None,
) -> None:
    """Write an audit log entry."""
    entry = AuditLog(
        user_id=user_id,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        detail=detail,
        ip_address=ip_address,
    )
    db.add(entry)
    await db.flush()
