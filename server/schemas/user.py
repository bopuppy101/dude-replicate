"""User request/response schemas."""

from datetime import datetime
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    role: str = "dude_replicate_operator"


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    display_name: str | None = None
    role: str | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
