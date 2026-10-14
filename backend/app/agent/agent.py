"""Main agent orchestrator using LangChain with OpenAI."""

import json
import logging
import uuid
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from sqlalchemy.orm import Session

from app.agent.markup_utils import clean_tool_markup, parse_text_tool_calls
from app.agent.prompts import ROLE_PROMPTS
from app.agent.session import ChatMessage, ChatSession, get_or_create_session
from app.agent.tools.confluence_tools import create_confluence_tools
from app.agent.tools.github_tools import create_github_tools
from app.agent.tools.jira_tools import create_jira_tools
from app.agent.tools.servicenow_tools import create_servicenow_tools
from app.core.config import settings
from app.models.integration import Integration
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)


def _get_user_integrations(user_id: int, db: Session) -> list[Integration]:
    """Get all integrations for a user."""
    return db.query(Integration).filter(Integration.user_id == user_id).all()


def _build_tools(integrations: list[Integration]) -> list:
    """Build tool list based on user's configured integrations."""
    tools = []
    for integration in integrations:
        if integration.type.value == "jira":
            tools.extend(create_jira_tools(integration.url, integration.token))
        elif integration.type.value == "confluence":
            tools.extend(create_confluence_tools(integration.url, integration.token))
        elif integration.type.value == "github":
            tools.extend(create_github_tools(integration.url, integration.token))
        elif integration.type.value == "servicenow":
            tools.extend(create_servicenow_tools(integration.url, integration.token))
    return tools


def _build_integrations_context(integrations: list[Integration]) -> str:
    """Build a description of available integrations for the system prompt."""
    if not integrations:
        return "No integrations configured. Ask the user to set up connections first."

    context = ""
    for i in integrations:
        context += f"- {i.type.value.title()}: {i.name} ({i.url})"
        if i.project_scope:
            context += f" [Scope: {i.project_scope}]"
        context += "\n"
    return context


def _extract_proposal(content: str) -> tuple[Optional[dict], str]:
    """Extract a proposal from tool output if present."""
    if "__PROPOSAL__" in content and "__END_PROPOSAL__" in content:
        start = content.index("__PROPOSAL__") + len("__PROPOSAL__")
        end = content.index("__END_PROPOSAL__")
        proposal_json = content[start:end]
        try:
            proposal = json.loads(proposal_json)
            return proposal, content[:content.index("__PROPOSAL__")]
        except json.JSONDecodeError:
            pass
    return None, content


async def execute_proposed_action(proposal: dict, integrations: list[Integration]) -> str:
    """Execute a previously proposed write action after user approval."""
    import httpx

    action = proposal.get("action")
    system = proposal.get("system")
    params = proposal.get("params", {})

    # Find the relevant integration
    integration = next(
        (i for i in integrations if i.type.value == system),
        None,
    )
    if not integration:
        return f"Error: No {system} integration configured."

    async with httpx.AsyncClient(timeout=10.0) as client:
        headers = {"X-API-Token": integration.token}

        if action == "create_story":
            response = await client.post(
                f"{integration.url}/stories",
                headers=headers,
                json=params,
            )
            if response.status_code == 201:
                data = response.json()
                return f"✅ Story created successfully: **{data['id']}** - {data['title']}"
            else:
                return f"❌ Failed to create story: {response.text}"

        elif action == "update_story":
            story_id = params["story_id"]
            response = await client.put(
                f"{integration.url}/stories/{story_id}",
                headers=headers,
                json=params.get("changes", {}),
            )
            if response.status_code == 200:
                data = response.json()
                return f"✅ Story updated successfully: **{data['id']}** - {data['title']}"
            else:
                return f"❌ Failed to update story {story_id}: {response.text}"

        elif action == "create_branch":
            response = await client.post(
                f"{integration.url}/repos/{params['repo_id']}/branches",
                headers=headers,
                json={"name": params["branch_name"], "from_branch": params.get("from_branch", "main")},
            )
            if response.status_code == 201:
                data = response.json()
                return f"✅ Branch created successfully: **{data['name']}**"
            else:
                return f"❌ Failed to create branch: {response.text}"

        elif action == "create_incident":
            response = await client.post(
                f"{integration.url}/incidents",
                headers=headers,
                json=params,
            )
            if response.status_code == 201:
                data = response.json()
                return f"✅ Incident opened successfully: **{data['id']}** - {data['title']} ({data['severity']})"
            else:
                return f"❌ Failed to open incident: {response.text}"

        else:
            return f"❌ Unknown action type: {action}"


