"""Application configuration loaded from environment variables."""

import logging
from pathlib import Path

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

# Resolve the workspace-root .env regardless of the process working directory.
# This file lives at <root>/backend/app/core/config.py, so the root is 3 parents
# up from here. The backend is typically launched from the backend/ directory,
# where no .env exists, so we must point at the root copy explicitly.
_ROOT_ENV = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Application settings."""

    # App
    app_name: str = "MAHALO3 Backend"
    debug: bool = False

    # Database
    database_url: str = "sqlite:///./mahalo3.db"

    # JWT
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_minutes: int = 60

    # CORS
    cors_origins: str = "http://localhost:3000"

    # ── LLM Configuration ─────────────────────────────
    # Orchestrator (tool-calling brain): ALWAYS OpenAI. It needs native function
    # calling, which only the OpenAI-compatible /chat/completions path provides.
    orchestrator_model: str = "gpt-4o"

    # Synthesis (final response phrasing): switchable provider.
    synthesis_provider: str = "onemin"  # "onemin" | "openai"
    synthesis_model: str = "gpt-4o"

    # OpenAI credentials (required — orchestrator depends on these)
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # 1min.ai credentials (required when synthesis_provider == "onemin")
    onemin_api_key: str = ""
    onemin_base_url: str = "https://api.1min.ai"

    # Mock Services
    mock_jira_url: str = "http://localhost:5001"
    mock_confluence_url: str = "http://localhost:5002"
    mock_github_url: str = "http://localhost:5003"
    mock_servicenow_url: str = "http://localhost:5004"

    class Config:
        # Prefer the workspace-root .env (absolute path), but also honor a
        # backend/.env if one exists (later entries take precedence).
        env_file = (str(_ROOT_ENV), ".env")
        env_file_encoding = "utf-8"
        # The shared .env also holds vars for the frontend, mock services, and
        # launch scripts. Ignore anything that isn't a declared setting here.
        extra = "ignore"

    # ── Validation / guardrails ───────────────────────

    def validate_llm_config(self) -> None:
        """Validate LLM configuration and normalize switchable options.

        - Orchestrator always requires an OpenAI API key (fail fast).
        - synthesis_provider must be one of the supported values; unknown
          values fall back to "openai" with a warning.
        - If synthesis is set to "onemin" but no 1min.ai key is configured,
          fall back to OpenAI synthesis so the demo still works.
        """
        if not self.openai_api_key or self.openai_api_key.startswith("sk-your-"):
            raise RuntimeError(
                "OPENAI_API_KEY is not configured. The orchestrator requires a "
                "valid OpenAI API key for tool calling. Set OPENAI_API_KEY in .env."
            )

        provider = (self.synthesis_provider or "").strip().lower()
        if provider not in ("onemin", "openai"):
            logger.warning(
                "Unknown SYNTHESIS_PROVIDER '%s'; falling back to 'openai'.",
                self.synthesis_provider,
            )
            provider = "openai"

        if provider == "onemin" and (
            not self.onemin_api_key or self.onemin_api_key.startswith("your-")
        ):
            logger.warning(
                "SYNTHESIS_PROVIDER=onemin but ONEMIN_API_KEY is not configured; "
                "falling back to OpenAI for synthesis."
            )
            provider = "openai"

        self.synthesis_provider = provider


settings = Settings()
