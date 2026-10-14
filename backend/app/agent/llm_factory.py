"""Central factory for building LangChain chat models per configured provider.

Keeps provider selection in ONE place so the orchestrator (agent.py) and the
synthesis layer (synthesis.py) stay in sync and new providers are easy to add.

Providers
---------
Orchestrator (``settings.llm_provider``) — must support tool calling:
    openrouter | openai -> ``ChatOpenAI`` against an OpenAI-compatible endpoint
    bedrock             -> ``ChatBedrockConverse`` (Amazon Bedrock, Converse API)

Synthesis (``settings.synthesis_provider``) — phrasing only, no tools:
    onemin  -> ``OneMinAIChatModel``
    openai  -> ``ChatOpenAI``
    bedrock -> ``ChatBedrockConverse``

Bedrock uses the standard AWS credential chain via boto3 (instance role, env
vars, or a mounted ~/.aws profile) — no API key is passed in.
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_bedrock(model: str, temperature: float):
    """Build a Bedrock Converse chat model (lazy import of langchain-aws)."""
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(
        model=model,
        region_name=settings.bedrock_region,
        temperature=temperature,
    )


def _build_openai_compatible(model: str, temperature: float):
    """Build a ChatOpenAI against the configured OpenAI-compatible endpoint."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        temperature=temperature,
    )


def build_orchestrator_llm(temperature: float = 0.1):
    """Construct the orchestrator chat model for the active ``llm_provider``.

    The caller is responsible for ``.bind_tools(...)``. The returned model MUST
    support tool calling (true for OpenAI-compatible models and for Bedrock
    Converse with tool-capable models such as Anthropic Claude 3.5+).
    """
    provider = (settings.llm_provider or "openrouter").strip().lower()
    if provider == "bedrock":
        logger.info(
            "Orchestrator: Bedrock (%s, region=%s)",
            settings.bedrock_orchestrator_model,
            settings.bedrock_region,
        )
        return _build_bedrock(settings.bedrock_orchestrator_model, temperature)

    # openrouter / openai (and any normalized fallback)
    logger.info("Orchestrator: OpenAI-compatible (%s)", settings.orchestrator_model)
    return _build_openai_compatible(settings.orchestrator_model, temperature)


def build_synthesis_llm(temperature: float = 0.2):
    """Construct the synthesis chat model for the active ``synthesis_provider``."""
    provider = (settings.synthesis_provider or "openai").strip().lower()

    if provider == "onemin":
        from app.agent.onemin_llm import OneMinAIChatModel

        return OneMinAIChatModel(
            api_key=settings.onemin_api_key,
            base_url=settings.onemin_base_url.rstrip("/v1").rstrip("/"),
            model=settings.synthesis_model,
            temperature=temperature,
        )

    if provider == "bedrock":
        return _build_bedrock(settings.bedrock_synthesis_model, temperature)

    # Default / fallback: OpenAI-compatible
    return _build_openai_compatible(settings.synthesis_model, temperature)
