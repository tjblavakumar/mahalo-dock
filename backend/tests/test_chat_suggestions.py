"""Tests for context-aware chat starter-prompt suggestions.

These cover the deterministic (no-LLM) paths so they run without network access
or an OpenAI key: the pure parsing/fallback helpers, plus generate_suggestions
exercised through its no-key fallback branch.
"""

import asyncio

from app.agent import agent
from app.agent.agent import (
    _fallback_suggestions,
    _parse_suggestion_lines,
    generate_suggestions,
)
from app.models.integration import Integration, IntegrationType
from app.models.user import User, UserRole


def _make_user(role: UserRole) -> User:
    return User(id=1, email="u@example.com", password_hash="x", name="Dev", role=role)


def _make_integration(int_type: IntegrationType) -> Integration:
    return Integration(
        id=1, user_id=1, type=int_type, name=int_type.value, url="http://x", token="t"
    )


class _FakeQuery:
    def __init__(self, results):
        self._results = results

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self._results


class _FakeSession:
    """Minimal stand-in: only supports db.query(Integration).filter(...).all()."""

    def __init__(self, integrations):
        self._integrations = integrations

    def query(self, model):
        if model is Integration:
            return _FakeQuery(self._integrations)
        return _FakeQuery([])


# --- _parse_suggestion_lines ------------------------------------------------

def test_parse_strips_numbering_bullets_and_quotes():
    raw = '1. "Show my open PRs"\n- What issues are mine?\n* Any failed deploys?'
    out = _parse_suggestion_lines(raw, limit=4)
    assert out == ["Show my open PRs", "What issues are mine?", "Any failed deploys?"]


def test_parse_ignores_blank_lines_and_respects_limit():
    raw = "one\n\n\ntwo\nthree\nfour\nfive"
    out = _parse_suggestion_lines(raw, limit=3)
    assert out == ["one", "two", "three"]


# --- _fallback_suggestions --------------------------------------------------

def test_fallback_filters_by_connected_systems():
    # Developer with only Jira connected -> no GitHub/ServiceNow suggestions.
    out = _fallback_suggestions(
        "developer", [_make_integration(IntegrationType.JIRA)], limit=4
    )
    assert len(out) <= 4
    assert all("pull request" not in s.lower() for s in out)
    assert any("assigned to me" in s.lower() for s in out)


def test_fallback_includes_github_when_connected():
    out = _fallback_suggestions(
        "developer", [_make_integration(IntegrationType.GITHUB)], limit=4
    )
    assert any("pull request" in s.lower() for s in out)


def test_fallback_unknown_role_defaults_to_developer():
    out = _fallback_suggestions("nonsense", [_make_integration(IntegrationType.GITHUB)], limit=4)
    assert any("pull request" in s.lower() for s in out)


def test_fallback_returns_generic_when_nothing_qualifies():
    # Executive with no connections: only the no-requirement entry qualifies.
    out = _fallback_suggestions("executive", [], limit=4)
    assert len(out) >= 1
    assert all(isinstance(s, str) and s for s in out)


# --- generate_suggestions (no-key fallback path) ----------------------------

def test_generate_suggestions_uses_fallback_without_openai_key(monkeypatch):
    monkeypatch.setattr(agent.settings, "openai_api_key", "", raising=False)
    db = _FakeSession([_make_integration(IntegrationType.GITHUB)])
    user = _make_user(UserRole.DEVELOPER)

    out = asyncio.run(generate_suggestions(user=user, db=db, project=None, limit=4))

    assert 1 <= len(out) <= 4
    assert all(isinstance(s, str) and s for s in out)
    # GitHub connected -> a PR suggestion should be present.
    assert any("pull request" in s.lower() for s in out)
