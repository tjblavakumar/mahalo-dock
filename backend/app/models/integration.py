"""Integration model for managing connections to external services."""

import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String

from app.core.database import Base


class IntegrationType(str, enum.Enum):
    """Supported integration types."""

    JIRA = "jira"
    CONFLUENCE = "confluence"
    GITHUB = "github"
    SERVICENOW = "servicenow"


class Integration(Base):
    """Integration model representing a connected external service."""

    __tablename__ = "integrations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    type = Column(Enum(IntegrationType), nullable=False)
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    token = Column(String, nullable=False)
    project_scope = Column(String, nullable=True)  # Optional: scope to specific project
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
