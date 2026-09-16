from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path

DEFAULT_OLLAMA_BASE = "http://localhost:11434"

PROVIDER_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "xai": "XAI_API_KEY",
    "cohere": "COHERE_API_KEY",
    "together": "TOGETHERAI_API_KEY",
    "fireworks": "FIREWORKS_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "azure": "AZURE_API_KEY",
    "bedrock": "AWS_ACCESS_KEY_ID",
    "vertex_ai": "GOOGLE_APPLICATION_CREDENTIALS",
}

CATALOG: dict[str, list[str]] = {
    "openai": [
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "openai/gpt-4.1-mini",
        "openai/gpt-4.1",
        "openai/o3-mini",
    ],
    "anthropic": [
        "anthropic/claude-sonnet-4-20250514",
        "anthropic/claude-3-5-sonnet-latest",
        "anthropic/claude-3-5-haiku-latest",
    ],
    "gemini": [
        "gemini/gemini-3.6-flash",
        "gemini/gemini-1.5-pro",
        "gemini/gemini-1.5-flash",
    ],
    "groq": [
        "groq/llama-3.3-70b-versatile",
        "groq/llama-3.1-8b-instant",
    ],
    "deepseek": [
        "deepseek/deepseek-chat",
        "deepseek/deepseek-reasoner",
    ],
    "mistral": [
        "mistral/mistral-small-latest",
        "mistral/mistral-large-latest",
    ],
    "xai": ["xai/grok-2-latest"],
    "cohere": [
        "cohere/command-r-plus",
        "cohere/command-r",
    ],
    "together": ["together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo"],
    "fireworks": ["fireworks_ai/llama-v3p3-70b-instruct"],
    "openrouter": [
        "openrouter/anthropic/claude-3.5-sonnet",
        "openrouter/openai/gpt-4o-mini",
    ],
    "azure": ["azure/gpt-4o"],
    "bedrock": ["bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"],
    "vertex_ai": ["vertex_ai/gemini-1.5-pro"],
}


@dataclass(frozen=True)
class Model:
    name: str
    provider: str
    label: str
    family: str | None = None
    available: bool = True

    @property
    def display(self) -> str:
        return f"{self.provider} · {self.label}"


def ollama_base_url() -> str:
    return (
        os.environ.get("OLLAMA_API_BASE")
        or os.environ.get("OLLAMA_HOST")
        or DEFAULT_OLLAMA_BASE
    )


def fetch_ollama_models(base_url: str | None = None, timeout: float = 3.0) -> list[str]:
    base = (base_url or ollama_base_url()).rstrip("/")
    if not base.startswith("http"):
        base = f"http://{base}"
    request = urllib.request.Request(f"{base}/api/tags", headers={"User-Agent": "sadhan"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [m["name"] for m in payload.get("models", []) if m.get("name")]


def _family_from_name(name: str) -> str | None:
    base = name.split(":")[0]
    if "/" in base:
        return base.rsplit("/", 1)[-1]
    return base or None


def _split_model_id(model_id: str) -> tuple[str, str]:
    if "/" in model_id:
        provider, label = model_id.split("/", 1)
        return provider, label
    return "ollama", model_id


def _normalize_id(model_id: str) -> str:
    provider, label = _split_model_id(model_id)
    return f"{provider}/{label}"


def keys_path() -> Path:
    return Path.home() / ".sadhan" / "keys.json"


def load_keys() -> dict:
    path = keys_path()
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    for var, value in data.items():
        if isinstance(value, str) and value and not os.environ.get(var):
            os.environ[var] = value
    return data


def save_keys(keys: dict) -> None:
    path = keys_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({k: v for k, v in keys.items() if v}, indent=2), encoding="utf-8")


class LLMRegistry:
    def __init__(self) -> None:
        self._models: dict[str, Model] = {}
        self._active: str | None = None
        self._user_selected = False

    def register(self, model: Model, *, active: bool = False) -> Model:
        self._models[model.name] = model
        if active:
            self._active = model.name
        return model

    def register_id(
        self,
        model_id: str,
        *,
        label: str | None = None,
        available: bool = True,
        active: bool = False,
    ) -> Model:
        provider, name = _split_model_id(model_id)
        model = Model(
            name=model_id,
            provider=provider,
            label=label or name,
            family=_family_from_name(name),
            available=available,
        )
        return self.register(model, active=active)

    def unregister(self, name: str) -> None:
        self._models.pop(name, None)
        if self._active == name:
            self._active = next(iter(self._models), None)

    def get(self, name: str | None = None) -> Model | None:
        return self._models.get(name or self._active)

    @property
    def active(self) -> Model | None:
        if self._active in self._models:
            return self._models[self._active]
        return self.list()[0] if self._models else None

    def set_active(self, name: str, *, user: bool = True) -> Model:
        if name not in self._models:
            raise KeyError(f"unknown model: {name}")
        self._active = name
        if user:
            self._user_selected = True
        return self._models[name]

    def list(self, provider: str | None = None) -> list[Model]:
        models = list(self._models.values())
        if provider is not None:
            models = [m for m in models if m.provider == provider]
        return sorted(
            models,
            key=lambda m: (m.available is False, m.provider, m.label.lower()),
        )

    def providers(self) -> list[str]:
        return sorted({m.provider for m in self._models.values()})

    def options(self) -> list[tuple[str, str]]:
        prompts = []
        for m in self.list():
            prompt = m.display
            if not m.available:
                prompt = f"{prompt}  (need key)"
            prompts.append((prompt, m.name))
        return prompts

    def __len__(self) -> int:
        return len(self._models)

    def __contains__(self, name: object) -> bool:
        return name in self._models


registry = LLMRegistry()

_discovered = False


def discover(
    registry_obj: LLMRegistry | None = None,
    *,
    default_model: str | None = None,
    force: bool = False,
) -> LLMRegistry:
    global _discovered
    load_keys()
    reg = registry_obj or registry
    if _discovered and not force:
        return reg

    env_model = os.environ.get("SADHAN_MODEL")
    extra = [m.strip() for m in os.environ.get("SADHAN_MODELS", "").split(",") if m.strip()]

    for model_id in extra:
        if model_id not in reg:
            reg.register_id(model_id, available=True)

    for provider, model_ids in CATALOG.items():
        ready = os.environ.get(PROVIDER_ENV[provider]) is not None
        for model_id in model_ids:
            label = model_id.split("/", 1)[-1]
            reg.register_id(model_id, label=label, available=ready)

    try:
        for name in fetch_ollama_models():
            reg.register_id(f"ollama/{name}", label=name, available=True)
    except Exception:
        pass

    candidates = [default_model, env_model]
    for model_id in candidates:
        if not model_id:
            continue
        canonical = _normalize_id(model_id)
        if canonical not in reg:
            reg.register_id(canonical, available=True)
        if env_model == model_id:
            env_model = canonical
        if default_model == model_id:
            default_model = canonical

    if reg._active is None and not reg._user_selected:
        preferred = env_model or default_model
        if preferred and preferred in reg:
            reg.set_active(preferred, user=False)
        elif len(reg):
            reg.set_active(reg.list()[0].name, user=False)

    _discovered = True
    return reg