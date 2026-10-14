"""Project model for scoped multi-project workspaces."""

import enum
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String

from app.core.database import Base


class ProjectType(str, enum.Enum):
    """Supported project types for a new initiative."""

    DEVELOPMENT = "development"
    MAINTENANCE = "maintenance"
    EXPERIMENT = "experiment"
    RESEARCH = "research"
    OTHER = "other"


class Project(Base):
    """Project record used to scope work across Jira, Confluence, GitHub, and ServiceNow."""

    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    name = Column(String, nullable=False, index=True)
    description = Column(String, default="", nullable=False)
    goal = Column(String, default="", nullable=False)
    project_type = Column(Enum(ProjectType), nullable=False)
    status = Column(String, default="active", nullable=False)

    jira_project_key = Column(String, nullable=True, index=True)
    confluence_space_key = Column(String, nullable=True, index=True)
    github_repo_name = Column(String, nullable=True, index=True)
    servicenow_service_name = Column(String, nullable=True, index=True)

    generate_mock_data = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    is_selected = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
