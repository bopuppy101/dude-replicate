"""Auth request/response schemas."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"


class UserInfo(BaseModel):
    id: int
    email: str
    display_name: str
    role: str


class PasswordResetRequest(BaseModel):
    current_password: str
    new_password: str
