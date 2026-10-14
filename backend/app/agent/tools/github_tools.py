"""LangChain tools for Mock GitHub service."""

import json
from typing import Optional

import httpx
from langchain_core.tools import tool


def _make_github_request(url: str, token: str, method: str = "GET", endpoint: str = "", params: dict = None, body: dict = None) -> dict:
    """Make a request to the GitHub mock service."""
    headers = {"X-API-Token": token}
    full_url = f"{url}{endpoint}"

    with httpx.Client(timeout=10.0) as client:
        if method == "GET":
            response = client.get(full_url, headers=headers, params=params)
        elif method == "POST":
            response = client.post(full_url, headers=headers, json=body)
        else:
            return {"error": f"Unsupported method: {method}"}

    if response.status_code in (200, 201):
        return response.json()
    else:
        return {"error": f"Request failed with status {response.status_code}: {response.text}"}


def create_github_tools(github_url: str, github_token: str):
    """Create LangChain tools configured for a specific GitHub instance."""

    @tool
    def github_list_repos() -> str:
        """List all available GitHub repositories."""
        data = _make_github_request(github_url, github_token, endpoint="/repos")
        if "error" in data:
            return f"Error: {data['error']}"

        output = "Available repositories:\n"
        for r in data.get("repos", []):
            output += f"- **{r['name']}** ({r['language']}) - {r['description']}\n"
            output += f"  Last push: {r['last_push']} | Open issues: {r['open_issues']}\n"
        return output

    @tool
    def github_get_pull_requests(repo_id: str, status: Optional[str] = None, author_id: Optional[str] = None) -> str:
        """Get pull requests for a repository. repo_id: repo-1 (payment-service), repo-2 (cart-service), repo-3 (auth-service), repo-4 (product-service), repo-5 (order-service).
        Optional filters: status (open/draft/merged/closed), author_id (dev-1 through dev-5)."""
        params = {}
        if status:
            params["status"] = status
        if author_id:
            params["author_id"] = author_id
        data = _make_github_request(github_url, github_token, endpoint=f"/repos/{repo_id}/pulls", params=params)
        if "error" in data:
            return f"Error: {data['error']}"

        prs = data.get("pull_requests", [])
        if not prs:
            return f"No pull requests found for {repo_id}"

        output = f"Pull requests for {repo_id} ({len(prs)} found):\n"
        for pr in prs:
            output += f"\n🔀 **PR #{pr['number']}**: {pr['title']}\n"
            output += f"   Author: {pr['author']} | Status: {pr['status']} | Branch: {pr['branch']}\n"
            output += f"   +{pr['additions']}/-{pr['deletions']} ({pr['files_changed']} files)\n"
            if pr.get("linked_story"):
                output += f"   Linked story: {pr['linked_story']}\n"
            if pr.get("reviews"):
                for review in pr["reviews"]:
                    output += f"   Review: {review['reviewer']} - {review['status']}\n"
        return output

    @tool
    def github_get_commits(repo_id: str, branch: Optional[str] = None, author: Optional[str] = None) -> str:
        """Get recent commits for a repository. Can filter by branch name or author (name or dev-ID).
        repo_id: repo-1 (payment-service), repo-2 (cart-service), repo-3 (auth-service), repo-4 (product-service), repo-5 (order-service)."""
        params = {}
        if branch:
            params["branch"] = branch
        if author:
            params["author"] = author
        data = _make_github_request(github_url, github_token, endpoint=f"/repos/{repo_id}/commits", params=params)
        if "error" in data:
            return f"Error: {data['error']}"

        commits = data.get("commits", [])
        if not commits:
            return "No commits found"

        output = f"Recent commits ({len(commits)}):\n"
        for c in commits:
            output += f"- [{c['date']}] {c['message']} (by {c['author']}, +{c['additions']}/-{c['deletions']})\n"
        return output

    @tool
    def github_get_repo_stats(repo_id: str) -> str:
        """Get repository statistics including contributor activity, total commits, and branch info.
        repo_id: repo-1 (payment-service), repo-2 (cart-service), repo-3 (auth-service), repo-4 (product-service), repo-5 (order-service)."""
        data = _make_github_request(github_url, github_token, endpoint=f"/repos/{repo_id}/stats")
        if "error" in data:
            return f"Error: {data['error']}"

        output = f"Repository stats for {repo_id}:\n"
        output += f"- Total commits: {data['total_commits']}\n"
        output += f"- Total additions: {data['total_additions']}\n"
        output += f"- Total deletions: {data['total_deletions']}\n"
        output += f"- Active branches: {data['active_branches']}\n"
        output += f"- Open PRs: {data['open_prs']}\n"
        output += "\nContributors:\n"
        for c in data.get("contributors", []):
            output += f"  - {c['author']}: {c['commits']} commits (+{c['additions']}/-{c['deletions']})\n"
        return output

    @tool
    def github_create_branch(repo_id: str, branch_name: str, from_branch: str = "main") -> str:
        """[WRITE ACTION - REQUIRES APPROVAL] Create a new branch in a repository.
        repo_id: repo-1 (payment-service), repo-2 (cart-service), etc.
        branch_name: Name for the new branch (e.g., feature/PAY-109-crypto-payments)."""
        proposal = {
            "action": "create_branch",
            "system": "github",
            "params": {
                "repo_id": repo_id,
                "branch_name": branch_name,
                "from_branch": from_branch,
            },
            "description": f"Create branch '{branch_name}' in {repo_id} from {from_branch}",
        }
        return f"__PROPOSAL__{json.dumps(proposal)}__END_PROPOSAL__"

    return [github_list_repos, github_get_pull_requests, github_get_commits, github_get_repo_stats, github_create_branch]
