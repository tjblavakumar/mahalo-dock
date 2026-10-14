"""Demo agent that works without OpenAI API key by using simple keyword-based tool selection.
Falls back to this when OPENAI_API_KEY is not configured."""

import json
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.agent.session import ChatMessage, get_or_create_session
from app.agent.tools.confluence_tools import create_confluence_tools
from app.agent.tools.github_tools import create_github_tools
from app.agent.tools.jira_tools import create_jira_tools
from app.agent.tools.servicenow_tools import create_servicenow_tools
from app.models.integration import Integration
from app.models.project import Project
from app.models.user import User

logger = logging.getLogger(__name__)


def _get_user_integrations(user_id: int, db: Session) -> list[Integration]:
    """Get all integrations for a user."""
    return db.query(Integration).filter(Integration.user_id == user_id).all()


def _build_tools_map(integrations: list[Integration]) -> dict:
    """Build tools organized by type."""
    tools_map = {"jira": [], "confluence": [], "github": [], "servicenow": []}
    for integration in integrations:
        if integration.type.value == "jira":
            tools_map["jira"] = create_jira_tools(integration.url, integration.token)
        elif integration.type.value == "confluence":
            tools_map["confluence"] = create_confluence_tools(integration.url, integration.token)
        elif integration.type.value == "github":
            tools_map["github"] = create_github_tools(integration.url, integration.token)
        elif integration.type.value == "servicenow":
            tools_map["servicenow"] = create_servicenow_tools(integration.url, integration.token)
    return tools_map


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


def build_project_context(project: Optional[Project]) -> dict:
    """Build a project context dict from the selected project or return an empty context."""
    if project is None:
        return {}

    return {
        "project_id": project.id,
        "project_name": project.name,
        "jira_project_key": project.jira_project_key,
        "confluence_space_key": project.confluence_space_key,
        "github_repo_name": project.github_repo_name,
        "servicenow_service_name": project.servicenow_service_name,
    }


