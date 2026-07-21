from __future__ import annotations

from types import SimpleNamespace

from efferents.agents.budget import CallUsage, cost_usd, model_for
from efferents.agents.model_client import (
    LiteLLMMessagesClient,
    credentials_available,
    provider_for_model,
    required_key_env,
)


def test_provider_and_credentials_follow_selected_model(monkeypatch):
    monkeypatch.setenv("EFFERENTS_MODEL", "openai/gpt-5")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert provider_for_model() == "openai"
    assert required_key_env() == "OPENAI_API_KEY"
    assert not credentials_available()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert credentials_available()


def test_local_provider_does_not_require_api_key(monkeypatch):
    monkeypatch.setenv("EFFERENTS_MODEL", "ollama/llama3.3")
    assert required_key_env() is None
    assert credentials_available()


def test_unknown_provider_uses_conventional_key_name():
    assert required_key_env("perplexity/sonar-pro") == "PERPLEXITY_API_KEY"


def test_role_model_override(monkeypatch):
    monkeypatch.setenv("EFFERENTS_MODEL", "openai/gpt-5-mini")
    monkeypatch.setenv("EFFERENTS_MODEL_CODER", "openai/gpt-5")
    assert model_for("writer") == "openai/gpt-5-mini"
    assert model_for("coder") == "openai/gpt-5"


def test_litellm_adapter_converts_text_usage_and_model(monkeypatch):
    calls = []

    def fake_completion(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            choices=[SimpleNamespace(
                finish_reason="stop",
                message=SimpleNamespace(content="hello", tool_calls=[]),
            )],
            usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3),
        )

    monkeypatch.setattr("litellm.completion", fake_completion)
    response = LiteLLMMessagesClient().messages.create(
        model="openai/gpt-5-mini",
        max_tokens=50,
        system=[{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
    )
    assert calls[0]["model"] == "openai/gpt-5-mini"
    assert calls[0]["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hi"},
    ]
    assert response.content[0].text == "hello"
    assert response.usage.input_tokens == 12
    assert response.usage.output_tokens == 3


def test_non_anthropic_model_uses_litellm_pricing():
    assert cost_usd("openai/gpt-5", CallUsage(1_000_000, 1_000_000)) > 0
