"""Project router: create projects, generate proposals, and manage selection."""

import re
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.integration import Integration
from app.models.project import Project, ProjectType
from app.models.user import User
from app.routers.auth import get_current_user
from app.schemas.project import (
    ProjectCreateRequest,
    ProjectProposalRequest,
    ProjectProposalResponse,
    ProjectResponse,
    ProjectSelectionRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])


def _slugify(value: str, max_length: int = 10) -> str:
    """Create a compact uppercase slug for project IDs."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "", value).upper()
    if not cleaned:
        cleaned = "PROJ"
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def _make_unique_candidate(base: str, existing_values: set[str]) -> str:
    """Append a suffix if the base value already exists."""
    candidate = base
    counter = 2
    while candidate in existing_values:
        candidate = f"{base}{counter}"
        counter += 1
    return candidate


def _serialize_project_type(project_type) -> str:
    """Normalize a project type value to a lowercase string."""
    if hasattr(project_type, "value"):
        return str(project_type.value).lower()
    return str(project_type).lower()


def build_project_bootstrap_payloads(project: Project) -> list[dict]:
    """Build the bootstrap resource creation requests for a newly approved project."""
    project_type = _serialize_project_type(project.project_type)
    project_name = project.name or "Project"
    jira_key = project.jira_project_key or _slugify(project_name, max_length=8)
    space_key = project.confluence_space_key or _slugify(project_name, max_length=8)
    repo_name = project.github_repo_name or re.sub(r"[^a-z0-9]+", "-", project_name.lower()).strip("-") or "project"
    repo_name = repo_name[:30].rstrip("-")
    project_description = project.description or project.goal or f"Project workspace for {project_name}."
    project_goal = project.goal or project.description or "TBD"

    return [
        {
            "service": "jira",
            "method": "POST",
            "path": "/projects",
            "body": {
                "id": jira_key.upper(),
                "name": project_name,
                "description": project_description,
                "status": "active",
                "lead": "dev-1",
            },
        },
        {
            "service": "jira",
            "method": "POST",
            "path": "/stories",
            "body": {
                "project_id": jira_key.upper(),
                "title": f"Initial setup: {project_name}",
                "description": f"Initial project setup for {project_name}.\n\nGoal: {project_goal}",
                "priority": "medium",
                "story_points": 3,
                "assignee": None,
                "sprint_id": None,
            },
        },
        {
            "service": "confluence",
            "method": "POST",
            "path": "/spaces",
            "body": {
                "id": space_key.upper(),
                "name": project_name,
                "description": project_description,
            },
        },
        {
            "service": "confluence",
            "method": "POST",
            "path": f"/spaces/{space_key.upper()}/pages",
            "body": {
                "title": "Project Overview",
                "content": (
                    f"# {project_name}\n\n"
                    f"## Goal\n{project_goal}\n\n"
                    f"## Description\n{project_description}\n"
                ),
            },
        },
        {
            "service": "github",
            "method": "POST",
            "path": "/repos",
            "body": {
                "name": repo_name,
                "description": project_description,
                "default_branch": "main",
                "private": False,
            },
        },
        {
            "service": "github",
            "method": "POST",
            "path": f"/repos/{repo_name}/readme",
            "body": {
                "title": "README.md",
                "content": (
                    f"# {project_name}\n\n"
                    f"{project_description}\n\n"
                    f"## Goal\n{project_goal}\n\n"
                    f"## Type\n{project_type}\n"
                ),
            },
        },
    ]


async def bootstrap_project_resources(project: Project, db: Session) -> None:
    """Create the initial Jira/Confluence/GitHub resources for a project if matching integrations are configured."""
    integrations = db.query(Integration).filter(Integration.user_id == project.user_id).all()
    for action in build_project_bootstrap_payloads(project):
        integration = next((item for item in integrations if item.type.value == action["service"]), None)
        if integration is None:
            continue

        url = f"{integration.url.rstrip('/')}{action['path']}"
        payload = action.get("body")
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.request(
                    action["method"],
                    url,
                    headers={"X-API-Token": integration.token},
                    json=payload,
                )
        except Exception:
            continue


def _build_project_proposal(name: str, description: str, goal: str, project_type: str) -> ProjectProposalResponse:
    """Generate project identifiers based on the project name and type."""
    slug = _slugify(name, max_length=10)
    base_jira = _slugify(name, max_length=8)
    if len(base_jira) < 2:
        base_jira = "PRJ"

    base_space = _slugify(name, max_length=8)
    base_repo = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    if len(base_repo) > 30:
        base_repo = base_repo[:30].rstrip("-")

    proposal = ProjectProposalResponse(
        jira_project_key=base_jira,
        confluence_space_key=base_space,
        github_repo_name=base_repo,
        servicenow_service_name=_slugify(f"{name} {project_type}", max_length=15),
    )
    return proposal


def _generate_unique_project_names(db: Session, user_id: int, proposal: ProjectProposalResponse) -> ProjectProposalResponse:
    """Check for existing names and make them unique within the user's project records."""
    existing = db.query(Project).filter(Project.user_id == user_id).all()
    seen = {
        p.jira_project_key for p in existing if p.jira_project_key
    } | {
        p.confluence_space_key for p in existing if p.confluence_space_key
    } | {
        p.github_repo_name for p in existing if p.github_repo_name
    } | {
        p.servicenow_service_name for p in existing if p.servicenow_service_name
    }

    proposal.jira_project_key = _make_unique_candidate(proposal.jira_project_key, {v for v in seen if v and v.upper() == v})
    proposal.confluence_space_key = _make_unique_candidate(proposal.confluence_space_key, {v for v in seen if v and v.upper() == v})
    proposal.github_repo_name = _make_unique_candidate(proposal.github_repo_name, {v for v in seen if v and v.lower() == v})
    proposal.servicenow_service_name = _make_unique_candidate(proposal.servicenow_service_name, {v for v in seen if v and v.upper() == v})
    return proposal


