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


def configured_model() -> str:
    """Return the default model identifier, preserving the Claude default."""
    return os.environ.get("EFFERENTS_MODEL", "claude-sonnet-4-6").strip()


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


def credentials_available(model: str | None = None) -> bool:
    key_name = required_key_env(model)
    return key_name is None or bool(os.environ.get(key_name, "").strip())


def credential_help(model: str | None = None) -> str:
    provider = provider_for_model(model)
    key_name = required_key_env(model)
    if key_name:
        return f"{key_name} is not available for provider {provider!r}"
    return f"credentials are not available for provider {provider!r}"


def make_client() -> Any:
    """Construct the native Anthropic client or the provider-neutral adapter."""
    provider = provider_for_model()
    if provider == "anthropic":
        import anthropic
        return anthropic.Anthropic()
    return LiteLLMMessagesClient()


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