async def demo_chat(
    message: str,
    user: User,
    session_id: str,
    db: Session,
    project: Optional[Project] = None,
) -> dict:
    """Process a chat message using keyword-based tool selection (no LLM needed).

    This provides a working demo without requiring an OpenAI API key.
    """
    session = get_or_create_session(session_id, user.id)
    integrations = _get_user_integrations(user.id, db)
    tools_map = _build_tools_map(integrations)
    project_context = build_project_context(project)

    msg_lower = message.lower()
    systems_queried = []
    tool_results = []
    proposal = None

    # Determine which tools to call based on keywords
    if not integrations:
        response = ("I don't have any integrations configured yet. "
                    "Please go to the Connections page and add your Jira, Confluence, and/or GitHub connections.")
        session.messages.append(ChatMessage(role="user", content=message))
        session.messages.append(ChatMessage(role="assistant", content=response))
        return {"response": response, "proposal": None, "systems_queried": [], "session_id": session_id}

    # --- Routing logic based on keywords ---

    # Create story -> propose action (check before generic "story" keyword)
    if any(kw in msg_lower for kw in ["create story", "create a story", "new story", "add story", "create a new story"]):
        if tools_map["jira"]:
            systems_queried.append("jira")
            create_tool = next((t for t in tools_map["jira"] if t.name == "jira_create_story"), None)
            if create_tool:
                project_id = _detect_project(msg_lower, project_context) or project_context.get("jira_project_key") or "PAY"
                title = _extract_story_title(message)
                result = create_tool.invoke({
                    "project_id": project_id,
                    "title": title,
                    "description": message,
                    "priority": "medium",
                    "story_points": 5,
                })
                tool_results.append(result)

    # Create branch -> propose action
    elif any(kw in msg_lower for kw in ["create branch", "new branch", "create a branch"]):
        if tools_map["github"]:
            systems_queried.append("github")
            create_tool = next((t for t in tools_map["github"] if t.name == "github_create_branch"), None)
            if create_tool:
                repo_id = _detect_repo(msg_lower, project_context) or project_context.get("github_repo_name") or "repo-1"
                branch_name = _extract_branch_name(message)
                result = create_tool.invoke({
                    "repo_id": repo_id,
                    "branch_name": branch_name,
                })
                tool_results.append(result)

    # Status/overview questions -> query Jira board + GitHub PRs
    elif (
        any(kw in msg_lower for kw in ["status", "overview", "progress", "how is", "what's happening"])
        and not any(kw in msg_lower for kw in ["deploy", "deployment", "servicenow"])
    ):
        # Determine project
        project_id = _detect_project(msg_lower, project_context)

        if tools_map["jira"]:
            systems_queried.append("jira")
            if project_id:
                board_tool = next((t for t in tools_map["jira"] if t.name == "jira_get_board"), None)
                if board_tool:
                    tool_results.append(board_tool.invoke({"project_id": project_id}))
                sprint_tool = next((t for t in tools_map["jira"] if t.name == "jira_get_sprint_info"), None)
                if sprint_tool:
                    tool_results.append(sprint_tool.invoke({"project_id": project_id}))
            else:
                # List all projects
                list_tool = next((t for t in tools_map["jira"] if t.name == "jira_list_projects"), None)
                if list_tool:
                    tool_results.append(list_tool.invoke({}))

        if tools_map["github"] and project_id:
            systems_queried.append("github")
            repo_id = _project_to_repo(project_id, project_context)
            if repo_id:
                pr_tool = next((t for t in tools_map["github"] if t.name == "github_get_pull_requests"), None)
                if pr_tool:
                    tool_results.append(pr_tool.invoke({"repo_id": repo_id}))

    # Sprint/velocity questions -> Jira sprints
    elif any(kw in msg_lower for kw in ["sprint", "velocity", "plan", "next sprint"]):
        project_id = _detect_project(msg_lower, project_context)
        if tools_map["jira"]:
            systems_queried.append("jira")
            if project_id:
                sprint_tool = next((t for t in tools_map["jira"] if t.name == "jira_get_sprint_info"), None)
                if sprint_tool:
                    tool_results.append(sprint_tool.invoke({"project_id": project_id}))
                board_tool = next((t for t in tools_map["jira"] if t.name == "jira_get_board"), None)
                if board_tool:
                    tool_results.append(board_tool.invoke({"project_id": project_id}))

    # Story-specific questions
    elif any(kw in msg_lower for kw in ["story", "stories", "assigned", "my work", "backlog"]):
        if tools_map["jira"]:
            systems_queried.append("jira")
            project_id = _detect_project(msg_lower, project_context)
            status = _detect_status(msg_lower)

            # If the user is asking about a specific person's work, resolve the
            # person to a developer and use the assignee-based tool. This mirrors
            # the real-life flow: resolve a name to an account, then filter.
            assignee_ref = _detect_person(message, tools_map["jira"], current_user=user)

            if assignee_ref:
                by_assignee_tool = next(
                    (t for t in tools_map["jira"] if t.name == "jira_get_stories_by_assignee"), None
                )
                if by_assignee_tool:
                    kwargs = {"assignee": assignee_ref}
                    if status:
                        kwargs["status"] = status
                    if project_id:
                        kwargs["project_id"] = project_id
                    tool_results.append(by_assignee_tool.invoke(kwargs))
            else:
                search_tool = next((t for t in tools_map["jira"] if t.name == "jira_search_stories"), None)
                if search_tool:
                    # Only pass a keyword if there is a meaningful topic term.
                    query = _extract_story_keyword(message)
                    kwargs = {}
                    if query:
                        kwargs["query"] = query
                    if project_id:
                        kwargs["project_id"] = project_id
                    if status:
                        kwargs["status"] = status
                    tool_results.append(search_tool.invoke(kwargs))

    # Deployment/incident/production questions -> ServiceNow
    elif any(kw in msg_lower for kw in ["deploy", "deployment", "incident", "outage", "production issue", "rollback", "rolled back", "sev", "p1", "p2"]):
        if tools_map["servicenow"]:
            systems_queried.append("servicenow")
            service = None
            proj = _detect_project(msg_lower, project_context)
            service_map = {"PAY": "payment-service", "CART": "cart-service", "AUTH": "auth-service", "PROD": "product-service", "ORD": "order-service"}
            if proj:
                service = service_map.get(proj)
            if any(kw in msg_lower for kw in ["incident", "outage", "production issue", "sev", "p1", "p2"]):
                inc_tool = next((t for t in tools_map["servicenow"] if t.name == "servicenow_list_incidents"), None)
                if inc_tool:
                    kwargs = {}
                    if service:
                        kwargs["service"] = service
                    tool_results.append(inc_tool.invoke(kwargs))
            else:
                grouped_request = any(
                    phrase in msg_lower
                    for phrase in ["per project", "by project", "each project", "all projects"]
                )
                preferred_tool = (
                    "servicenow_deployment_status_by_project"
                    if grouped_request
                    else "servicenow_list_deployments"
                )
                dep_tool = next((t for t in tools_map["servicenow"] if t.name == preferred_tool), None)
                if dep_tool:
                    kwargs = {} if grouped_request else ({"service": service} if service else {})
                    tool_results.append(dep_tool.invoke(kwargs))

    # Documentation/security/architecture questions -> Confluence
    elif any(kw in msg_lower for kw in ["doc", "documentation", "security", "architecture", "pci", "compliance", "api spec", "design"]):
        if tools_map["confluence"]:
            systems_queried.append("confluence")
            search_tool = next((t for t in tools_map["confluence"] if t.name == "confluence_search"), None)
            if search_tool:
                # For confluence, use more targeted query extraction
                query = _extract_confluence_query(msg_lower)
                tool_results.append(search_tool.invoke({"query": query}))

    # PR/code/commits questions -> GitHub
    elif any(kw in msg_lower for kw in ["pr", "pull request", "commit", "branch", "code", "repo"]):
        if tools_map["github"]:
            systems_queried.append("github")
            repo_id = _detect_repo(msg_lower, project_context)
            if repo_id:
                pr_tool = next((t for t in tools_map["github"] if t.name == "github_get_pull_requests"), None)
                if pr_tool:
                    tool_results.append(pr_tool.invoke({"repo_id": repo_id}))
                commits_tool = next((t for t in tools_map["github"] if t.name == "github_get_commits"), None)
                if commits_tool:
                    tool_results.append(commits_tool.invoke({"repo_id": repo_id}))
            else:
                repos_tool = next((t for t in tools_map["github"] if t.name == "github_list_repos"), None)
                if repos_tool:
                    tool_results.append(repos_tool.invoke({}))

    # Default: try to search across all systems
    else:
        query = _extract_search_query(message)
        if tools_map["jira"]:
            systems_queried.append("jira")
            search_tool = next((t for t in tools_map["jira"] if t.name == "jira_search_stories"), None)
            if search_tool:
                tool_results.append(search_tool.invoke({"query": query}))
        if tools_map["confluence"]:
            systems_queried.append("confluence")
            search_tool = next((t for t in tools_map["confluence"] if t.name == "confluence_search"), None)
            if search_tool:
                tool_results.append(search_tool.invoke({"query": query}))

    # Build response from tool results
    response_parts = []
    for result in tool_results:
        p, clean = _extract_proposal(str(result))
        if p:
            proposal = p
            if clean.strip():
                response_parts.append(clean)
        else:
            response_parts.append(str(result))

    if proposal:
        response_parts.append(
            f"\n\n🔔 **Proposed Action**: {proposal['description']}\n"
            f"- System: {proposal['system']}\n"
            f"- Parameters: {json.dumps(proposal['params'], indent=2)}\n\n"
            f"Would you like me to proceed? (Approve or Reject)"
        )

    if response_parts:
        response = "\n\n---\n\n".join(response_parts)
    else:
        response = ("I searched the connected systems but couldn't find specific information for your query. "
                    "Try asking about a specific project (Payment Gateway, Shopping Cart, User Auth, Product Catalog, Order Management), "
                    "or ask about sprints, stories, documentation, PRs, or commits.")

    # Apply persona-specific formatting
    response = _format_for_persona(response, user.role.value, msg_lower)

    # Add systems queried info
    if systems_queried:
        response += f"\n\n_Systems queried: {', '.join(systems_queried)}_"

    # Store in session
    session.messages.append(ChatMessage(role="user", content=message))
    session.messages.append(ChatMessage(role="assistant", content=response))
    if proposal:
        session.pending_action = proposal

    return {
        "response": response,
        "proposal": proposal,
        "systems_queried": systems_queried,
        "session_id": session_id,
    }