@router.post("/proposal", response_model=ProjectProposalResponse)
def propose_project(
    request: ProjectProposalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate a project proposal based on the project description and current usage."""
    proposal = _build_project_proposal(
        request.name,
        request.description,
        request.goal,
        request.project_type.value,
    )
    return _generate_unique_project_names(db, current_user.id, proposal)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: ProjectCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new project and immediately persist the selected system identifiers."""
    if not request.jira_project_key:
        request.jira_project_key = _slugify(request.name, max_length=8)
    if not request.confluence_space_key:
        request.confluence_space_key = _slugify(request.name, max_length=8)
    if not request.github_repo_name:
        request.github_repo_name = re.sub(r"[^a-z0-9]+", "-", request.name.lower()).strip("-") or "project"
    if not request.servicenow_service_name:
        request.servicenow_service_name = _slugify(f"{request.name} {request.project_type.value}", max_length=15)

    request.jira_project_key = _make_unique_candidate(request.jira_project_key.upper(), {p.jira_project_key for p in db.query(Project).filter(Project.user_id == current_user.id).all() if p.jira_project_key})
    request.confluence_space_key = _make_unique_candidate(request.confluence_space_key.upper(), {p.confluence_space_key for p in db.query(Project).filter(Project.user_id == current_user.id).all() if p.confluence_space_key})
    request.github_repo_name = _make_unique_candidate(request.github_repo_name.lower(), {p.github_repo_name for p in db.query(Project).filter(Project.user_id == current_user.id).all() if p.github_repo_name})
    request.servicenow_service_name = _make_unique_candidate(request.servicenow_service_name.upper(), {p.servicenow_service_name for p in db.query(Project).filter(Project.user_id == current_user.id).all() if p.servicenow_service_name})

    project = Project(
        user_id=current_user.id,
        name=request.name,
        description=request.description,
        goal=request.goal,
        project_type=request.project_type,
        status="active",
        jira_project_key=request.jira_project_key,
        confluence_space_key=request.confluence_space_key,
        github_repo_name=request.github_repo_name,
        servicenow_service_name=request.servicenow_service_name,
        generate_mock_data=request.generate_mock_data,
        is_active=True,
        is_selected=True,
    )

    # Ensure only one active project remains true for this user.
    existing_active = (
        db.query(Project)
        .filter(Project.user_id == current_user.id, Project.is_active.is_(True))
        .all()
    )
    for item in existing_active:
        if item.id != project.id:
            item.is_active = False

    db.add(project)
    db.commit()
    db.refresh(project)

    if request.generate_mock_data:
        await bootstrap_project_resources(project, db)

    return project


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return all projects for the current user."""
    return (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.post("/sync", response_model=list[ProjectResponse])
async def sync_projects(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import projects that exist in the connected Jira into the local project list.

    Reads the projects from the user's configured Jira integration and creates a
    local Project row for any that aren't already linked (matched on
    jira_project_key). Existing projects are left untouched. Returns the full,
    refreshed project list.
    """
    jira = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id, Integration.type == "jira")
        .first()
    )

    # Without a Jira connection there's nothing to import; return what we have.
    existing_projects = (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )
    if jira is None:
        return existing_projects

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{jira.url.rstrip('/')}/projects",
                headers={"X-API-Token": jira.token},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to read projects from Jira: {exc}",
        )

    jira_projects = payload.get("projects", []) if isinstance(payload, dict) else []

    # Existing links, case-insensitive, so we don't create duplicates.
    linked_keys = {
        (p.jira_project_key or "").upper()
        for p in existing_projects
        if p.jira_project_key
    }

    created_any = False
    for jira_project in jira_projects:
        jira_id = str(jira_project.get("id") or "").strip()
        if not jira_id or jira_id.upper() in linked_keys:
            continue

        name = jira_project.get("name") or jira_id
        description = jira_project.get("description") or ""
        space_key = _slugify(name, max_length=8)
        repo_name = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
        repo_name = repo_name[:30].rstrip("-")

        project = Project(
            user_id=current_user.id,
            name=name,
            description=description,
            goal="",
            project_type=ProjectType.DEVELOPMENT,
            status=jira_project.get("status") or "active",
            jira_project_key=jira_id.upper(),
            confluence_space_key=space_key.upper(),
            github_repo_name=repo_name,
            servicenow_service_name=_slugify(name, max_length=15),
            generate_mock_data=False,
            is_active=False,
            # Imported projects are selected by default so they appear in the
            # dashboard/chat scope immediately.
            is_selected=True,
        )
        db.add(project)
        linked_keys.add(jira_id.upper())
        created_any = True

    if created_any:
        db.commit()

    return (
        db.query(Project)
        .filter(Project.user_id == current_user.id)
        .order_by(Project.created_at.desc())
        .all()
    )


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return a specific project for the current user."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return project


@router.put("/{project_id}/selection", response_model=ProjectResponse)
def update_project_selection(
    project_id: int,
    request: ProjectSelectionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set the active and selected state for a project."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    if request.is_active:
        active_projects = (
            db.query(Project)
            .filter(Project.user_id == current_user.id, Project.is_active.is_(True))
            .all()
        )
        for item in active_projects:
            if item.id != project_id:
                item.is_active = False

    project.is_active = request.is_active
    project.is_selected = request.is_selected
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a project and its linked IDs."""
    project = (
        db.query(Project)
        .filter(Project.id == project_id, Project.user_id == current_user.id)
        .first()
    )
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    db.delete(project)
    db.commit()
