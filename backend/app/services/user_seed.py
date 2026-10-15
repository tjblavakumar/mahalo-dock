"""Seed default persona users for the demo.

Creates one login account per role so a fresh deploy (or the monthly account
reset) always has the three demo personas ready without manual registration:

    lava@dev.com  -> Developer
    lava@pm.com   -> Product Manager
    lava@exe.com  -> Executive

Idempotent: existing emails are skipped, so this is safe to run on every
startup. Passwords are demo-only (change for any non-demo use).
"""

import logging

from sqlalchemy.orm import Session

from app.models.user import User, UserRole
from app.services.auth_service import hash_password

logger = logging.getLogger(__name__)

# Demo-only default password for all seeded personas.
DEFAULT_PASSWORD = "MahaloDock123!"

DEFAULT_USERS = [
    {"email": "lava@dev.com", "name": "Lava Dev", "role": UserRole.DEVELOPER},
    {"email": "lava@pm.com", "name": "Lava PM", "role": UserRole.PRODUCT_MANAGER},
    {"email": "lava@exe.com", "name": "Lava Exec", "role": UserRole.EXECUTIVE},
]


def seed_default_users(db: Session) -> None:
    """Create the default persona users if they don't already exist."""
    created = 0
    for spec in DEFAULT_USERS:
        exists = db.query(User).filter(User.email == spec["email"]).first()
        if exists:
            continue
        db.add(
            User(
                email=spec["email"],
                name=spec["name"],
                role=spec["role"],
                password_hash=hash_password(DEFAULT_PASSWORD),
            )
        )
        created += 1
    if created:
        db.commit()
        logger.info("Seeded %d default persona user(s).", created)
    else:
        logger.info("Default persona users already present; nothing seeded.")
