"""Seed consistent demo projects for the persona users.

Each demo persona (lava@dev.com / lava@exe.com / lava@pm.com) gets the SAME set
of 5 projects, aligned to the Jira seed projects (PAY/CART/AUTH/PROD/ORD) and the
mock-system service/repo names. This keeps the dashboard and agent consistent
across personas and survives the monthly account reset (runs idempotently at
startup).

NOTE: only `payment-service` currently exists in Gitea, so only the PAY project's
github_repo_name resolves to a real repo today. The others are seeded with their
intended names for when per-project repos are added (BACKLOG item #2); until then
the dashboard widgets simply show "no data" for those (they no longer hang).
"""

import logging

from sqlalchemy.orm import Session

from app.models.project import Project, ProjectType
from app.models.user import User

logger = logging.getLogger(__name__)

# jira_key, name, repo (real Gitea repo for PAY; intended names for the rest),
# confluence space, servicenow service.
_PROJECTS = [
    ("PAY", "Payment Gateway", "payment-service", "PAYMENTG", "payment-service"),
    ("CART", "Shopping Cart", "cart-service", "CART", "cart-service"),
    ("AUTH", "User Authentication", "auth-service", "AUTH", "auth-service"),
    ("PROD", "Product Catalog", "product-catalog", "PROD", "product-service"),
    ("ORD", "Order Management", "order-management", "ORD", "order-service"),
]

_PERSONA_EMAILS = ["lava@dev.com", "lava@exe.com", "lava@pm.com"]


def seed_persona_projects(db: Session) -> None:
    """Ensure each persona user has the standard 5 demo projects (idempotent).

    Reconciles existing projects (fixes stale github_repo_name) and creates any
    missing ones. The PAY project is marked active so the dashboard has a default
    scope that maps to the one real repo.
    """
    changed = 0
    for email in _PERSONA_EMAILS:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            continue
        for jira_key, name, repo, space, service in _PROJECTS:
            proj = (
                db.query(Project)
                .filter(Project.user_id == user.id, Project.jira_project_key == jira_key)
                .first()
            )
            if proj is None:
                db.add(
                    Project(
                        user_id=user.id,
                        name=name,
                        description=f"{name} demo project",
                        goal="",
                        project_type=ProjectType.DEVELOPMENT,
                        status="active",
                        jira_project_key=jira_key,
                        confluence_space_key=space,
                        github_repo_name=repo,
                        servicenow_service_name=service,
                        is_active=(jira_key == "PAY"),
                        is_selected=(jira_key == "PAY"),
                    )
                )
                changed += 1
            else:
                # Reconcile stale fields (e.g. github_repo_name=payment-gateway).
                if proj.github_repo_name != repo:
                    proj.github_repo_name = repo
                    changed += 1
                if proj.servicenow_service_name != service:
                    proj.servicenow_service_name = service
                    changed += 1
                if jira_key == "PAY" and not proj.is_active:
                    proj.is_active = True
                    changed += 1
    if changed:
        db.commit()
        logger.info("Seeded/reconciled %d persona project field(s).", changed)
    else:
        logger.info("Persona projects already consistent; nothing to seed.")
