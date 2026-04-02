"""User management routes (admin only)."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import require_admin
from server.models.user import User
from server.schemas.user import UserCreate, UserUpdate, UserOut
from server.services.auth_service import hash_password
from server.services.audit_service import log_audit

router = APIRouter(prefix="/api/users", tags=["users"])

VALID_ROLES = {"dude_replicate_admin", "dude_replicate_operator"}


@router.get("", response_model=list[UserOut])
async def list_users(admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).order_by(User.id))
    return result.scalars().all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate, request: Request, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db),
):
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {VALID_ROLES}")

    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role=body.role,
    )
    db.add(user)
    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        user_email=admin.email,
        action="user.create",
        resource_type="user",
        resource_id=user.id,
        detail={"email": user.email, "role": user.role},
        ip_address=request.client.host if request.client else None,
    )
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    body: UserUpdate,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of: {VALID_ROLES}")

    changes = {}
    for field in ("email", "display_name", "role", "is_active"):
        val = getattr(body, field)
        if val is not None:
            changes[field] = val
            setattr(user, field, val)

    db.add(user)
    await db.flush()

    await log_audit(
        db,
        user_id=admin.id,
        user_email=admin.email,
        action="user.update",
        resource_type="user",
        resource_id=user.id,
        detail=changes,
        ip_address=request.client.host if request.client else None,
    )
    return user


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    request: Request,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.add(user)

    await log_audit(
        db,
        user_id=admin.id,
        user_email=admin.email,
        action="user.deactivate",
        resource_type="user",
        resource_id=user.id,
        ip_address=request.client.host if request.client else None,
    )
    return {"message": f"User {user.email} deactivated"}
