"""Chat router: conversation endpoint for the AI agent."""

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agent.agent import chat, execute_proposed_action, generate_suggestions
from app.agent.session import get_session
from app.core.config import settings

logger = logging.getLogger(__name__)
from app.core.database import get_db
from app.models.integration import Integration
from app.models.project import Project
from app.models.user import User
from app.routers.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    """Request body for chat message."""

    message: str
    session_id: Optional[str] = None
    project_id: Optional[int] = None


class ChatResponse(BaseModel):
    """Response from the chat agent."""

    response: str
    proposal: Optional[dict] = None
    systems_queried: list[str] = []
    session_id: str


class ActionApprovalRequest(BaseModel):
    """Request to approve or reject a proposed action."""

    session_id: str
    approved: bool


class ActionResult(BaseModel):
    """Result of executing an approved action."""

    success: bool
    message: str


class SuggestionsRequest(BaseModel):
    """Request body for generating starter-prompt suggestions."""

    project_id: Optional[int] = None


class SuggestionsResponse(BaseModel):
    """Context-aware starter prompts for the chat empty-state."""

    suggestions: list[str] = []


@router.post("", response_model=ChatResponse)
async def send_message(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Send a message to the AI agent and get a response."""
    session_id = request.session_id or str(uuid.uuid4())

    active_project = None
    if request.project_id is not None:
        active_project = (
            db.query(Project)
            .filter(Project.id == request.project_id, Project.user_id == current_user.id)
            .first()
        )
    if active_project is None:
        active_project = (
            db.query(Project)
            .filter(Project.user_id == current_user.id, Project.is_active.is_(True))
            .first()
        )

    try:
        if settings.openai_api_key:
            result = await chat(
                message=request.message,
                user=current_user,
                session_id=session_id,
                db=db,
                project=active_project,
            )
        else:
            logger.warning("OPENAI_API_KEY not set; using keyword demo agent fallback.")
            from app.agent.demo_agent import demo_chat

            result = await demo_chat(
                message=request.message,
                user=current_user,
                session_id=session_id,
                db=db,
                project=active_project,
            )

        return ChatResponse(
            response=result["response"],
            proposal=result.get("proposal"),
            systems_queried=result.get("systems_queried", []),
            session_id=result["session_id"],
        )
    except Exception as e:
        logger.exception("Agent error")
        raise HTTPException(
            status_code=500,
            detail=f"Agent error: {str(e)}",
        )


@router.post("/suggestions", response_model=SuggestionsResponse)
async def suggest_prompts(
    request: SuggestionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate short, context-aware starter prompts for the current user.

    Grounded in the user's role, connected systems, and scoped project. Falls
    back to a deterministic list when the LLM is unavailable.
    """
    active_project = None
    if request.project_id is not None:
        active_project = (
            db.query(Project)
            .filter(Project.id == request.project_id, Project.user_id == current_user.id)
            .first()
        )
    if active_project is None:
        active_project = (
            db.query(Project)
            .filter(Project.user_id == current_user.id, Project.is_active.is_(True))
            .first()
        )

    try:
        suggestions = await generate_suggestions(
            user=current_user,
            db=db,
            project=active_project,
        )
        return SuggestionsResponse(suggestions=suggestions)
    except Exception as e:
        logger.exception("Suggestion generation error")
        raise HTTPException(status_code=500, detail=f"Suggestion error: {str(e)}")


@router.post("/approve", response_model=ActionResult)
async def approve_action(
    request: ActionApprovalRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Approve or reject a proposed write action."""
    session = get_session(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.pending_action:
        raise HTTPException(status_code=400, detail="No pending action to approve")

    if not request.approved:
        # User rejected the action
        session.pending_action = None
        return ActionResult(success=True, message="Action rejected. How else can I help?")

    # Execute the approved action
    integrations = (
        db.query(Integration)
        .filter(Integration.user_id == current_user.id)
        .all()
    )

    try:
        result_message = await execute_proposed_action(session.pending_action, integrations)
        session.pending_action = None
        return ActionResult(success=True, message=result_message)
    except Exception as e:
        session.pending_action = None
        return ActionResult(success=False, message=f"Failed to execute action: {str(e)}")
