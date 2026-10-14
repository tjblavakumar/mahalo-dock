from app.agent.demo_agent import build_project_context
from app.routers.projects import build_project_bootstrap_payloads
from app.models.project import Project


def test_build_project_context_uses_active_project_identifiers():
    project = Project(
        id=42,
        user_id=1,
        name="Customer Portal",
        description="Portal project",
        goal="Launch portal",
        project_type="development",
        status="active",
        jira_project_key="CP",
        confluence_space_key="CP",
        github_repo_name="customer-portal",
        servicenow_service_name="CP",
        generate_mock_data=True,
        is_active=True,
        is_selected=True,
    )

    context = build_project_context(project)

    assert context["jira_project_key"] == "CP"
    assert context["confluence_space_key"] == "CP"
    assert context["github_repo_name"] == "customer-portal"
    assert context["project_name"] == "Customer Portal"


def test_build_project_bootstrap_payloads_for_mock_project():
    project = Project(
        id=99,
        user_id=1,
        name="Customer Portal",
        description="Portal project",
        goal="Launch portal",
        project_type="development",
        status="active",
        jira_project_key="CP",
        confluence_space_key="CP",
        github_repo_name="customer-portal",
        servicenow_service_name="CP",
        generate_mock_data=True,
        is_active=True,
        is_selected=True,
    )

    payloads = build_project_bootstrap_payloads(project)

    assert any(item["service"] == "jira" and item["path"] == "/projects" for item in payloads)
    assert any(item["service"] == "jira" and item["path"] == "/stories" for item in payloads)
    assert any(item["service"] == "confluence" and item["path"] == "/spaces" for item in payloads)
    assert any(item["service"] == "confluence" and item["path"] == "/spaces/CP/pages" for item in payloads)
    assert any(item["service"] == "github" and item["path"] == "/repos" for item in payloads)
    assert any(item["service"] == "github" and item["path"] == "/repos/customer-portal/readme" for item in payloads)
