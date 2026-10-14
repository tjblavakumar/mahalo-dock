"""GitHub adapter service for MAHALO-dock.

Exposes a single stable HTTP contract (the original mock-GitHub API with
``X-API-Token`` auth) and dispatches each request to one of two interchangeable
backends chosen by the ``GITHUB_MODE`` environment variable:

- ``mock`` (default) — the original in-memory JSON store; offline-friendly.
- ``real``            — backed by a self-hosted Gitea instance.

The contract, auth, request models, status codes, and response shapes are
identical in both modes, so MAHALO's agent tools, proxy, and dashboard need no
changes when the mode is flipped.
"""

import logging
import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

from backend_base import BackendError, GithubBackend

logger = logging.getLogger("github-adapter")

app = FastAPI(title="MAHALO GitHub Adapter", version="2.0.0")

API_TOKEN = os.environ.get("MOCK_GITHUB_TOKEN", "mock-github-token-12345")
GITHUB_MODE = os.environ.get("GITHUB_MODE", "mock").strip().lower()


def _build_backend() -> GithubBackend:
    """Instantiate the backend selected by GITHUB_MODE (default: mock)."""
    if GITHUB_MODE == "real":
        from gitea_backend import GiteaBackend

        logger.info("GITHUB_MODE=real → using Gitea-backed adapter")
        return GiteaBackend()

    if GITHUB_MODE != "mock":
        logger.warning("Unknown GITHUB_MODE=%r; falling back to 'mock'", GITHUB_MODE)
    else:
        logger.info("GITHUB_MODE=mock → using in-memory JSON store")
    from mock_backend import MockBackend

    return MockBackend()


backend: GithubBackend = _build_backend()


def verify_token(x_api_token: Optional[str] = Header(None)):
    """Validate API token from request header."""
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")


def _call(fn, *args, **kwargs):
    """Invoke a backend method, translating BackendError into HTTPException."""
    try:
        return fn(*args, **kwargs)
    except BackendError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


# --- Request models (unchanged contract) ---

class CreateBranchRequest(BaseModel):
    name: str
    from_branch: str = "main"


class CreateCommitRequest(BaseModel):
    branch: str
    message: str
    author_id: str
    additions: int = 0
    deletions: int = 0


# --- Health ---

@app.get("/health")
def health():
    return {
        "status": "healthy",
        "service": "github-adapter",
        "version": "2.0.0",
        "mode": GITHUB_MODE,
    }


# --- Repos ---

@app.post("/repos", status_code=201)
def create_repo(repo: dict, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.create_repo, repo)


@app.get("/repos")
def list_repos(x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.list_repos)


@app.get("/repos/{repo_id}")
def get_repo(repo_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.get_repo, repo_id)


# --- Branches ---

@app.get("/repos/{repo_id}/branches")
def list_branches(repo_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.list_branches, repo_id)


@app.post("/repos/{repo_id}/branches", status_code=201)
def create_branch(
    repo_id: str,
    request: CreateBranchRequest,
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    return _call(backend.create_branch, repo_id, request.name, request.from_branch)


# --- Pull Requests ---

@app.get("/pulls")
def list_all_pulls(
    status: Optional[str] = Query(None),
    author_id: Optional[str] = Query(None),
    repo_id: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    return _call(backend.list_all_pulls, status, author_id, repo_id)


@app.get("/repos/{repo_id}/pulls")
def list_pulls(
    repo_id: str,
    status: Optional[str] = Query(None),
    author_id: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    return _call(backend.list_pulls, repo_id, status, author_id)


@app.get("/repos/{repo_id}/pulls/{pr_number}")
def get_pull(repo_id: str, pr_number: int, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.get_pull, repo_id, pr_number)


@app.post("/repos/{repo_id}/pulls", status_code=201)
def create_pull(repo_id: str, request: dict, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.create_pull, repo_id, request)


# --- Commits ---

@app.get("/repos/{repo_id}/commits")
def list_commits(
    repo_id: str,
    branch: Optional[str] = Query(None),
    author: Optional[str] = Query(None, description="Author name or author_id"),
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    return _call(backend.list_commits, repo_id, branch, author)


@app.post("/repos/{repo_id}/commits", status_code=201)
def create_commit(
    repo_id: str,
    request: dict,
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    # Accept the legacy metadata-only shape as well as the new file-contents
    # shape (Task 5). The backend decides what it supports.
    return _call(backend.create_commit, repo_id, request)


# --- Docs ---

@app.post("/repos/{repo_id}/readme", status_code=201)
def create_readme(repo_id: str, readme: dict, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.create_readme, repo_id, readme)


# --- Stats ---

@app.get("/repos/{repo_id}/stats")
def get_stats(repo_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return _call(backend.get_stats, repo_id)
