"""Provider-neutral model client with an Anthropic-compatible internal shape.

Agent modules intentionally keep using ``client.messages.create(...)``.  The
factory returns Anthropic's native client for Claude, or a LiteLLM adapter for
other providers.  Keeping the compatibility boundary here avoids coupling the
research loop to every provider's message and tool-call representation.
"""
from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any


PROVIDER_KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "azure": "AZURE_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "cohere": "COHERE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "xai": "XAI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "together_ai": "TOGETHERAI_API_KEY",
    "huggingface": "HUGGINGFACE_API_KEY",
}


def parse_chain(value: str) -> list[str]:
    """Split a comma-separated model chain into ordered candidates.

    Every ``EFFERENTS_MODEL*`` value may be a chain: the first entry is the
    preferred model, later entries are failovers tried in order when the
    preferred provider errors or has no credentials.
    """
    return [item.strip() for item in value.split(",") if item.strip()]


def configured_chain() -> list[str]:
    return parse_chain(os.environ.get("EFFERENTS_MODEL", "claude-sonnet-4-6"))


def configured_model() -> str:
    """Return the preferred (first-choice) model, preserving the Claude default."""
    return configured_chain()[0]


def resolve_chain(model: str | None = None) -> list[str]:
    if model:
        return parse_chain(model)
    return configured_chain()


def provider_for_model(model: str | None = None) -> str:
    explicit = os.environ.get("EFFERENTS_MODEL_PROVIDER", "").strip().lower()
    if explicit:
        return explicit
    value = (model or configured_model()).strip()
    if "/" in value:
        return value.split("/", 1)[0].lower()
    return "anthropic" if value.startswith("claude-") else "openai"


def required_key_env(model: str | None = None) -> str | None:
    provider = provider_for_model(model)
    # Ollama/local and AWS/Vertex commonly authenticate outside an API-key env.
    if provider in {"ollama", "bedrock", "vertex_ai", "sagemaker"}:
        return None
    return PROVIDER_KEY_ENV.get(provider, f"{provider.upper()}_API_KEY")


def _candidate_credentials_available(candidate: str) -> bool:
    key_name = required_key_env(candidate)
    return key_name is None or bool(os.environ.get(key_name, "").strip())


def credentials_available(model: str | None = None) -> bool:
    """True if any candidate in the (possibly chained) model value has keys."""
    return any(_candidate_credentials_available(c) for c in resolve_chain(model))


def credential_help(model: str | None = None) -> str:
    provider = provider_for_model(model)
    key_name = required_key_env(model)
    if key_name:
        return f"{key_name} is not available for provider {provider!r}"
    return f"credentials are not available for provider {provider!r}"


def make_client() -> Any:
    """Construct the routing client.

    The routing client dispatches each ``messages.create`` call to the provider
    of the model it names — the native Anthropic SDK for ``claude-*``, the
    LiteLLM adapter for everything else — so different roles can run on
    different providers within one process, and comma-separated model chains
    fail over across providers.
    """
    return RoutingMessagesClient()


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    out: list[str] = []
    for block in content or []:
        if isinstance(block, str):
            out.append(block)
        elif block.get("type") == "text":
            out.append(str(block.get("text", "")))
    return "".join(out)


def _system_text(system: Any) -> str:
    return _text_from_content(system)


def _convert_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted = []
    for tool in tools:
        # Anthropic's hosted web search has no portable equivalent. Omitting it
        # triggers Librarian's existing no-search synthesis path.
        if str(tool.get("type", "")).startswith("web_search_"):
            continue
        converted.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object"}),
            },
        })
    return converted


def _convert_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        role, content = message["role"], message.get("content", "")
        if not isinstance(content, list):
            converted.append({"role": role, "content": content})
            continue
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        for block in content:
            kind = block.get("type")
            if kind == "text":
                text_parts.append(str(block.get("text", "")))
            elif kind == "tool_use":
                tool_calls.append({
                    "id": block["id"],
                    "type": "function",
                    "function": {
                        "name": block["name"],
                        "arguments": json.dumps(block.get("input", {})),
                    },
                })
            elif kind == "tool_result":
                tool_results.append({
                    "role": "tool",
                    "tool_call_id": block["tool_use_id"],
                    "content": str(block.get("content", "")),
                })
        item: dict[str, Any] = {"role": role, "content": "".join(text_parts) or None}
        if tool_calls:
            item["tool_calls"] = tool_calls
        if text_parts or tool_calls:
            converted.append(item)
        converted.extend(tool_results)
    return converted


