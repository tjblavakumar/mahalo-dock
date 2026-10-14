"""LangChain tools for Mock Jira service."""

import json
from typing import Optional

import httpx
from langchain_core.tools import tool


def _make_jira_request(url: str, token: str, method: str = "GET", endpoint: str = "", params: dict = None, body: dict = None) -> dict:
    """Make a request to the Jira mock service."""
    headers = {"X-API-Token": token}
    full_url = f"{url}{endpoint}"

    with httpx.Client(timeout=10.0) as client:
        if method == "GET":
            response = client.get(full_url, headers=headers, params=params)
        elif method == "POST":
            response = client.post(full_url, headers=headers, json=body)
        elif method == "PUT":
            response = client.put(full_url, headers=headers, json=body)
        else:
            return {"error": f"Unsupported method: {method}"}

    if response.status_code == 200 or response.status_code == 201:
        return response.json()
    else:
        return {"error": f"Request failed with status {response.status_code}: {response.text}"}


def create_jira_tools(jira_url: str, jira_token: str):
    """Create LangChain tools configured for a specific Jira instance."""

    def _fetch_developers() -> list[dict]:
        """Fetch the developer directory from Jira."""
        data = _make_jira_request(jira_url, jira_token, endpoint="/developers")
        return data.get("developers", []) if isinstance(data, dict) else []

    def _resolve_assignee(assignee: str) -> Optional[str]:
        """Resolve an assignee reference to a developer ID.

        Accepts a developer ID (dev-1..dev-5) as-is, or resolves a person's
        name (full name, first name, or email local-part) to their dev-ID.
        Returns None if no confident match is found.
        """
        if not assignee:
            return None
        val = assignee.strip().lower()
        # Already a developer ID
        if val.startswith("dev-"):
            return val
        developers = _fetch_developers()
        # Exact full-name or email match first
        for d in developers:
            if val == d["name"].lower() or val == d.get("email", "").lower():
                return d["id"]
        # First-name / partial match (e.g. "raj" -> "Raj Patel")
        matches = [
            d for d in developers
            if val in d["name"].lower()
            or val == d.get("email", "").split("@")[0].lower()
            or d["name"].lower().split()[0] == val
        ]
        if len(matches) == 1:
            return matches[0]["id"]
        return None

    def _format_stories(results: list[dict], label: str, developers: Optional[list[dict]] = None) -> str:
        """Format a list of stories with human-readable assignee names."""
        dev_by_id = {d["id"]: d["name"] for d in (developers or [])}
        output = f"Found {len(results)} stories {label}:\n"
        for s in results:
            assignee_id = s.get("assignee")
            assignee_name = dev_by_id.get(assignee_id, assignee_id or "Unassigned")
            output += (
                f"- [{s['id']}] {s['title']} | Status: {s['status']} | "
                f"Points: {s['story_points']} | Assignee: {assignee_name}\n"
            )
        return output

    @tool
    def jira_list_developers() -> str:
        """List all developers (team members) in Jira with their IDs, names, and emails.
        Use this to resolve a person's name (e.g. 'Raj') to their developer ID (e.g. dev-3)
        before filtering stories, PRs, or commits by assignee/author."""
        developers = _fetch_developers()
        if not developers:
            return "No developers found."
        output = "Developers:\n"
        for d in developers:
            output += f"- {d['id']}: {d['name']} ({d.get('email', 'no email')})\n"
        return output

    @tool
    def jira_get_stories_by_assignee(assignee: str, status: Optional[str] = None, project_id: Optional[str] = None) -> str:
        """Get all Jira stories assigned to a specific person across all projects (or one project).
        assignee: a developer ID (dev-1..dev-5) OR a person's name/first name (e.g. 'Raj', 'Raj Patel').
        Names are automatically resolved to developer IDs.
        Optional filters: status (todo/in_progress/in_review/done), project_id."""
        developers = _fetch_developers()
        dev_id = _resolve_assignee(assignee)
        if not dev_id:
            names = ", ".join(f"{d['name']} ({d['id']})" for d in developers)
            return (
                f"Could not resolve '{assignee}' to a known developer. "
                f"Available developers: {names}"
            )

        params = {"assignee": dev_id}
        if status:
            params["status"] = status

        results = []
        if project_id:
            data = _make_jira_request(jira_url, jira_token, endpoint=f"/projects/{project_id}/stories", params=params)
            results = data.get("stories", []) if isinstance(data, dict) else []
        else:
            projects_data = _make_jira_request(jira_url, jira_token, endpoint="/projects")
            for proj in projects_data.get("projects", []) if isinstance(projects_data, dict) else []:
                data = _make_jira_request(jira_url, jira_token, endpoint=f"/projects/{proj['id']}/stories", params=params)
                results.extend(data.get("stories", []) if isinstance(data, dict) else [])

        dev_name = next((d["name"] for d in developers if d["id"] == dev_id), dev_id)
        if not results:
            status_note = f" with status '{status}'" if status else ""
            return f"No stories assigned to {dev_name} ({dev_id}){status_note}."

        return _format_stories(results, f"assigned to {dev_name} ({dev_id})", developers)

    @tool
    def jira_search_stories(query: Optional[str] = None, project_id: Optional[str] = None, status: Optional[str] = None, assignee: Optional[str] = None) -> str:
        """Search for stories in Jira. Can filter by project_id, status (todo/in_progress/in_review/done), and assignee.
        query: optional keyword matched against story title/description. Omit it to list all stories matching the filters.
        assignee: a developer ID (dev-1..dev-5) OR a person's name (e.g. 'Raj') which will be resolved automatically.
        If filtering by a person, prefer the jira_get_stories_by_assignee tool.
        If project_id is not specified, searches across all projects."""
        developers = _fetch_developers()

        # Resolve a name-based assignee to a developer ID for the API filter
        assignee_id = None
        if assignee:
            assignee_id = _resolve_assignee(assignee)
            if not assignee_id:
                names = ", ".join(f"{d['name']} ({d['id']})" for d in developers)
                return f"Could not resolve assignee '{assignee}'. Available developers: {names}"

        keyword = (query or "").strip().lower()

        def _matches_keyword(s: dict) -> bool:
            if not keyword:
                return True
            return keyword in s["title"].lower() or keyword in s.get("description", "").lower()

        def _base_params() -> dict:
            params = {}
            if status:
                params["status"] = status
            if assignee_id:
                params["assignee"] = assignee_id
            return params

        results = []
        if project_id:
            data = _make_jira_request(jira_url, jira_token, endpoint=f"/projects/{project_id}/stories", params=_base_params())
            stories = data.get("stories", []) if isinstance(data, dict) else []
            results = [s for s in stories if _matches_keyword(s)]
        else:
            projects_data = _make_jira_request(jira_url, jira_token, endpoint="/projects")
            for proj in projects_data.get("projects", []) if isinstance(projects_data, dict) else []:
                data = _make_jira_request(jira_url, jira_token, endpoint=f"/projects/{proj['id']}/stories", params=_base_params())
                stories = data.get("stories", []) if isinstance(data, dict) else []
                results.extend(s for s in stories if _matches_keyword(s))

        if not results:
            descriptor = f"matching '{query}'" if query else "matching the given filters"
            return f"No stories found {descriptor}."

        label = f"matching '{query}'" if query else "matching the given filters"
        return _format_stories(results, label, developers)

    @tool
    def jira_get_story(story_id: str) -> str:
        """Get detailed information about a specific Jira story by its ID (e.g., PAY-105)."""
        data = _make_jira_request(jira_url, jira_token, endpoint=f"/stories/{story_id}")
        if "error" in data:
            return f"Error: {data['error']}"

        output = f"**{data['id']}: {data['title']}**\n"
        output += f"- Status: {data['status']}\n"
        output += f"- Priority: {data['priority']}\n"
        output += f"- Story Points: {data['story_points']}\n"
        output += f"- Assignee: {data.get('assignee_details', {}).get('name', data.get('assignee', 'Unassigned'))}\n"
        output += f"- Sprint: {data.get('sprint_id', 'Backlog')}\n"
        output += f"\nDescription: {data['description']}\n"
        if data.get("acceptance_criteria"):
            output += "\nAcceptance Criteria:\n"
            for ac in data["acceptance_criteria"]:
                output += f"  - {ac}\n"
        if data.get("comments"):
            output += "\nComments:\n"
            for c in data["comments"]:
                output += f"  - [{c['date']}] {c['author']}: {c['text']}\n"
        return output

    @tool
    def jira_get_sprint_info(project_id: str) -> str:
        """Get sprint information and velocity data for a project. Use project IDs like PAY, CART, AUTH, PROD, ORD."""
        data = _make_jira_request(jira_url, jira_token, endpoint=f"/sprints/{project_id}")
        if "error" in data:
            return f"Error: {data['error']}"

        output = f"Sprints for project {project_id}:\n"
        for sprint in data.get("sprints", []):
            output += f"\n**{sprint['name']}** ({sprint['status']})\n"
            output += f"  Period: {sprint['start_date']} to {sprint['end_date']}\n"
            if sprint.get("velocity"):
                output += f"  Velocity: {sprint['velocity']} points\n"
            if sprint.get("completed_points") is not None:
                output += f"  Completed: {sprint['completed_points']}/{sprint['total_points']} points\n"
        return output

    @tool
    def jira_get_board(project_id: str) -> str:
        """Get the current sprint board showing stories grouped by status for a project."""
        data = _make_jira_request(jira_url, jira_token, endpoint=f"/projects/{project_id}/board")
        if "error" in data:
            return f"Error: {data['error']}"

        if not data.get("sprint"):
            return f"No active sprint found for project {project_id}"

        sprint = data["sprint"]
        columns = data["columns"]
        output = f"**Sprint Board: {sprint['name']}** ({sprint['start_date']} to {sprint['end_date']})\n\n"

        for col_name, stories in columns.items():
            output += f"📌 {col_name.upper()} ({len(stories)}):\n"
            for s in stories:
                output += f"  - [{s['id']}] {s['title']} ({s['story_points']}pts) - {s.get('assignee', 'Unassigned')}\n"
            output += "\n"
        return output

    @tool
    def jira_create_story(project_id: str, title: str, description: str, priority: str = "medium", story_points: int = 0, assignee: Optional[str] = None) -> str:
        """[WRITE ACTION - REQUIRES APPROVAL] Create a new story in Jira. Returns a proposal for user confirmation.
        project_id: Jira project key (e.g. PAY, CART, AUTH, PROD, ORD, or any custom project key like GOLDSELL or EXP).
        priority: critical, high, medium, or low.
        assignee: developer ID (dev-1 through dev-5) or None."""
        # This is a write action - return proposal instead of executing
        proposal = {
            "action": "create_story",
            "system": "jira",
            "params": {
                "project_id": project_id,
                "title": title,
                "description": description,
                "priority": priority,
                "story_points": story_points,
                "assignee": assignee,
            },
            "description": f"Create a new story in project {project_id}: '{title}'",
        }
        return f"__PROPOSAL__{json.dumps(proposal)}__END_PROPOSAL__"

    @tool
    def jira_update_story(
        story_id: str,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        priority: Optional[str] = None,
        story_points: Optional[int] = None,
        sprint_id: Optional[str] = None,
    ) -> str:
        """[WRITE ACTION - REQUIRES APPROVAL] Update an EXISTING Jira story. Returns a proposal for user confirmation.
        Use this (never jira_create_story) whenever the user references a story that already exists (e.g. PAY-111).
        story_id: the existing story key, e.g. PAY-111.
        Only the fields you pass are changed; omit the rest.
        status: todo | in_progress | in_review | done.
        assignee: developer ID (dev-1..dev-6) OR a person's name (e.g. 'Lava Dev'), resolved automatically.
        priority: critical | high | medium | low."""
        # Verify the story exists so we never silently create/duplicate.
        existing = _make_jira_request(jira_url, jira_token, endpoint=f"/stories/{story_id}")
        if "error" in existing:
            return (
                f"Story '{story_id}' was not found, so it cannot be updated. "
                f"Double-check the story ID (e.g. PAY-111)."
            )

        # Resolve a name-based assignee to a developer ID.
        resolved_assignee = None
        if assignee is not None:
            resolved_assignee = _resolve_assignee(assignee)
            if not resolved_assignee:
                developers = _fetch_developers()
                names = ", ".join(f"{d['name']} ({d['id']})" for d in developers)
                return f"Could not resolve assignee '{assignee}'. Available developers: {names}"

        # Build the set of changes (only provided fields).
        changes = {}
        if status is not None:
            changes["status"] = status
        if resolved_assignee is not None:
            changes["assignee"] = resolved_assignee
        if priority is not None:
            changes["priority"] = priority
        if story_points is not None:
            changes["story_points"] = story_points
        if sprint_id is not None:
            changes["sprint_id"] = sprint_id

        if not changes:
            return f"No changes specified for {story_id}. Provide at least one field to update."

        # Human-readable change summary for the proposal.
        parts = []
        for k, v in changes.items():
            label = v
            if k == "assignee":
                developers = _fetch_developers()
                dev_name = next((d["name"] for d in developers if d["id"] == v), v)
                label = f"{dev_name} ({v})"
            parts.append(f"{k.replace('_', ' ')} -> {label}")
        change_desc = "; ".join(parts)

        proposal = {
            "action": "update_story",
            "system": "jira",
            "params": {
                "story_id": story_id,
                "changes": changes,
            },
            "description": f"Update story {story_id}: {change_desc}",
        }
        return f"__PROPOSAL__{json.dumps(proposal)}__END_PROPOSAL__"

    @tool
    def jira_list_projects() -> str:
        """List all available Jira projects."""
        data = _make_jira_request(jira_url, jira_token, endpoint="/projects")
        if "error" in data:
            return f"Error: {data['error']}"

        output = "Available projects:\n"
        for p in data.get("projects", []):
            output += f"- **{p['id']}**: {p['name']} - {p['description']}\n"
        return output

    return [jira_list_projects, jira_list_developers, jira_search_stories, jira_get_stories_by_assignee, jira_get_story, jira_get_sprint_info, jira_get_board, jira_create_story, jira_update_story]