# --- Helper functions for keyword extraction ---

def _detect_project(msg: str, project_context: Optional[dict] = None) -> Optional[str]:
    """Detect which project the user is asking about, defaulting to the active project when available."""
    project_keywords = {
        "PAY": ["payment", "pay", "stripe", "apple pay", "google pay"],
        "CART": ["cart", "shopping", "checkout", "coupon"],
        "AUTH": ["auth", "login", "authentication", "sso", "2fa"],
        "PROD": ["product", "catalog", "search", "inventory", "recommendation"],
        "ORD": ["order", "fulfillment", "tracking", "shipping", "return"],
    }
    for proj_id, keywords in project_keywords.items():
        if any(kw in msg for kw in keywords):
            return proj_id
    if project_context and project_context.get("jira_project_key"):
        return project_context["jira_project_key"]
    return None


def _project_to_repo(project_id: str, project_context: Optional[dict] = None) -> Optional[str]:
    """Map project ID to GitHub repo ID, preferring the active project when available."""
    if project_context and project_context.get("github_repo_name"):
        return project_context["github_repo_name"]
    mapping = {"PAY": "repo-1", "CART": "repo-2", "AUTH": "repo-3", "PROD": "repo-4", "ORD": "repo-5"}
    return mapping.get(project_id)


# Cache the developer directory per process to avoid repeated lookups.
_DEVELOPERS_CACHE: Optional[list[dict]] = None


