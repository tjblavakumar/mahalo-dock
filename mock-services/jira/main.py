"""Mock Jira Service - Simulates Jira REST API for MAHALO3."""

import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

import store
from store import DEVELOPERS, PROJECTS, SPRINTS, STORIES

app = FastAPI(title="Mock Jira Service", version="1.0.0")

API_TOKEN = os.environ.get("MOCK_JIRA_TOKEN", "mock-jira-token-12345")


def verify_token(x_api_token: Optional[str] = Header(None)):
    """Validate API token from request header."""
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")


# --- Health ---

@app.get("/health")
def health():
    return {"status": "healthy", "service": "mock-jira", "version": "1.0.0"}


# --- Projects ---

@app.get("/projects")
def list_projects(x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return {"projects": PROJECTS}


@app.post("/projects", status_code=201)
def create_project(project: dict, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    project_id = str(project.get("id") or project.get("project_id") or "PROJ").upper()
    if any(p["id"] == project_id for p in PROJECTS):
        raise HTTPException(status_code=409, detail="Project already exists")

    new_project = {
        "id": project_id,
        "name": project.get("name") or project_id,
        "description": project.get("description") or "",
        "status": project.get("status") or "active",
        "lead": project.get("lead") or "dev-1",
    }
    PROJECTS.append(new_project)
    store.save()
    return new_project


@app.get("/projects/{project_id}")
def get_project(project_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    project = next((p for p in PROJECTS if p["id"] == project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.get("/projects/{project_id}/board")
def get_board(project_id: str, x_api_token: Optional[str] = Header(None)):
    """Get sprint board (active sprint stories grouped by status)."""
    verify_token(x_api_token)

    # Find active sprint for this project
    active_sprint = next(
        (s for s in SPRINTS if s["project_id"] == project_id and s["status"] == "active"),
        None,
    )
    if not active_sprint:
        return {"sprint": None, "columns": {}}

    sprint_stories = [s for s in STORIES if s["sprint_id"] == active_sprint["id"]]
    columns = {
        "todo": [s for s in sprint_stories if s["status"] == "todo"],
        "in_progress": [s for s in sprint_stories if s["status"] == "in_progress"],
        "in_review": [s for s in sprint_stories if s["status"] == "in_review"],
        "done": [s for s in sprint_stories if s["status"] == "done"],
    }
    return {"sprint": active_sprint, "columns": columns}


@app.get("/stories")
def list_all_stories(
    status: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    project_id: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    """Flat list of all stories across projects (optionally filtered)."""
    verify_token(x_api_token)
    stories = list(STORIES)
    if project_id:
        stories = [s for s in stories if s["project_id"] == project_id]
    if status:
        stories = [s for s in stories if s["status"] == status]
    if assignee:
        stories = [s for s in stories if s["assignee"] == assignee]
    return {"stories": stories, "total": len(stories)}


@app.get("/projects/{project_id}/stories")
def list_stories(
    project_id: str,
    status: Optional[str] = Query(None),
    assignee: Optional[str] = Query(None),
    sprint_id: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    """List stories for a project with optional filters."""
    verify_token(x_api_token)

    stories = [s for s in STORIES if s["project_id"] == project_id]

    if status:
        stories = [s for s in stories if s["status"] == status]
    if assignee:
        stories = [s for s in stories if s["assignee"] == assignee]
    if sprint_id:
        stories = [s for s in stories if s["sprint_id"] == sprint_id]

    return {"stories": stories, "total": len(stories)}


# --- Stories ---

@app.get("/stories/{story_id}")
def get_story(story_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    story = next((s for s in STORIES if s["id"] == story_id), None)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    # Enrich with assignee details
    result = dict(story)
    if story["assignee"]:
        dev = next((d for d in DEVELOPERS if d["id"] == story["assignee"]), None)
        result["assignee_details"] = dev

    return result


class CreateStoryRequest(BaseModel):
    project_id: str
    title: str
    description: str = ""
    priority: str = "medium"
    story_points: int = 0
    assignee: Optional[str] = None
    sprint_id: Optional[str] = None


@app.post("/stories", status_code=201)
def create_story(request: CreateStoryRequest, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)

    # Validate project exists
    project = next((p for p in PROJECTS if p["id"] == request.project_id), None)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Generate story ID
    project_stories = [s for s in STORIES if s["project_id"] == request.project_id]
    max_num = 0
    for s in project_stories:
        num = int(s["id"].split("-")[1])
        if num > max_num:
            max_num = num
    new_id = f"{request.project_id}-{max_num + 1}"

    new_story = {
        "id": new_id,
        "project_id": request.project_id,
        "sprint_id": request.sprint_id,
        "title": request.title,
        "description": request.description,
        "status": "todo",
        "priority": request.priority,
        "story_points": request.story_points,
        "assignee": request.assignee,
        "acceptance_criteria": [],
        "comments": [],
    }
    STORIES.append(new_story)
    store.save()
    return new_story


class UpdateStoryRequest(BaseModel):
    status: Optional[str] = None
    assignee: Optional[str] = None
    priority: Optional[str] = None
    sprint_id: Optional[str] = None
    story_points: Optional[int] = None


@app.put("/stories/{story_id}")
def update_story(
    story_id: str,
    request: UpdateStoryRequest,
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    story = next((s for s in STORIES if s["id"] == story_id), None)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    if request.status is not None:
        story["status"] = request.status
    if request.assignee is not None:
        story["assignee"] = request.assignee
    if request.priority is not None:
        story["priority"] = request.priority
    if request.sprint_id is not None:
        story["sprint_id"] = request.sprint_id
    if request.story_points is not None:
        story["story_points"] = request.story_points

    store.save()
    return story


# --- Sprints ---

@app.get("/sprints/{project_id}")
def list_sprints(project_id: str, x_api_token: Optional[str] = Header(None)):
    """List sprints for a project with velocity data."""
    verify_token(x_api_token)

    project_sprints = [s for s in SPRINTS if s["project_id"] == project_id]

    # Calculate velocity for active sprint (sum of done story points)
    for sprint in project_sprints:
        if sprint["status"] == "active":
            done_stories = [
                s for s in STORIES
                if s["sprint_id"] == sprint["id"] and s["status"] == "done"
            ]
            sprint["completed_points"] = sum(s["story_points"] for s in done_stories)
            total_stories = [s for s in STORIES if s["sprint_id"] == sprint["id"]]
            sprint["total_points"] = sum(s["story_points"] for s in total_stories)

    return {"sprints": project_sprints}


# --- Developers ---

@app.get("/developers")
def list_developers(x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return {"developers": DEVELOPERS}
