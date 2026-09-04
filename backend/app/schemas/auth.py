"""Auth request/response schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class UserProfileUpdateRequest(BaseModel):
    """Self-service profile update — name only (privilege-safe)."""

    name: str = Field(min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("name must not be empty")
        return stripped



class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=10, max_length=256)

    @field_validator("new_password")
    @classmethod
    def reject_same_as_current(cls, value: str, info) -> str:
        current = info.data.get("current_password")
        if current is not None and value == current:
            raise ValueError("new password must differ from current password")
        return value


class UserPublic(BaseModel):
    id: UUID
    email: str
    name: str
    status: str
    system_role: str
    must_change_password: bool

    model_config = {"from_attributes": True}


class SessionInfo(BaseModel):
    expires_at: datetime
    absolute_expires_at: datetime


class LoginResponse(BaseModel):
    user: UserPublic
    session: SessionInfo


class CsrfResponse(BaseModel):
    csrf_token: str