def _build_project_context(project: Optional[Project], user_id: int, db: Session) -> str:
    """Summarize the active project and all available user projects for the orchestrator prompt."""
    lines = []
    if project:
        lines.append(f"Active Project: {project.name}")
        lines.append(f"- Jira key: {project.jira_project_key or 'not set'}")
        lines.append(f"- Confluence space: {project.confluence_space_key or 'not set'}")
        lines.append(f"- GitHub repo: {project.github_repo_name or 'not set'}")
        lines.append(f"- ServiceNow service: {project.servicenow_service_name or 'not set'}")
    else:
        lines.append("No single active project selected.")

    all_projects = db.query(Project).filter(Project.user_id == user_id).all()
    if all_projects:
        lines.append("\nAvailable User Projects:")
        for p in all_projects:
            flags = []
            if project and p.id == project.id:
                flags.append("ACTIVE")
            if p.is_selected:
                flags.append("SELECTED")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(
                f"- '{p.name}'{flag_str}: Jira Key={p.jira_project_key or 'None'}, "
                f"Confluence Space={p.confluence_space_key or 'None'}, "
                f"GitHub Repo={p.github_repo_name or 'None'}, "
                f"ServiceNow Service={p.servicenow_service_name or 'None'}"
            )
    return "\n".join(lines)


async def chat(
    message: str,
    user: User,
    session_id: str,
    db: Session,
    project: Optional[Project] = None,
) -> dict:
    """Process a chat message through the agent and return the response.

    Returns a dict with:
    - response: The agent's text response
    - proposal: Optional proposal dict if a write action was suggested
    - systems_queried: List of systems that were queried
    """
    # Get or create session
    session = get_or_create_session(session_id, user.id)

    # Get user integrations
    integrations = _get_user_integrations(user.id, db)

    # Build tools based on integrations
    tools = _build_tools(integrations)

    # Build system prompt
    role_prompt = ROLE_PROMPTS.get(user.role.value, ROLE_PROMPTS["developer"])
    integrations_context = _build_integrations_context(integrations)
    project_context = _build_project_context(project, user.id, db)
    system_prompt = role_prompt.format(
        integrations_context=integrations_context,
        user_name=user.name,
        user_role=user.role.value.replace("_", " ").title(),
    )
    system_prompt += f"\n\nProject context:\n{project_context}\n"

    # Initialize the orchestrator LLM. This is ALWAYS OpenAI: it needs native
    # function calling to decide which tools to invoke from the user's intent.
    llm = ChatOpenAI(
        model=settings.orchestrator_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=0.1,
    )
    # Bind tools if available
    if tools:
        llm_with_tools = llm.bind_tools(tools)
    else:
        llm_with_tools = llm

    # Build message history
    messages = [SystemMessage(content=system_prompt)]

    # Add conversation history (last 20 messages for context)
    for msg in session.messages[-20:]:
        if msg.role == "user":
            messages.append(HumanMessage(content=msg.content))
        elif msg.role == "assistant":
            messages.append(AIMessage(content=msg.content))

    # Add current message
    messages.append(HumanMessage(content=message))

    # Track queried systems
    systems_queried = set()

    # Agent loop: call LLM, execute tools, repeat until done
    max_iterations = 10
    response = None
    for _ in range(max_iterations):
        response = await llm_with_tools.ainvoke(messages)

        tool_calls_to_run = []
        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls_to_run = response.tool_calls
        elif hasattr(response, "content") and response.content:
            text_calls = parse_text_tool_calls(str(response.content))
            if text_calls:
                tool_calls_to_run = text_calls

        # Check if the model wants to call tools
        if tool_calls_to_run:
            messages.append(response)

            for tool_call in tool_calls_to_run:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args") or {}
                call_id = tool_call.get("id") or f"call_{uuid.uuid4().hex[:8]}"

                # Track which systems are queried
                if "jira" in tool_name:
                    systems_queried.add("jira")
                elif "confluence" in tool_name:
                    systems_queried.add("confluence")
                elif "github" in tool_name:
                    systems_queried.add("github")
                elif "servicenow" in tool_name:
                    systems_queried.add("servicenow")

                # Find and execute the tool
                tool_fn = next((t for t in tools if t.name == tool_name), None)
                if tool_fn:
                    try:
                        tool_result = tool_fn.invoke(tool_args)
                    except Exception as e:
                        logger.error(f"Tool {tool_name} failed: {e}")
                        tool_result = f"Error executing {tool_name}: {str(e)}"
                else:
                    tool_result = f"Tool {tool_name} not found"

                # Add tool result as a tool message
                messages.append(ToolMessage(content=str(tool_result), tool_call_id=call_id))
        else:
            # No more tool calls, we have our final response
            break

    # Check if any tool call returned a proposal
    proposal = None
    for msg in messages:
        if hasattr(msg, "content") and "__PROPOSAL__" in str(msg.content):
            p, _ = _extract_proposal(str(msg.content))
            if p:
                proposal = p
                break

    raw_response = response.content if (response and hasattr(response, "content")) else str(response or "")
    final_response = clean_tool_markup(raw_response)

    # Synthesis pass: re-phrase the orchestrator's answer using the configured
    # synthesis provider (1min.ai by default, or OpenAI). Skip it when there is
    # a pending write proposal (structured text that must not be reworded) or
    # when no systems were queried (nothing to summarize).
    if final_response and not proposal and systems_queried:
        from app.agent.synthesis import synthesize_response

        final_response = synthesize_response(
            user_message=message,
            orchestrator_answer=final_response,
            role=user.role.value,
            system_prompt=system_prompt,
        )
        final_response = clean_tool_markup(final_response)

    # Store in session
    session.messages.append(ChatMessage(role="user", content=message))
    session.messages.append(ChatMessage(role="assistant", content=final_response))

    if proposal:
        session.pending_action = proposal

    return {
        "response": final_response,
        "proposal": proposal,
        "systems_queried": list(systems_queried),
        "session_id": session_id,
    }


