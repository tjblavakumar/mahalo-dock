"""Pydantic schemas for project creation and selection."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.project import ProjectType


class ProjectProposalRequest(BaseModel):
    """Request to generate a project proposal and suggested IDs."""

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="")
    goal: str = Field(default="")
    project_type: ProjectType = ProjectType.DEVELOPMENT


class ProjectProposalResponse(BaseModel):
    """Suggested keys and names for the new project."""

    jira_project_key: str
    confluence_space_key: str
    github_repo_name: str
    servicenow_service_name: str


class ProjectCreateRequest(ProjectProposalRequest):
    """Request body for creating a project after approval."""

    jira_project_key: Optional[str] = None
    confluence_space_key: Optional[str] = None
    github_repo_name: Optional[str] = None
    servicenow_service_name: Optional[str] = None
    generate_mock_data: bool = False


class ProjectResponse(BaseModel):
    """Serialized project information."""

    id: int
    user_id: int
    name: str
    description: str
    goal: str
    project_type: ProjectType
    status: str
    jira_project_key: Optional[str]
    confluence_space_key: Optional[str]
    github_repo_name: Optional[str]
    servicenow_service_name: Optional[str]
    generate_mock_data: bool
    is_active: bool
    is_selected: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectSelectionRequest(BaseModel):
    """Request to mark a project as active or selected."""

    is_active: bool = False
    is_selected: bool = False
