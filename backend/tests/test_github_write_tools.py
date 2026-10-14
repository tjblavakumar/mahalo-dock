"""Unit tests for the GitHub write tools (commit files + open PR) and the
`execute_proposed_action` dispatch, with the adapter HTTP mocked.

These cover Task 7: proposal shape produced by the tools, and that an approved
proposal dispatches the right HTTP call to the adapter and formats the result.
"""

import asyncio
import json
from types import SimpleNamespace

from app.agent.tools.github_tools import _normalize_files_arg, create_github_tools


# --------------------------------------------------------------------------
# Proposal shape
# --------------------------------------------------------------------------

def _get_tool(name):
    tools = create_github_tools("http://adapter:5003", "tok")
    return next(t for t in tools if t.name == name)


def _extract_proposal(blob: str) -> dict:
    assert blob.startswith("__PROPOSAL__") and blob.endswith("__END_PROPOSAL__")
    inner = blob[len("__PROPOSAL__"): -len("__END_PROPOSAL__")]
    return json.loads(inner)


def test_commit_files_proposal_shape():
    tool = _get_tool("github_commit_files")
    out = tool.invoke(
        {
            "repo_id": "repo-1",
            "branch": "feature/x",
            "message": "feat: add thing",
            "files": [{"path": "src/a.py", "content": "print(1)\n"}],
        }
    )
    p = _extract_proposal(out)
    assert p["action"] == "commit_files"
    assert p["system"] == "github"
    assert p["params"]["repo_id"] == "repo-1"
    assert p["params"]["branch"] == "feature/x"
    assert p["params"]["files"] == [{"path": "src/a.py", "content": "print(1)\n"}]
    assert "src/a.py" in p["description"]


def test_open_pull_request_proposal_shape():
    tool = _get_tool("github_open_pull_request")
    out = tool.invoke(
        {
            "repo_id": "repo-1",
            "head": "feature/x",
            "base": "main",
            "title": "My PR",
            "body": "desc",
        }
    )
    p = _extract_proposal(out)
    assert p["action"] == "open_pull_request"
    assert p["params"]["head"] == "feature/x"
    assert p["params"]["base"] == "main"
    assert p["params"]["title"] == "My PR"


def test_commit_files_normalizes_json_string():
    # The LLM sometimes passes files as a JSON string.
    tool = _get_tool("github_commit_files")
    out = tool.invoke(
        {
            "repo_id": "repo-1",
            "branch": "b",
            "message": "m",
            "files": json.dumps([{"path": "x.txt", "content": "hi"}]),
        }
    )
    p = _extract_proposal(out)
    assert p["params"]["files"] == [{"path": "x.txt", "content": "hi"}]


def test_normalize_files_arg_variants():
    assert _normalize_files_arg([{"path": "a", "content": "b"}]) == [{"path": "a", "content": "b"}]
    assert _normalize_files_arg({"path": "a", "content": "b"}) == [{"path": "a", "content": "b"}]
    assert _normalize_files_arg('[{"path":"a","content":"b"}]') == [{"path": "a", "content": "b"}]
    assert _normalize_files_arg("not json") == []
    assert _normalize_files_arg([{"content": "no path"}]) == []
    assert _normalize_files_arg([{"path": "a"}]) == [{"path": "a", "content": ""}]


# --------------------------------------------------------------------------
# execute_proposed_action dispatch (adapter HTTP mocked)
# --------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


class _FakeClient:
    """Records POSTs and returns queued responses keyed by URL suffix."""

    def __init__(self, routes):
        self._routes = routes
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append((url, json))
        for suffix, resp in self._routes.items():
            if url.endswith(suffix):
                return resp
        return _FakeResponse(500, text="no route")


def _integration():
    # Mimic an Integration with .type.value == "github", .url, .token
    return SimpleNamespace(
        type=SimpleNamespace(value="github"),
        url="http://adapter:5003",
        token="tok",
    )


def _patch_httpx(monkeypatch, fake):
    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: fake, raising=False)


def test_execute_commit_files_dispatch(monkeypatch):
    import app.agent.agent as agent

    fake = _FakeClient(
        {
            "/repos/repo-1/commits": _FakeResponse(
                201,
                {
                    "id": "abc123",
                    "branch": "feature/x",
                    "files_committed": ["src/a.py"],
                    "url": "http://localhost:3001/mahalo_admin/payment-service/commit/abc123",
                },
            )
        }
    )
    _patch_httpx(monkeypatch, fake)

    proposal = {
        "action": "commit_files",
        "system": "github",
        "params": {
            "repo_id": "repo-1",
            "branch": "feature/x",
            "message": "feat: add",
            "files": [{"path": "src/a.py", "content": "print(1)\n"}],
        },
    }
    msg = asyncio.run(agent.execute_proposed_action(proposal, [_integration()]))
    assert "src/a.py" in msg
    assert "feature/x" in msg
    assert "localhost:3001" in msg
    # The dispatch sent branch/message/files to the commits endpoint.
    url, body = fake.calls[0]
    assert url.endswith("/repos/repo-1/commits")
    assert body["branch"] == "feature/x"
    assert body["files"] == [{"path": "src/a.py", "content": "print(1)\n"}]


def test_execute_open_pull_request_dispatch(monkeypatch):
    import app.agent.agent as agent

    fake = _FakeClient(
        {
            "/repos/repo-1/pulls": _FakeResponse(
                201,
                {
                    "number": 7,
                    "title": "My PR",
                    "url": "http://localhost:3001/mahalo_admin/payment-service/pulls/7",
                },
            )
        }
    )
    _patch_httpx(monkeypatch, fake)

    proposal = {
        "action": "open_pull_request",
        "system": "github",
        "params": {
            "repo_id": "repo-1",
            "head": "feature/x",
            "base": "main",
            "title": "My PR",
            "body": "desc",
        },
    }
    msg = asyncio.run(agent.execute_proposed_action(proposal, [_integration()]))
    assert "#7" in msg
    assert "localhost:3001" in msg
    url, body = fake.calls[0]
    assert url.endswith("/repos/repo-1/pulls")
    assert body["head"] == "feature/x"
    assert body["base"] == "main"
