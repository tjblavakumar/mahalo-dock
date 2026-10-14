"""LangChain tools for Mock Confluence service."""

import httpx
from langchain_core.tools import tool


def _make_confluence_request(url: str, token: str, endpoint: str = "", params: dict = None) -> dict:
    """Make a request to the Confluence mock service."""
    headers = {"X-API-Token": token}
    full_url = f"{url}{endpoint}"

    with httpx.Client(timeout=10.0) as client:
        response = client.get(full_url, headers=headers, params=params)

    if response.status_code == 200:
        return response.json()
    else:
        return {"error": f"Request failed with status {response.status_code}: {response.text}"}


def create_confluence_tools(confluence_url: str, confluence_token: str):
    """Create LangChain tools configured for a specific Confluence instance."""

    @tool
    def confluence_search(query: str, space_id: str = None) -> str:
        """Search Confluence documentation by keyword. Optionally filter by space_id (ENG, SEC, PROD, API).
        Use this to find architecture docs, security guidelines, API specs, requirements, and retrospectives."""
        params = {"q": query}
        if space_id:
            params["space_id"] = space_id
        data = _make_confluence_request(confluence_url, confluence_token, endpoint="/search", params=params)
        if "error" in data:
            return f"Error: {data['error']}"

        results = data.get("results", [])
        if not results:
            return f"No documentation found matching '{query}'"

        output = f"Found {len(results)} documents matching '{query}':\n"
        for r in results:
            output += f"\n📄 **{r['title']}** (Space: {r['space_id']})\n"
            output += f"   Author: {r['author']} | Updated: {r['last_updated']}\n"
            output += f"   Excerpt: {r['excerpt'][:150]}...\n"
        return output

    @tool
    def confluence_get_page(page_id: str) -> str:
        """Get the full content of a Confluence page by its ID (e.g., ENG-001, SEC-001, PROD-001, API-001).
        Use this after searching to read the full document content."""
        data = _make_confluence_request(confluence_url, confluence_token, endpoint=f"/pages/{page_id}")
        if "error" in data:
            return f"Error: {data['error']}"

        output = f"📄 **{data['title']}**\n"
        output += f"Space: {data['space_id']} | Author: {data['author']} | Updated: {data['last_updated']}\n\n"
        # Truncate content if too long for context
        content = data.get("content", "")
        if len(content) > 2000:
            content = content[:2000] + "\n\n... [content truncated]"
        output += content
        return output

    @tool
    def confluence_list_spaces() -> str:
        """List all available Confluence spaces."""
        data = _make_confluence_request(confluence_url, confluence_token, endpoint="/spaces")
        if "error" in data:
            return f"Error: {data['error']}"

        output = "Available Confluence spaces:\n"
        for s in data.get("spaces", []):
            output += f"- **{s['id']}**: {s['name']} - {s['description']}\n"
        return output

    return [confluence_search, confluence_get_page, confluence_list_spaces]
