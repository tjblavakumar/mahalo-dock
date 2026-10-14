"""In-memory session management for agent conversations."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ChatMessage:
    """A single chat message."""
    role: str  # "user", "assistant", "system"
    content: str
    metadata: Optional[dict] = None


@dataclass
class ChatSession:
    """A conversation session with history."""
    session_id: str
    user_id: int
    messages: list[ChatMessage] = field(default_factory=list)
    pending_action: Optional[dict] = None  # For propose & confirm


# In-memory session store (session-scoped, no persistence needed for PoC)
_sessions: dict[str, ChatSession] = {}


def get_or_create_session(session_id: str, user_id: int) -> ChatSession:
    """Get an existing session or create a new one."""
    if session_id not in _sessions:
        _sessions[session_id] = ChatSession(session_id=session_id, user_id=user_id)
    return _sessions[session_id]


def get_session(session_id: str) -> Optional[ChatSession]:
    """Get an existing session."""
    return _sessions.get(session_id)


def clear_session(session_id: str) -> None:
    """Remove a session."""
    _sessions.pop(session_id, None)
