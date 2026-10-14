"""Mock (in-memory JSON store) backend for the GitHub adapter.

This is the original behavior of the mock GitHub service, lifted verbatim out of
main.py into the common :class:`GithubBackend` interface. It persists to
``data.json`` via ``store`` and is the default backend (``GITHUB_MODE=mock``),
so network-free demos behave exactly as before.
"""

from __future__ import annotations

from typing import Optional

import store
from backend_base import BackendError, GithubBackend
from store import BRANCHES, COMMITS, CONTRIBUTOR_STATS, PULL_REQUESTS, REPOS


class MockBackend(GithubBackend):
    """GitHub adapter backed by the in-memory/JSON-file store."""

    # --- Repos ---

    def create_repo(self, repo: dict) -> dict:
        repo_id = str(repo.get("name") or "repo").lower().strip()
        if any(r["id"] == repo_id for r in REPOS):
            raise BackendError(409, "Repository already exists")

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
        BRANCHES.setdefault(
            repo_id, [{"name": "main", "protected": True, "last_commit": "2026-08-29"}]
        )
        store.save()
        return new_repo

    def list_repos(self) -> dict:
        return {"repos": REPOS}

    def get_repo(self, repo_id: str) -> dict:
        repo = next((r for r in REPOS if r["id"] == repo_id), None)
        if not repo:
            raise BackendError(404, "Repository not found")
        return repo

    # --- Branches ---

    def list_branches(self, repo_id: str) -> dict:
        if repo_id not in BRANCHES:
            raise BackendError(404, "Repository not found")
        return {"branches": BRANCHES[repo_id]}

    def create_branch(self, repo_id: str, name: str, from_branch: str) -> dict:
        if repo_id not in BRANCHES:
            raise BackendError(404, "Repository not found")

        existing = next((b for b in BRANCHES[repo_id] if b["name"] == name), None)
        if existing:
            raise BackendError(409, "Branch already exists")

        new_branch = {
            "name": name,
            "protected": False,
            "last_commit": "2026-08-25",
        }
        BRANCHES[repo_id].append(new_branch)
        store.save()
        return new_branch

    # --- Pull requests ---

    def list_all_pulls(
        self,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
        repo_id: Optional[str] = None,
    ) -> dict:
        prs = list(PULL_REQUESTS)
        if repo_id:
            prs = [pr for pr in prs if pr["repo_id"] == repo_id]
        if status:
            prs = [pr for pr in prs if pr["status"] == status]
        if author_id:
            prs = [pr for pr in prs if pr["author_id"] == author_id]
        return {"pull_requests": prs, "total": len(prs)}

    def list_pulls(
        self,
        repo_id: str,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> dict:
        prs = [pr for pr in PULL_REQUESTS if pr["repo_id"] == repo_id]
        if status:
            prs = [pr for pr in prs if pr["status"] == status]
        if author_id:
            prs = [pr for pr in prs if pr["author_id"] == author_id]
        return {"pull_requests": prs, "total": len(prs)}

    def get_pull(self, repo_id: str, pr_number: int) -> dict:
        pr = next(
            (
                pr
                for pr in PULL_REQUESTS
                if pr["repo_id"] == repo_id and pr["number"] == pr_number
            ),
            None,
        )
        if not pr:
            raise BackendError(404, "Pull request not found")
        return pr

    def create_pull(self, repo_id: str, request: dict) -> dict:
        # Mock mode records a PR in the JSON store (no real git behind it).
        if repo_id not in BRANCHES:
            raise BackendError(404, "Repository not found")

        head = request.get("head") or request.get("branch")
        base = request.get("base") or request.get("target_branch") or "main"
        if not head:
            raise BackendError(422, "head branch is required")

        # Allocate the next PR number globally (mirrors seed-data numbering style).
        next_number = max((pr["number"] for pr in PULL_REQUESTS), default=0) + 1
        new_pr = {
            "id": f"pr-{len(PULL_REQUESTS) + 1}",
            "repo_id": repo_id,
            "number": next_number,
            "title": request.get("title") or head,
            "description": request.get("body") or request.get("description") or "",
            "author": request.get("author") or request.get("author_id") or "mahalo-bot",
            "author_id": request.get("author_id") or "mahalo-bot",
            "status": "open",
            "branch": head,
            "target_branch": base,
            "created_at": "2026-08-29",
            "updated_at": "2026-08-29",
            "additions": request.get("additions", 0),
            "deletions": request.get("deletions", 0),
            "files_changed": request.get("files_changed", 0),
            "reviews": [],
            "linked_story": request.get("linked_story"),
            "url": None,
        }
        PULL_REQUESTS.append(new_pr)
        store.save()
        return new_pr

    # --- Commits ---

    def list_commits(
        self,
        repo_id: str,
        branch: Optional[str] = None,
        author: Optional[str] = None,
    ) -> dict:
        commits = [c for c in COMMITS if c["repo_id"] == repo_id]
        if branch:
            commits = [c for c in commits if c["branch"] == branch]
        if author:
            commits = [
                c
                for c in commits
                if author.lower() in c["author"].lower() or c["author_id"] == author
            ]
        commits.sort(key=lambda x: x["date"], reverse=True)
        return {"commits": commits, "total": len(commits)}

    def create_commit(self, repo_id: str, request: dict) -> dict:
        if repo_id not in BRANCHES:
            raise BackendError(404, "Repository not found")

        # Two accepted shapes:
        #  - legacy metadata: requires branch, message, author_id
        #  - file-contents (Task 5/7): {branch, message, files:[{path,content}]}
        #    author_id is optional here; default it so mock mode still records a
        #    metadata-only commit (it does not write real files).
        has_files = isinstance(request.get("files"), list) or request.get("path")
        required = ("branch", "message") if has_files else ("branch", "message", "author_id")
        for field in required:
            if request.get(field) in (None, ""):
                raise BackendError(422, f"Field '{field}' is required")
        if has_files and not request.get("author_id"):
            request = {**request, "author_id": "mahalo-bot"}

        branch_name = request.get("branch")
        branch = next((b for b in BRANCHES[repo_id] if b["name"] == branch_name), None)
        if not branch:
            raise BackendError(404, "Branch not found")

        author_id = request.get("author_id")
        author_name = author_id
        for repo_stats in CONTRIBUTOR_STATS.values():
            for stat in repo_stats:
                if stat["author_id"] == author_id:
                    author_name = stat["author"]
                    break

        new_commit = {
            "id": f"c{len(COMMITS) + 1:03d}",
            "repo_id": repo_id,
            "branch": branch_name,
            "author": author_name,
            "author_id": author_id,
            "message": request.get("message"),
            "date": "2026-08-25",
            "additions": request.get("additions", 0),
            "deletions": request.get("deletions", 0),
        }
        COMMITS.append(new_commit)
        store.save()
        return new_commit

    # --- Docs ---

    def create_readme(self, repo_id: str, readme: dict) -> dict:
        if repo_id not in BRANCHES:
            raise BackendError(404, "Repository not found")
        return {
            "repo_id": repo_id,
            "title": readme.get("title") or "README.md",
            "content": readme.get("content") or "",
            "updated_at": "2026-08-29",
        }

    # --- Stats ---

    def get_stats(self, repo_id: str) -> dict:
        if repo_id not in CONTRIBUTOR_STATS:
            raise BackendError(404, "Repository not found")

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
            "open_prs": len(
                [
                    pr
                    for pr in PULL_REQUESTS
                    if pr["repo_id"] == repo_id and pr["status"] == "open"
                ]
            ),
        }