def _get_developers(jira_tools: list) -> list[dict]:
    """Fetch the developer directory via the jira_list_developers tool output.

    Parses the tool's formatted text back into structured records so the demo
    router can resolve names without needing a separate HTTP client.
    """
    global _DEVELOPERS_CACHE
    if _DEVELOPERS_CACHE is not None:
        return _DEVELOPERS_CACHE

    list_tool = next((t for t in jira_tools if t.name == "jira_list_developers"), None)
    developers: list[dict] = []
    if list_tool:
        try:
            raw = str(list_tool.invoke({}))
        except Exception as e:
            logger.warning(f"Failed to list developers: {e}")
            raw = ""
        # Lines look like: "- dev-3: Raj Patel (raj@ecommerce.io)"
        for line in raw.splitlines():
            line = line.strip().lstrip("-").strip()
            if not line.startswith("dev-") or ":" not in line:
                continue
            dev_id, rest = line.split(":", 1)
            rest = rest.strip()
            name = rest
            email = ""
            if "(" in rest and rest.endswith(")"):
                name = rest[: rest.index("(")].strip()
                email = rest[rest.index("(") + 1 : -1].strip()
            developers.append({"id": dev_id.strip(), "name": name, "email": email})

    _DEVELOPERS_CACHE = developers
    return developers


def _detect_person(message: str, jira_tools: list, current_user=None) -> Optional[str]:
    """Detect whether the message references a specific person and return a
    resolvable assignee reference (developer name or 'me' -> current user).

    Returns the matched name/first-name so the assignee tool can resolve it,
    or None if the query is not person-scoped.
    """
    msg_lower = message.lower()

    # Handle first-person phrasing ("my stories", "assigned to me")
    if current_user is not None and any(
        kw in msg_lower for kw in ["assigned to me", "my stories", "my work", "my tasks", "my assignments"]
    ):
        # Match the current user's name against the directory.
        return getattr(current_user, "name", None)

    developers = _get_developers(jira_tools)
    if not developers:
        return None

    for dev in developers:
        name = dev["name"]
        first = name.split()[0]
        # Match full name or a standalone first name token in the message.
        if name.lower() in msg_lower:
            return name
        tokens = [t.strip("?.,!'\"") for t in msg_lower.split()]
        if first.lower() in tokens:
            return name
    return None


def _detect_status(msg: str) -> Optional[str]:
    """Detect a story status filter from the message."""
    if "in review" in msg or "in-review" in msg or "in_review" in msg:
        return "in_review"
    if "in progress" in msg or "in-progress" in msg or "in_progress" in msg:
        return "in_progress"
    if "done" in msg or "completed" in msg or "finished" in msg:
        return "done"
    if "todo" in msg or "to do" in msg or "backlog" in msg or "not started" in msg:
        return "todo"
    return None


# Words that indicate intent/role rather than a searchable story topic.
_STORY_NON_TOPIC_WORDS = {
    "story", "stories", "assigned", "assign", "assignee", "work", "working",
    "backlog", "task", "tasks", "jira", "ticket", "tickets", "show", "list",
    "get", "find", "give", "tell", "what", "which", "the", "for", "all",
    "todo", "done", "progress", "review", "status",
}


def _extract_story_keyword(message: str) -> Optional[str]:
    """Extract a meaningful topic keyword for story search, or None.

    Unlike the generic query extractor, this drops story/role/status words so
    we don't accidentally pass a whole sentence as a literal keyword filter.
    """
    words = [w.strip("?.,!'\"").lower() for w in message.split()]
    topic = [w for w in words if len(w) > 2 and w not in _STORY_NON_TOPIC_WORDS]
    if not topic:
        return None
    return " ".join(topic[:4])


def _detect_repo(msg: str, project_context: Optional[dict] = None) -> Optional[str]:
    """Detect which repo the user is asking about, defaulting to the active project repo when available."""
    repo_keywords = {
        "repo-1": ["payment-service", "payment service", "payment repo"],
        "repo-2": ["cart-service", "cart service", "cart repo"],
        "repo-3": ["auth-service", "auth service", "auth repo"],
        "repo-4": ["product-service", "product service", "product repo"],
        "repo-5": ["order-service", "order service", "order repo"],
    }
    for repo_id, keywords in repo_keywords.items():
        if any(kw in msg for kw in keywords):
            return repo_id
    project_id = _detect_project(msg, project_context)
    if project_id:
        return _project_to_repo(project_id, project_context)
    if project_context and project_context.get("github_repo_name"):
        return project_context["github_repo_name"]
    return None


