"""MAHALO3 Backend - FastAPI application entry point."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.database import init_db
from app.models.project import Project  # noqa: F401
from app.routers import auth, chat, health, integrations, projects, proxy

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.app_name,
        description="AI-powered multi-persona SDLC platform",
        version="0.1.0",
    )

    # CORS middleware
    origins = [origin.strip() for origin in settings.cors_origins.split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router, tags=["health"])
    app.include_router(auth.router)
    app.include_router(integrations.router)
    app.include_router(projects.router)
    app.include_router(chat.router)
    app.include_router(proxy.router)

    @app.on_event("startup")
    async def startup():
        """Initialize database and validate configuration on startup."""
        logger.info("Starting MAHALO3 backend...")
        init_db()
        logger.info("Database initialized.")

        # Seed default persona login accounts (idempotent) so a fresh deploy
        # always has the demo users ready: lava@dev.com / lava@pm.com / lava@exe.com.
        from app.core.database import SessionLocal
        from app.services.project_seed import seed_persona_projects
        from app.services.user_seed import seed_default_users

        _db = SessionLocal()
        try:
            seed_default_users(_db)
            # Must run after users exist: gives each persona the standard 5
            # demo projects with real repo names so dashboards are consistent.
            seed_persona_projects(_db)
        finally:
            _db.close()

        # Validate LLM configuration (fails fast if the orchestrator can't run,
        # normalizes the switchable synthesis provider otherwise).
        settings.validate_llm_config()
        logger.info(
            "LLM config: orchestrator=openai(%s), synthesis=%s(%s)",
            settings.orchestrator_model,
            settings.synthesis_provider,
            settings.synthesis_model,
        )

    return app


app = create_app()
