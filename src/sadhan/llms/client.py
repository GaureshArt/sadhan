from __future__ import annotations

from typing import Any, AsyncIterator, Iterable

import litellm

from .registry import Model, registry

litellm.suppress_debug_info = True

PROVIDER_PARAMS: dict[str, dict[str, Any]] = {
    "ollama": {"think": False},
}


def _first_delta(chunk: Any) -> Any | None:
    choices = getattr(chunk, "choices", None)
    if not choices:
        return None
    return getattr(choices[0], "delta", None)


def chunk_text(chunk: Any) -> str:
    delta = _first_delta(chunk)
    if delta is None:
        return ""
    return getattr(delta, "content", None) or ""


def chunk_reasoning(chunk: Any) -> str:
    delta = _first_delta(chunk)
    if delta is None:
        return ""
    return getattr(delta, "reasoning_content", None) or ""


def chunk_usage_tokens(chunk: Any) -> int | None:
    usage = getattr(chunk, "usage", None)
    if usage is None:
        return None
    total = getattr(usage, "total_tokens", None)
    if total is not None:
        return int(total)
    prompt = getattr(usage, "prompt_tokens", None) or 0
    completion = getattr(usage, "completion_tokens", None) or 0
    if prompt or completion:
        return int(prompt + completion)
    return None


class LiteLLMClient:
    def __init__(
        self,
        model: str | Model | None = None,
        *,
        api_base: str | None = None,
        timeout: float = 300.0,
        **default_params: Any,
    ) -> None:
        self._model = model
        self.api_base = api_base
        self.timeout = timeout
        self.default_params = default_params

    @property
    def model(self) -> str | None:
        if isinstance(self._model, Model):
            return self._model.name
        if self._model:
            return self._model
        active = registry.active
        return active.name if active else None

    @property
    def provider(self) -> str | None:
        if isinstance(self._model, Model):
            return self._model.provider
        active = registry.active
        return active.provider if active else None

    def _resolve(self, model: str | Model | None) -> tuple[str | None, str | None]:
        if isinstance(model, Model):
            return model.name, model.provider
        if model:
            provider = model.split("/", 1)[0] if "/" in model else None
            return model, provider
        return self.model, self.provider

    def _params(self, messages: Iterable[dict], model, provider, stream: bool, overrides: dict) -> dict:
        name, resolved_provider = self._resolve(model)
        if name is None:
            raise RuntimeError("no model selected")

        provider = provider or resolved_provider
        params: dict[str, Any] = {
            "model": name,
            "messages": list(messages),
            "stream": stream,
            "timeout": self.timeout,
        }
        if self.api_base:
            params["api_base"] = self.api_base
        params.update(self.default_params)
        if provider:
            params.update(PROVIDER_PARAMS.get(provider, {}))
        params.update(overrides)
        return params

    async def stream_chat(
        self,
        messages: Iterable[dict],
        *,
        model: str | Model | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[Any]:
        params = self._params(messages, model, provider, True, kwargs)
        response = await litellm.acompletion(**params)
        async for chunk in response:
            yield chunk

    async def chat(
        self,
        messages: Iterable[dict],
        *,
        model: str | Model | None = None,
        provider: str | None = None,
        **kwargs: Any,
    ) -> str:
        params = self._params(messages, model, provider, False, kwargs)
        response = await litellm.acompletion(**params)
        return response.choices[0].message.content or ""