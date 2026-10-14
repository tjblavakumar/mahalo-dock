"""Common backend interface for the GitHub adapter.

The adapter exposes a single, stable HTTP contract (see main.py). Behind that
contract, requests are dispatched to one of two interchangeable backends:

- ``mock``  — the original in-memory JSON store (default; offline-friendly).
- ``real``  — backed by a self-hosted Gitea instance.

Both backends implement this same interface so main.py never has to care which
one is active. Methods return plain dicts/lists already shaped like MAHALO's
existing GitHub responses; they raise :class:`BackendError` for anything the
HTTP layer should translate into an error status code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class BackendError(Exception):
    """Raised by a backend to signal an HTTP-translatable error.

    ``status`` is the HTTP status code main.py should return; ``detail`` is the
    human-readable message. This keeps backends free of FastAPI imports.
    """

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class GithubBackend(ABC):
    """Interface implemented by both the mock and Gitea-backed adapters."""

    # --- Repos ---

    @abstractmethod
    def create_repo(self, repo: dict) -> dict:
        """Create a repository. Returns the created repo record."""

    @abstractmethod
    def list_repos(self) -> dict:
        """Return ``{"repos": [...]}``."""

    @abstractmethod
    def get_repo(self, repo_id: str) -> dict:
        """Return a single repo record, or raise BackendError(404)."""

    # --- Branches ---

    @abstractmethod
    def list_branches(self, repo_id: str) -> dict:
        """Return ``{"branches": [...]}`` or raise BackendError(404)."""

    @abstractmethod
    def create_branch(self, repo_id: str, name: str, from_branch: str) -> dict:
        """Create a branch. Returns the created branch record."""

    # --- Pull requests ---

    @abstractmethod
    def list_all_pulls(
        self,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
        repo_id: Optional[str] = None,
    ) -> dict:
        """Return ``{"pull_requests": [...], "total": n}`` across all repos."""

    @abstractmethod
    def list_pulls(
        self,
        repo_id: str,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
    ) -> dict:
        """Return ``{"pull_requests": [...], "total": n}`` for one repo."""

    @abstractmethod
    def get_pull(self, repo_id: str, pr_number: int) -> dict:
        """Return a single PR record, or raise BackendError(404)."""

    @abstractmethod
    def create_pull(self, repo_id: str, request: dict) -> dict:
        """Create a pull request. Returns the created PR record."""

    # --- Commits ---

    @abstractmethod
    def list_commits(
        self,
        repo_id: str,
        branch: Optional[str] = None,
        author: Optional[str] = None,
    ) -> dict:
        """Return ``{"commits": [...], "total": n}``."""

    @abstractmethod
    def create_commit(self, repo_id: str, request: dict) -> dict:
        """Record/create a commit. Returns the created commit record."""

    # --- Docs ---

    @abstractmethod
    def create_readme(self, repo_id: str, readme: dict) -> dict:
        """Create/update a README. Returns the doc record."""

    # --- Stats ---

    @abstractmethod
    def get_stats(self, repo_id: str) -> dict:
        """Return repository statistics, or raise BackendError(404)."""
