"""Pydantic schemas for authentication endpoints."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserRegisterRequest(BaseModel):
    """Request body for user registration."""

    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    role: UserRole


class UserLoginRequest(BaseModel):
    """Request body for user login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response containing the JWT access token."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Response containing user information."""

    id: int
    email: str
    name: str
    role: UserRole
    created_at: datetime
    # Mock-system identity (dev-1..dev-6) this login maps to, so the dashboard
    # and agent key off the same id. Resolved from the email (see services.identity).
    developer_id: str | None = None

    class Config:
        from_attributes = True
