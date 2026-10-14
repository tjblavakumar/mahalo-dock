"""Unit tests for the LLM provider factory and config validation.

External SDK clients (ChatOpenAI, ChatBedrockConverse, OneMinAIChatModel) are
monkeypatched so these tests need no network, API keys, or AWS credentials — we
only assert that the factory picks the right client and passes the right
model/region per provider, and that validate_llm_config behaves per provider.
"""

import sys
import types

import pytest

from app.agent import llm_factory
from app.core.config import Settings


# --------------------------------------------------------------------------
# Helpers: record-only fake clients
# --------------------------------------------------------------------------

class _FakeChat:
    """Captures constructor kwargs so tests can assert what was requested."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _patch_openai(monkeypatch):
    created = {}

    def factory(**kwargs):
        obj = _FakeChat(**kwargs)
        created["openai"] = obj
        return obj

    # llm_factory imports ChatOpenAI lazily inside _build_openai_compatible:
    #   from langchain_openai import ChatOpenAI
    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = factory
    monkeypatch.setitem(sys.modules, "langchain_openai", mod)
    return created


def _patch_bedrock(monkeypatch):
    created = {}

    def factory(**kwargs):
        obj = _FakeChat(**kwargs)
        created["bedrock"] = obj
        return obj

    mod = types.ModuleType("langchain_aws")
    mod.ChatBedrockConverse = factory
    monkeypatch.setitem(sys.modules, "langchain_aws", mod)
    return created


def _use_settings(monkeypatch, **overrides):
    """Point llm_factory.settings at a fresh Settings with given overrides."""
    s = Settings(**overrides)
    monkeypatch.setattr(llm_factory, "settings", s)
    return s


# --------------------------------------------------------------------------
# Orchestrator provider selection
# --------------------------------------------------------------------------

def test_orchestrator_openrouter_uses_chatopenai(monkeypatch):
    created = _patch_openai(monkeypatch)
    _use_settings(
        monkeypatch,
        llm_provider="openrouter",
        orchestrator_model="openai/gpt-5-nano",
        openai_api_key="k",
        openai_base_url="https://openrouter.ai/api/v1",
    )
    llm = llm_factory.build_orchestrator_llm(temperature=0.1)
    assert "openai" in created and llm is created["openai"]
    assert llm.kwargs["model"] == "openai/gpt-5-nano"
    assert llm.kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert llm.kwargs["temperature"] == 0.1


def test_orchestrator_bedrock_uses_converse(monkeypatch):
    created = _patch_bedrock(monkeypatch)
    _use_settings(
        monkeypatch,
        llm_provider="bedrock",
        bedrock_region="us-west-2",
        bedrock_orchestrator_model="anthropic.claude-3-5-sonnet-20240620-v1:0",
    )
    llm = llm_factory.build_orchestrator_llm(temperature=0.1)
    assert "bedrock" in created and llm is created["bedrock"]
    assert llm.kwargs["model"] == "anthropic.claude-3-5-sonnet-20240620-v1:0"
    assert llm.kwargs["region_name"] == "us-west-2"


def test_orchestrator_bedrock_does_not_touch_openai(monkeypatch):
    # If bedrock is selected, importing/constructing ChatOpenAI must not happen.
    _patch_bedrock(monkeypatch)

    def boom(**kwargs):
        raise AssertionError("ChatOpenAI should not be built in bedrock mode")

    mod = types.ModuleType("langchain_openai")
    mod.ChatOpenAI = boom
    monkeypatch.setitem(sys.modules, "langchain_openai", mod)

    _use_settings(monkeypatch, llm_provider="bedrock")
    llm_factory.build_orchestrator_llm()  # must not raise


# --------------------------------------------------------------------------
# Synthesis provider selection
# --------------------------------------------------------------------------

def test_synthesis_bedrock_uses_converse(monkeypatch):
    created = _patch_bedrock(monkeypatch)
    _use_settings(
        monkeypatch,
        synthesis_provider="bedrock",
        bedrock_region="eu-west-1",
        bedrock_synthesis_model="anthropic.claude-3-haiku-20240307-v1:0",
    )
    llm = llm_factory.build_synthesis_llm(temperature=0.2)
    assert llm is created["bedrock"]
    assert llm.kwargs["model"] == "anthropic.claude-3-haiku-20240307-v1:0"
    assert llm.kwargs["region_name"] == "eu-west-1"


def test_synthesis_openai_uses_chatopenai(monkeypatch):
    created = _patch_openai(monkeypatch)
    _use_settings(
        monkeypatch,
        synthesis_provider="openai",
        synthesis_model="gpt-4o",
        openai_api_key="k",
    )
    llm = llm_factory.build_synthesis_llm()
    assert llm is created["openai"]
    assert llm.kwargs["model"] == "gpt-4o"


def test_synthesis_onemin_uses_onemin(monkeypatch):
    # Patch the OneMin client where it's imported from.
    import app.agent.onemin_llm as onemin_mod

    created = {}

    class FakeOneMin:
        def __init__(self, **kwargs):
            created["onemin"] = kwargs

    monkeypatch.setattr(onemin_mod, "OneMinAIChatModel", FakeOneMin)
    _use_settings(
        monkeypatch,
        synthesis_provider="onemin",
        synthesis_model="deepseek-flash",
        onemin_api_key="k",
        onemin_base_url="https://api.1min.ai",
    )
    llm_factory.build_synthesis_llm()
    assert created["onemin"]["model"] == "deepseek-flash"


# --------------------------------------------------------------------------
# validate_llm_config
# --------------------------------------------------------------------------

def test_validate_bedrock_requires_no_openai_key():
    s = Settings(llm_provider="bedrock", openai_api_key="", synthesis_provider="bedrock")
    s.validate_llm_config()  # must not raise
    assert s.llm_provider == "bedrock"
    assert s.synthesis_provider == "bedrock"


def test_validate_openrouter_requires_openai_key():
    s = Settings(llm_provider="openrouter", openai_api_key="")
    with pytest.raises(RuntimeError):
        s.validate_llm_config()


def test_validate_unknown_provider_falls_back_to_openrouter():
    s = Settings(llm_provider="nonsense", openai_api_key="k")
    s.validate_llm_config()
    assert s.llm_provider == "openrouter"


def test_validate_onemin_without_key_falls_back_to_openai():
    s = Settings(
        llm_provider="openrouter",
        openai_api_key="k",
        synthesis_provider="onemin",
        onemin_api_key="",
    )
    s.validate_llm_config()
    assert s.synthesis_provider == "openai"
