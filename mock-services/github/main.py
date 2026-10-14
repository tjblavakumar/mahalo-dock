"""Mock GitHub Service - Simulates GitHub REST API for MAHALO3."""

import os
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

import store
from store import BRANCHES, COMMITS, CONTRIBUTOR_STATS, PULL_REQUESTS, REPOS

app = FastAPI(title="Mock GitHub Service", version="1.0.0")

API_TOKEN = os.environ.get("MOCK_GITHUB_TOKEN", "mock-github-token-12345")


def verify_token(x_api_token: Optional[str] = Header(None)):
    """Validate API token from request header."""
    if x_api_token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid API token")


# --- Health ---

@app.get("/health")
def health():
    return {"status": "healthy", "service": "mock-github", "version": "1.0.0"}


# --- Repos ---

@app.post("/repos", status_code=201)
def create_repo(repo: dict, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    repo_id = str(repo.get("name") or "repo").lower().strip()
    if any(r["id"] == repo_id for r in REPOS):
        raise HTTPException(status_code=409, detail="Repository already exists")

    new_repo = {
        "id": repo_id,
        "name": repo_id,
        "description": repo.get("description") or "",
        "language": repo.get("language") or "Python",
        "default_branch": repo.get("default_branch") or "main",
        "stars": 0,
        "open_issues": 0,
        "last_push": "2026-08-29",
    }
    REPOS.append(new_repo)
    BRANCHES.setdefault(repo_id, [{"name": "main", "protected": True, "last_commit": "2026-08-29"}])
    store.save()
    return new_repo


@app.get("/repos")
def list_repos(x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    return {"repos": REPOS}


@app.get("/repos/{repo_id}")
def get_repo(repo_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    repo = next((r for r in REPOS if r["id"] == repo_id), None)
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


# --- Branches ---

@app.get("/repos/{repo_id}/branches")
def list_branches(repo_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    if repo_id not in BRANCHES:
        raise HTTPException(status_code=404, detail="Repository not found")
    return {"branches": BRANCHES[repo_id]}


class CreateBranchRequest(BaseModel):
    name: str
    from_branch: str = "main"


@app.post("/repos/{repo_id}/branches", status_code=201)
def create_branch(
    repo_id: str,
    request: CreateBranchRequest,
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    if repo_id not in BRANCHES:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Check if branch already exists
    existing = next((b for b in BRANCHES[repo_id] if b["name"] == request.name), None)
    if existing:
        raise HTTPException(status_code=409, detail="Branch already exists")

    new_branch = {
        "name": request.name,
        "protected": False,
        "last_commit": "2026-08-25",
    }
    BRANCHES[repo_id].append(new_branch)
    store.save()
    return new_branch


# --- Pull Requests ---

@app.get("/pulls")
def list_all_pulls(
    status: Optional[str] = Query(None),
    author_id: Optional[str] = Query(None),
    repo_id: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    """Flat list of all pull requests across repositories (optionally filtered)."""
    verify_token(x_api_token)
    prs = list(PULL_REQUESTS)
    if repo_id:
        prs = [pr for pr in prs if pr["repo_id"] == repo_id]
    if status:
        prs = [pr for pr in prs if pr["status"] == status]
    if author_id:
        prs = [pr for pr in prs if pr["author_id"] == author_id]
    return {"pull_requests": prs, "total": len(prs)}


@app.get("/repos/{repo_id}/pulls")
def list_pulls(
    repo_id: str,
    status: Optional[str] = Query(None),
    author_id: Optional[str] = Query(None),
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    prs = [pr for pr in PULL_REQUESTS if pr["repo_id"] == repo_id]

    if status:
        prs = [pr for pr in prs if pr["status"] == status]
    if author_id:
        prs = [pr for pr in prs if pr["author_id"] == author_id]

    return {"pull_requests": prs, "total": len(prs)}


@app.get("/repos/{repo_id}/pulls/{pr_number}")
def get_pull(repo_id: str, pr_number: int, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    pr = next(
        (pr for pr in PULL_REQUESTS if pr["repo_id"] == repo_id and pr["number"] == pr_number),
        None,
    )
    if not pr:
        raise HTTPException(status_code=404, detail="Pull request not found")
    return pr


# --- Commits ---

@app.get("/repos/{repo_id}/commits")
def list_commits(
    repo_id: str,
    branch: Optional[str] = Query(None),
    author: Optional[str] = Query(None, description="Author name or author_id"),
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    commits = [c for c in COMMITS if c["repo_id"] == repo_id]

    if branch:
        commits = [c for c in commits if c["branch"] == branch]
    if author:
        commits = [
            c for c in commits
            if author.lower() in c["author"].lower() or c["author_id"] == author
        ]

    # Sort by date descending
    commits.sort(key=lambda x: x["date"], reverse=True)
    return {"commits": commits, "total": len(commits)}


class CreateCommitRequest(BaseModel):
    branch: str
    message: str
    author_id: str
    additions: int = 0
    deletions: int = 0


@app.post("/repos/{repo_id}/commits", status_code=201)
def create_commit(
    repo_id: str,
    request: CreateCommitRequest,
    x_api_token: Optional[str] = Header(None),
):
    verify_token(x_api_token)
    if repo_id not in BRANCHES:
        raise HTTPException(status_code=404, detail="Repository not found")

    # Verify branch exists
    branch = next((b for b in BRANCHES[repo_id] if b["name"] == request.branch), None)
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    # Find author name
    author_name = request.author_id
    for repo_stats in CONTRIBUTOR_STATS.values():
        for stat in repo_stats:
            if stat["author_id"] == request.author_id:
                author_name = stat["author"]
                break

    new_commit = {
        "id": f"c{len(COMMITS) + 1:03d}",
        "repo_id": repo_id,
        "branch": request.branch,
        "author": author_name,
        "author_id": request.author_id,
        "message": request.message,
        "date": "2026-08-25",
        "additions": request.additions,
        "deletions": request.deletions,
    }
    COMMITS.append(new_commit)
    store.save()
    return new_commit


# --- Stats ---

@app.post("/repos/{repo_id}/readme", status_code=201)
def create_readme(repo_id: str, readme: dict, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    if repo_id not in BRANCHES:
        raise HTTPException(status_code=404, detail="Repository not found")

    doc = {
        "repo_id": repo_id,
        "title": readme.get("title") or "README.md",
        "content": readme.get("content") or "",
        "updated_at": "2026-08-29",
    }
    return doc


@app.get("/repos/{repo_id}/stats")
def get_stats(repo_id: str, x_api_token: Optional[str] = Header(None)):
    verify_token(x_api_token)
    if repo_id not in CONTRIBUTOR_STATS:
        raise HTTPException(status_code=404, detail="Repository not found")

    contributors = CONTRIBUTOR_STATS[repo_id]
    total_commits = sum(c["commits"] for c in contributors)
    total_additions = sum(c["additions"] for c in contributors)
    total_deletions = sum(c["deletions"] for c in contributors)

    return {
        "repo_id": repo_id,
        "contributors": contributors,
        "total_commits": total_commits,
        "total_additions": total_additions,
        "total_deletions": total_deletions,
        "active_branches": len(BRANCHES.get(repo_id, [])),
        "open_prs": len([pr for pr in PULL_REQUESTS if pr["repo_id"] == repo_id and pr["status"] == "open"]),
    }
