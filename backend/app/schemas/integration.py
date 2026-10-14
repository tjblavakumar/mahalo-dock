"""Pydantic schemas for integration endpoints."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.integration import IntegrationType


class IntegrationCreateRequest(BaseModel):
    """Request body for creating an integration."""

    type: IntegrationType
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(min_length=1)
    token: str = Field(min_length=1)
    project_scope: Optional[str] = None


class IntegrationResponse(BaseModel):
    """Response containing integration information."""

    id: int
    user_id: int
    type: IntegrationType
    name: str
    url: str
    project_scope: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class IntegrationTestResponse(BaseModel):
    """Response from testing an integration connection."""

    success: bool
    message: str
    service_info: Optional[dict] = None
