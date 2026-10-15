"""Single source of truth mapping app login users to mock-system identities.

The mock systems (Jira, GitHub, ServiceNow) identify people by developer IDs
(dev-1 .. dev-6), while the app logs users in by email. This module maps the
demo persona logins to the Jira developer identity that represents "you" in the
seed data, so the dashboard widgets and the agent's "me" resolution all key off
the SAME id and the demo data stays consistent.

All three demo personas (developer / executive / product manager) represent the
same demo person — "Lava Dev" (dev-6) in the Jira seed data — so they map to
dev-6. Change here if the seed data's identity for the demo user changes.
"""

# Jira seed data: dev-6 == "Lava Dev" (lava@ecommerce.io). The demo personas all
# map to this single identity.
_DEMO_DEVELOPER_ID = "dev-6"

EMAIL_TO_DEVELOPER_ID = {
    "lava@dev.com": _DEMO_DEVELOPER_ID,
    "lava@exe.com": _DEMO_DEVELOPER_ID,
    "lava@pm.com": _DEMO_DEVELOPER_ID,
}

# Fallback for any other login (e.g. earlier manually-registered accounts) so the
# dashboard still resolves to the demo identity rather than the stale "dev-1".
DEFAULT_DEVELOPER_ID = _DEMO_DEVELOPER_ID


def developer_id_for_email(email: str | None) -> str:
    """Resolve a login email to the mock-system developer id."""
    if not email:
        return DEFAULT_DEVELOPER_ID
    return EMAIL_TO_DEVELOPER_ID.get(email.strip().lower(), DEFAULT_DEVELOPER_ID)
