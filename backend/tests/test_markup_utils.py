"""Tests for DSML/XML tool call parsing and markup sanitization."""

import pytest
from app.agent.markup_utils import clean_tool_markup, parse_text_tool_calls


def test_parse_dsml_tool_calls_no_params():
    dsml_text = """I'll look into both projects across the systems to find concrete commonalities rather than just speculating. Let me pull data from Jira, Confluence, GitHub, and ServiceNow.

<｜｜DSML｜｜tool_calls> <｜｜DSML｜｜invoke name="jira_list_projects"> <｜｜DSML｜｜invoke name="jira_get_stories"> <｜｜DSML｜｜invoke name="confluence_get_spaces"> <｜｜DSML｜｜invoke name="github_list_repositories"> <｜｜DSML｜｜invoke name="servicenow_get_services"> </｜｜DSML｜｜invoke> </｜｜DSML｜｜invoke> </｜｜DSML｜｜invoke> </｜｜DSML｜｜invoke> </｜｜DSML｜｜invoke> </｜｜DSML｜｜tool_calls>"""

    calls = parse_text_tool_calls(dsml_text)
    assert len(calls) == 5
    names = [c["name"] for c in calls]
    assert names == [
        "jira_list_projects",
        "jira_get_stories",
        "confluence_get_spaces",
        "github_list_repositories",
        "servicenow_get_services",
    ]


def test_parse_dsml_tool_calls_with_params():
    dsml_text = """<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="jira_get_stories">
<｜｜DSML｜｜parameter name="project_id" string="true">GOLD</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>"""

    calls = parse_text_tool_calls(dsml_text)
    assert len(calls) == 1
    assert calls[0]["name"] == "jira_get_stories"
    assert calls[0]["args"] == {"project_id": "GOLD"}


def test_parse_json_tool_calls():
    json_tc = '<tool_call>{"name": "jira_get_stories", "arguments": {"project_id": "PAY"}}</tool_call>'
    calls = parse_text_tool_calls(json_tc)
    assert len(calls) == 1
    assert calls[0]["name"] == "jira_get_stories"
    assert calls[0]["args"] == {"project_id": "PAY"}


def test_clean_tool_markup_dsml():
    raw_text = """I'll look into both projects across the systems.

<｜｜DSML｜｜tool_calls> <｜｜DSML｜｜invoke name="jira_list_projects"> </｜｜DSML｜｜invoke> </｜｜DSML｜｜tool_calls>"""

    cleaned = clean_tool_markup(raw_text)
    assert cleaned == "I'll look into both projects across the systems."
    assert "DSML" not in cleaned
    assert "invoke" not in cleaned


def test_clean_tool_markup_empty_and_normal():
    assert clean_tool_markup("") == ""
    assert clean_tool_markup("Here is the final report for both projects.") == "Here is the final report for both projects."
