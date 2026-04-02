"""Authentication routes."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from server.database import get_db
from server.dependencies import get_current_user
from server.models.user import User
from server.schemas.auth import LoginRequest, LoginResponse, PasswordResetRequest, UserInfo
from server.services.auth_service import verify_password, hash_password, create_access_token
from server.services.audit_service import log_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is deactivated")

    token = create_access_token(user.id, user.email, user.role)

    await log_audit(
        db,
        user_id=user.id,
        user_email=user.email,
        action="auth.login",
        ip_address=request.client.host if request.client else None,
    )

    return LoginResponse(
        access_token=token,
        user=UserInfo(id=user.id, email=user.email, display_name=user.display_name, role=user.role),
    )


@router.post("/reset-password")
async def reset_password(
    body: PasswordResetRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(body.current_password, current_user.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

    current_user.password_hash = hash_password(body.new_password)
    db.add(current_user)

    await log_audit(
        db,
        user_id=current_user.id,
        user_email=current_user.email,
        action="auth.reset_password",
        ip_address=request.client.host if request.client else None,
    )

    return {"message": "Password updated"}