class _Messages:
    def create(self, **kwargs: Any) -> Any:
        try:
            from litellm import completion
        except ImportError as exc:  # pragma: no cover - installation problem
            raise RuntimeError(
                "Non-Anthropic models require the 'litellm' dependency; reinstall efferents"
            ) from exc

        messages = _convert_messages(kwargs["messages"])
        system = _system_text(kwargs.get("system"))
        if system:
            messages.insert(0, {"role": "system", "content": system})
        call: dict[str, Any] = {
            "model": kwargs["model"],
            "messages": messages,
            "max_tokens": kwargs.get("max_tokens"),
        }
        tools = _convert_tools(kwargs.get("tools") or [])
        if tools:
            call["tools"] = tools
        if os.environ.get("EFFERENTS_API_BASE"):
            call["api_base"] = os.environ["EFFERENTS_API_BASE"]
        response = completion(**call)
        choice = response.choices[0]
        message = choice.message
        blocks: list[Any] = []
        if message.content:
            blocks.append(SimpleNamespace(type="text", text=message.content))
        for tool_call in message.tool_calls or []:
            try:
                payload = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                payload = {"raw": tool_call.function.arguments}
            blocks.append(SimpleNamespace(
                type="tool_use", id=tool_call.id,
                name=tool_call.function.name, input=payload,
            ))
        usage = response.usage
        return SimpleNamespace(
            content=blocks,
            stop_reason="tool_use" if (message.tool_calls or []) else choice.finish_reason,
            usage=SimpleNamespace(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            ),
        )


class LiteLLMMessagesClient:
    def __init__(self) -> None:
        self.messages = _Messages()


class _RoutingMessages:
    def __init__(self, parent: "RoutingMessagesClient") -> None:
        self._parent = parent

    def create(self, **kwargs: Any) -> Any:
        chain = resolve_chain(kwargs.get("model"))
        failures: list[tuple[str, str]] = []
        last_exc: Exception | None = None
        for candidate in chain:
            if not _candidate_credentials_available(candidate):
                failures.append((candidate, credential_help(candidate)))
                continue
            provider = provider_for_model(candidate)
            model_id = candidate
            if provider == "anthropic" and candidate.lower().startswith("anthropic/"):
                model_id = candidate.split("/", 1)[1]
            delegate = self._parent.delegate_for(provider)
            try:
                response = delegate.messages.create(**{**kwargs, "model": model_id})
            except Exception as exc:  # provider outage/quota/auth — try the next link
                if len(chain) == 1:
                    raise
                last_exc = exc
                failures.append((candidate, f"{type(exc).__name__}: {exc}"))
                print(f"model_client: {candidate} failed ({type(exc).__name__}); "
                      f"failing over", flush=True)
                continue
            self._parent.last_served_model = candidate
            return response
        detail = "; ".join(f"{model} ({reason})" for model, reason in failures)
        raise RuntimeError(f"all models in chain failed: {detail}") from last_exc


class RoutingMessagesClient:
    """Per-call provider routing with chain failover.

    ``messages.create(model="moonshot/kimi-k2-thinking,claude-sonnet-5")``
    tries Kimi first and falls back to Claude on any provider error; a bare
    single model behaves exactly as before. Provider delegates are cached, so
    mixed-provider role configs share one client instance.
    """

    def __init__(self) -> None:
        self.messages = _RoutingMessages(self)
        self.last_served_model: str | None = None
        self._anthropic_client: Any = None
        self._litellm_client = LiteLLMMessagesClient()

    def delegate_for(self, provider: str) -> Any:
        if provider == "anthropic":
            if self._anthropic_client is None:
                import anthropic
                self._anthropic_client = anthropic.Anthropic()
            return self._anthropic_client
        return self._litellm_client