def _extract_search_query(message: str) -> str:
    """Extract the main search terms from a message."""
    # Remove common question words
    stop_words = {"what", "is", "the", "of", "a", "an", "for", "in", "on", "to", "can", "you",
                  "me", "tell", "show", "get", "find", "search", "about", "how", "are", "my",
                  "give", "do", "does", "i", "we", "this", "that", "please", "help"}
    words = message.lower().split()
    query_words = [w for w in words if w.strip("?.,!") not in stop_words and len(w) > 2]
    return " ".join(query_words[:5]) if query_words else message[:30]


def _extract_confluence_query(msg_lower: str) -> str:
    """Extract a better search query for Confluence based on detected topic."""
    # Map detected keywords to good search terms
    if "pci" in msg_lower:
        return "PCI"
    elif "compliance" in msg_lower:
        return "compliance"
    elif "security" in msg_lower:
        return "security"
    elif "architecture" in msg_lower:
        return "architecture"
    elif "api spec" in msg_lower:
        return "API"
    elif "design" in msg_lower:
        return "design"
    # Fallback to generic extraction
    return _extract_search_query(msg_lower)


def _extract_story_title(message: str) -> str:
    """Extract a story title from a create request."""
    # Try to find text after "story" or "for"
    lower = message.lower()
    for keyword in ["story for ", "story: ", "story about ", "called "]:
        if keyword in lower:
            idx = lower.index(keyword) + len(keyword)
            return message[idx:].strip()[:100]
    return message[:100]


def _extract_branch_name(message: str) -> str:
    """Extract a branch name from a create request."""
    lower = message.lower()
    for keyword in ["branch ", "called ", "named "]:
        if keyword in lower:
            idx = lower.index(keyword) + len(keyword)
            name = message[idx:].strip().split()[0]
            return name
    return "feature/new-feature"


def _format_for_persona(response: str, role: str, msg_lower: str) -> str:
    """Add persona-specific framing to the response."""
    if not response or "couldn't find" in response:
        return response

    # Add role-specific header/summary
    if role == "product_manager":
        # PM gets strategic framing with delivery focus
        if "sprint" in msg_lower or "status" in msg_lower or "overview" in msg_lower:
            header = "## 📊 Sprint Status Report\n\nHere's the current status based on data from your connected systems:\n\n"
            footer = "\n\n💡 **Recommendation**: Focus on unblocking in-progress items to maintain velocity. Consider whether any todo items should be deprioritized if the sprint is at risk."
            return header + response + footer
        elif "velocity" in msg_lower or "plan" in msg_lower:
            header = "## 📈 Velocity & Planning Data\n\n"
            footer = "\n\n💡 **Planning Insight**: Use the average velocity to scope your next sprint. Avoid committing to more than 110% of average velocity."
            return header + response + footer

    elif role == "executive":
        # Executive gets concise, high-level framing
        if "status" in msg_lower or "overview" in msg_lower:
            header = "## 🏢 Executive Summary\n\nHere's a high-level view of project health:\n\n"
            footer = "\n\n📌 **Key Takeaway**: Monitor projects with critical-priority items closely. Items in review should be unblocked within 24 hours to maintain flow."
            return header + response + footer
        elif "risk" in msg_lower or "blocker" in msg_lower:
            header = "## ⚠️ Risk Assessment\n\n"
            footer = "\n\n📌 **Action Required**: Critical items require immediate attention from engineering leads."
            return header + response + footer

    elif role == "developer":
        # Developer gets technical, action-oriented framing
        if "assigned" in msg_lower or "my" in msg_lower or "work" in msg_lower:
            header = "## 🛠️ Your Active Work\n\nHere are your current assignments:\n\n"
            footer = "\n\n💻 **Next Step**: Pick the highest-priority item that's in 'todo' and move it to in-progress. Check linked PRs for review requests."
            return header + response + footer
        elif "pr" in msg_lower or "pull" in msg_lower or "commit" in msg_lower:
            header = "## 🔀 Code Activity\n\n"
            footer = "\n\n💻 **Tip**: PRs with 'changes_requested' reviews need attention first. Keep PRs small (<400 lines) for faster reviews."
            return header + response + footer

    return response