# --- Starter-prompt suggestions -------------------------------------------

# Deterministic, connection-aware fallback suggestions per role. Used when no
# OpenAI key is configured, or when LLM generation fails/returns nothing. Each
# entry is (text, required_integration_type_or_None).
_FALLBACK_SUGGESTIONS: dict[str, list[tuple[str, Optional[str]]]] = {
    "product_manager": [
        ("What is the current sprint status?", "jira"),
        ("Summarize open blockers", "jira"),
        ("Summarize the latest documentation updates", "confluence"),
        ("Are there any active production incidents?", "servicenow"),
        ("Give me a delivery status overview", None),
    ],
    "developer": [
        ("Show my open pull requests", "github"),
        ("What issues are assigned to me?", "jira"),
        ("Any recent failed deployments?", "servicenow"),
        ("Find the technical docs for my project", "confluence"),
        ("What changed in the latest release?", "github"),
    ],
    "executive": [
        ("Give me a high-level delivery status", None),
        ("What are the top risks and blockers right now?", "jira"),
        ("Any active production incidents?", "servicenow"),
        ("How is the team performing this quarter?", "jira"),
    ],
}


def _fallback_suggestions(
    role: str, integrations: list[Integration], limit: int = 4
) -> list[str]:
    """Build role/connection-aware suggestions without calling the LLM."""
    connected = {i.type.value for i in integrations}
    entries = _FALLBACK_SUGGESTIONS.get(role, _FALLBACK_SUGGESTIONS["developer"])
    out: list[str] = []
    for text, required in entries:
        if len(out) >= limit:
            break
        if required is not None and required not in connected:
            continue
        out.append(text)
    if not out:
        out = ["What can you help me with?", "Give me a status overview of my projects"]
    return out[:limit]


def _parse_suggestion_lines(raw: str, limit: int) -> list[str]:
    """Parse the LLM output into a clean list of short suggestion strings."""
    suggestions: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        # Strip common list markers: "1.", "-", "*", "•", quotes.
        cleaned = cleaned.lstrip("-*•0123456789. )\t").strip()
        cleaned = cleaned.strip('"').strip("'").strip()
        if not cleaned:
            continue
        suggestions.append(cleaned)
        if len(suggestions) >= limit:
            break
    return suggestions


async def generate_suggestions(
    user: User,
    db: Session,
    project: Optional[Project] = None,
    limit: int = 4,
) -> list[str]:
    """Generate short, context-aware chat starter prompts for the user.

    Reuses the same role prompt, integrations context, and project context the
    chat agent uses so the suggestions reflect the user's actual connected
    systems and scoped project. Falls back to a deterministic list when no
    OpenAI key is configured or generation fails.
    """
    integrations = _get_user_integrations(user.id, db)

    # No key configured -> deterministic fallback (mirrors the demo agent path).
    if not settings.openai_api_key:
        return _fallback_suggestions(user.role.value, integrations, limit)

    role_prompt = ROLE_PROMPTS.get(user.role.value, ROLE_PROMPTS["developer"])
    integrations_context = _build_integrations_context(integrations)
    project_context = _build_project_context(project, user.id, db)
    system_prompt = role_prompt.format(
        integrations_context=integrations_context,
        user_name=user.name,
        user_role=user.role.value.replace("_", " ").title(),
    )
    system_prompt += f"\n\nProject context:\n{project_context}\n"

    instruction = (
        f"Generate exactly {limit} short starter questions this user could ask you right now. "
        "Rules:\n"
        "- Each on its own line, no numbering, no bullets, no quotes.\n"
        "- Keep each under 12 words, phrased as a question or request.\n"
        "- Only reference systems that are actually connected (see the integrations above).\n"
        "- Prefer the user's scoped/active project and use its real name or keys when relevant.\n"
        "- Do NOT call any tools or include tool-call tags; just output the plain lines."
    )

    try:
        llm = ChatOpenAI(
            model=settings.orchestrator_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            temperature=0.4,
        )
        response = await llm.ainvoke(
            [SystemMessage(content=system_prompt), HumanMessage(content=instruction)]
        )
        raw = response.content if hasattr(response, "content") else str(response)
        raw = clean_tool_markup(raw if isinstance(raw, str) else str(raw))
        suggestions = _parse_suggestion_lines(raw, limit)
        if suggestions:
            return suggestions
    except Exception:
        logger.exception("Failed to generate LLM suggestions; using fallback")

    return _fallback_suggestions(user.role.value, integrations, limit)
