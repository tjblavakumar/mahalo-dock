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
    # Orchestrator provider (the tool-calling brain). It must support native
    # function/tool calling. Supported:
    #   openrouter | openai  -> OpenAI-compatible endpoint (ChatOpenAI)
    #   bedrock              -> Amazon Bedrock (ChatBedrockConverse); creds come
    #                           from the standard AWS chain, no API key needed.
    # "openai" is accepted as an alias for the OpenAI-compatible path.
    llm_provider: str = "openrouter"

    # Model used by the orchestrator. For openrouter/openai this is an
    # OpenAI-style id (e.g. "openai/gpt-5-nano"); unused in bedrock mode (see
    # bedrock_orchestrator_model).
    orchestrator_model: str = "gpt-4o"

    # Synthesis (final response phrasing): switchable provider.
    #   onemin | openai | bedrock
    synthesis_provider: str = "onemin"
    synthesis_model: str = "gpt-4o"

    # OpenAI / OpenAI-compatible credentials (required for openrouter/openai
    # providers; NOT required in bedrock mode).
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"

    # 1min.ai credentials (required when synthesis_provider == "onemin")
    onemin_api_key: str = ""
    onemin_base_url: str = "https://api.1min.ai"

    # Amazon Bedrock (used when llm_provider/synthesis_provider == "bedrock").
    # No API key: boto3 resolves credentials from the standard AWS chain
    # (instance role, env vars, or a mounted ~/.aws profile).
    bedrock_region: str = "us-east-1"
    # Tool-calling-capable model id (e.g. an Anthropic Claude 3.5+ Bedrock id).
    bedrock_orchestrator_model: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    bedrock_synthesis_model: str = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    # Read timeout (seconds) for Bedrock Converse calls. The boto3 default is 60s,
    # which is too short when the model generates a large response (e.g. a full
    # source file), causing ReadTimeoutError mid-generation. Code generation can
    # legitimately take minutes.
    bedrock_read_timeout: int = 300
    bedrock_connect_timeout: int = 10

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

        - Normalize ``llm_provider`` (openrouter | openai | bedrock); unknown
          values fall back to "openrouter" with a warning.
        - The orchestrator requires an OpenAI API key ONLY for the OpenAI-
          compatible providers (openrouter/openai). In bedrock mode no key is
          needed (boto3 resolves AWS credentials).
        - synthesis_provider must be onemin | openai | bedrock; unknown values
          fall back to "openai" with a warning.
        - If synthesis is "onemin" but no 1min.ai key is configured, fall back to
          OpenAI synthesis so the demo still works.
        """
        provider = (self.llm_provider or "").strip().lower()
        if provider not in ("openrouter", "openai", "bedrock"):
            logger.warning(
                "Unknown LLM_PROVIDER '%s'; falling back to 'openrouter'.",
                self.llm_provider,
            )
            provider = "openrouter"
        self.llm_provider = provider

        # OpenAI key only required for the OpenAI-compatible orchestrator paths.
        if provider in ("openrouter", "openai"):
            if not self.openai_api_key or self.openai_api_key.startswith("sk-your-"):
                raise RuntimeError(
                    "OPENAI_API_KEY is not configured. The orchestrator "
                    f"(LLM_PROVIDER={provider}) requires a valid OpenAI-compatible "
                    "API key for tool calling. Set OPENAI_API_KEY in .env, or use "
                    "LLM_PROVIDER=bedrock."
                )

        syn = (self.synthesis_provider or "").strip().lower()
        if syn not in ("onemin", "openai", "bedrock"):
            logger.warning(
                "Unknown SYNTHESIS_PROVIDER '%s'; falling back to 'openai'.",
                self.synthesis_provider,
            )
            syn = "openai"

        if syn == "onemin" and (
            not self.onemin_api_key or self.onemin_api_key.startswith("your-")
        ):
            logger.warning(
                "SYNTHESIS_PROVIDER=onemin but ONEMIN_API_KEY is not configured; "
                "falling back to OpenAI for synthesis."
            )
            syn = "openai"

        self.synthesis_provider = syn


settings = Settings()
