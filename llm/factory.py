"""
Provider-agnostic chat model factory with provider registry and model catalog validation.

This enables:
1) BYOM validation before runtime by fetching provider model catalogs.
2) Plugin-based provider extension without changing core factory code.
"""
import hashlib
import importlib
import inspect
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from config import settings
from utils.mcp_transport import HTTPResult, http_get_json


CatalogFetcher = Callable[[str, int], list[str]]


def _safe_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _catalog_timeout_default() -> int:
    try:
        from config import settings

        return int(getattr(settings, "LLM_PROVIDER_CATALOG_TIMEOUT_SECONDS", 12))
    except Exception:
        return _safe_int_env("LLM_PROVIDER_CATALOG_TIMEOUT_SECONDS", 12)


def _catalog_ttl_default() -> int:
    try:
        from config import settings

        return int(getattr(settings, "LLM_PROVIDER_CATALOG_CACHE_TTL_SECONDS", 300))
    except Exception:
        return _safe_int_env("LLM_PROVIDER_CATALOG_CACHE_TTL_SECONDS", 300)


@dataclass(frozen=True)
class LLMRuntimeConfig:
    provider: str
    model: str
    api_key: str


@dataclass
class ProviderSpec:
    name: str
    module: str
    class_name: str
    aliases: tuple[str, ...] = ()
    model_param_names: tuple[str, ...] = ("model",)
    api_key_param_names: tuple[str, ...] = ("api_key",)
    max_tokens_param_names: tuple[str, ...] = ("max_tokens",)
    timeout_param_names: tuple[str, ...] = ("timeout",)
    extra_kwargs: dict[str, Any] = field(default_factory=dict)
    catalog_fetcher: Optional[CatalogFetcher] = None


_provider_registry: dict[str, ProviderSpec] = {}
_provider_aliases: dict[str, str] = {}
_registry_lock = threading.Lock()
_plugins_loaded = False

_catalog_cache: dict[str, tuple[float, list[str]]] = {}
_catalog_lock = threading.Lock()


def _normalize_model_name(model: str) -> str:
    return (model or "").strip().lower()


def _models_match(requested_model: str, available_model: str) -> bool:
    req = _normalize_model_name(requested_model)
    avail = _normalize_model_name(available_model)
    if req == avail:
        return True
    # Gemini often returns models/<name>; accept short/long forms interchangeably.
    if avail.endswith(f"/{req}"):
        return True
    if req.endswith(f"/{avail}"):
        return True
    return False


def _raise_for_status(response: HTTPResult, provider: str):
    if response.ok:
        return
    body = (response.text or "")[:500]
    raise RuntimeError(
        f"{provider} model catalog request failed ({response.status_code}): {body}"
    )


def _extract_model_ids(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if isinstance(data, list):
        ids = []
        for item in data:
            if isinstance(item, dict):
                candidate = item.get("id") or item.get("name")
                if isinstance(candidate, str) and candidate.strip():
                    ids.append(candidate.strip())
        return ids
    return []


def _catalog_http_get_json(
    url: str,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout_seconds: int = 12,
) -> HTTPResult:
    return http_get_json(
        url,
        headers=headers,
        params=params,
        timeout_seconds=timeout_seconds,
        allow_fallback=bool(settings.MCP_FAIL_OPEN and not settings.MCP_AGENT_STRICT_MODE),
        require_mcp=bool(settings.MCP_AGENT_STRICT_MODE),
    )


def _fetch_groq_models(api_key: str, timeout_seconds: int) -> list[str]:
    response = _catalog_http_get_json(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=timeout_seconds,
    )
    _raise_for_status(response, "groq")
    payload = response.json_data if isinstance(response.json_data, dict) else {}
    return _extract_model_ids(payload)


def _fetch_openai_models(api_key: str, timeout_seconds: int) -> list[str]:
    response = _catalog_http_get_json(
        "https://api.openai.com/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout_seconds=timeout_seconds,
    )
    _raise_for_status(response, "openai")
    payload = response.json_data if isinstance(response.json_data, dict) else {}
    return _extract_model_ids(payload)


def _fetch_anthropic_models(api_key: str, timeout_seconds: int) -> list[str]:
    response = _catalog_http_get_json(
        "https://api.anthropic.com/v1/models",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        timeout_seconds=timeout_seconds,
    )
    _raise_for_status(response, "anthropic")
    payload = response.json_data if isinstance(response.json_data, dict) else {}
    return _extract_model_ids(payload)


def _fetch_gemini_models(api_key: str, timeout_seconds: int) -> list[str]:
    response = _catalog_http_get_json(
        "https://generativelanguage.googleapis.com/v1beta/models",
        params={"key": api_key},
        timeout_seconds=timeout_seconds,
    )
    _raise_for_status(response, "gemini")
    payload = response.json_data if isinstance(response.json_data, dict) else {}
    models = payload.get("models")
    if not isinstance(models, list):
        return []

    result: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods") or []
        if isinstance(methods, list) and "generateContent" not in methods:
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        full_name = name.strip()
        result.append(full_name)
        if "/" in full_name:
            result.append(full_name.split("/", 1)[1])
    return result


def _register_builtin_providers() -> None:
    if "groq" in _provider_registry:
        return

    register_provider(
        ProviderSpec(
            name="groq",
            module="langchain_groq",
            class_name="ChatGroq",
            aliases=("groq",),
            model_param_names=("model",),
            api_key_param_names=("api_key", "groq_api_key"),
            max_tokens_param_names=("max_tokens",),
            timeout_param_names=("timeout",),
            catalog_fetcher=_fetch_groq_models,
        )
    )
    register_provider(
        ProviderSpec(
            name="openai",
            module="langchain_openai",
            class_name="ChatOpenAI",
            aliases=("openai",),
            model_param_names=("model",),
            api_key_param_names=("api_key", "openai_api_key"),
            max_tokens_param_names=("max_tokens",),
            timeout_param_names=("timeout",),
            catalog_fetcher=_fetch_openai_models,
        )
    )
    register_provider(
        ProviderSpec(
            name="anthropic",
            module="langchain_anthropic",
            class_name="ChatAnthropic",
            aliases=("anthropic",),
            model_param_names=("model", "model_name"),
            api_key_param_names=("api_key", "anthropic_api_key"),
            max_tokens_param_names=("max_tokens", "max_tokens_to_sample"),
            timeout_param_names=("timeout",),
            extra_kwargs={"stop": None},
            catalog_fetcher=_fetch_anthropic_models,
        )
    )
    register_provider(
        ProviderSpec(
            name="gemini",
            module="langchain_google_genai",
            class_name="ChatGoogleGenerativeAI",
            aliases=("gemini", "google", "google-genai"),
            model_param_names=("model",),
            api_key_param_names=("api_key", "google_api_key"),
            max_tokens_param_names=("max_tokens", "max_output_tokens"),
            timeout_param_names=(),
            catalog_fetcher=_fetch_gemini_models,
        )
    )


def _load_plugins_once() -> None:
    global _plugins_loaded
    with _registry_lock:
        if _plugins_loaded:
            return

        raw = (os.getenv("LLM_PROVIDER_PLUGIN_MODULES") or "").strip()
        if not raw:
            try:
                from config import settings

                raw = (settings.LLM_PROVIDER_PLUGIN_MODULES or "").strip()
            except Exception:
                raw = ""
        plugin_modules = [m.strip() for m in raw.split(",") if m.strip()]
        for module_name in plugin_modules:
            importlib.import_module(module_name)

        _plugins_loaded = True


def _ensure_registry_ready() -> None:
    _register_builtin_providers()
    _load_plugins_once()


def register_provider(spec: ProviderSpec) -> None:
    """
    Register a provider implementation.

    Plugin modules should import this function and call it at import time.
    """
    normalized_name = (spec.name or "").strip().lower()
    if not normalized_name:
        raise ValueError("Provider name cannot be empty")

    aliases = {normalized_name}
    aliases.update((alias or "").strip().lower() for alias in spec.aliases if alias)

    with _registry_lock:
        _provider_registry[normalized_name] = ProviderSpec(
            name=normalized_name,
            module=spec.module,
            class_name=spec.class_name,
            aliases=tuple(sorted(aliases)),
            model_param_names=spec.model_param_names,
            api_key_param_names=spec.api_key_param_names,
            max_tokens_param_names=spec.max_tokens_param_names,
            timeout_param_names=spec.timeout_param_names,
            extra_kwargs=dict(spec.extra_kwargs or {}),
            catalog_fetcher=spec.catalog_fetcher,
        )
        for alias in aliases:
            _provider_aliases[alias] = normalized_name


def get_registered_providers() -> list[str]:
    _ensure_registry_ready()
    return sorted(_provider_registry.keys())


def normalize_provider(provider: str) -> str:
    _ensure_registry_ready()
    normalized = (provider or "").strip().lower()
    resolved = _provider_aliases.get(normalized)
    if not resolved:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return resolved


def _instantiate(cls, **kwargs):
    """Instantiate class with only supported kwargs for compatibility across package versions."""
    try:
        sig = inspect.signature(cls.__init__)
        has_var_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD
            for param in sig.parameters.values()
        )
        if has_var_kwargs:
            supported = kwargs
        else:
            supported = {k: v for k, v in kwargs.items() if k in sig.parameters}
    except Exception:
        supported = kwargs
    return cls(**supported)


def create_chat_model(
    runtime: LLMRuntimeConfig,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
):
    """
    Create provider-specific chat model instance from unified runtime config.
    """
    provider = normalize_provider(runtime.provider)
    spec = _provider_registry[provider]

    cls = getattr(importlib.import_module(spec.module), spec.class_name)
    kwargs: dict[str, Any] = {"temperature": temperature}
    for param_name in spec.model_param_names:
        kwargs[param_name] = runtime.model
    for param_name in spec.api_key_param_names:
        kwargs[param_name] = runtime.api_key
    for param_name in spec.max_tokens_param_names:
        kwargs[param_name] = max_tokens
    for param_name in spec.timeout_param_names:
        kwargs[param_name] = timeout_seconds
    kwargs.update(spec.extra_kwargs)

    return _instantiate(cls, **kwargs)


def _catalog_cache_key(provider: str, api_key: str) -> str:
    key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"{provider}:{key_hash}"


def fetch_provider_models(
    provider: str,
    api_key: str,
    timeout_seconds: Optional[int] = None,
    force_refresh: bool = False,
) -> list[str]:
    """Fetch available model IDs from provider catalog APIs."""
    normalized_provider = normalize_provider(provider)
    if not api_key or not api_key.strip():
        raise ValueError("API key is required to fetch provider model catalog")

    spec = _provider_registry[normalized_provider]
    if spec.catalog_fetcher is None:
        raise ValueError(f"Provider {normalized_provider} does not expose a model catalog fetcher")

    cache_key = _catalog_cache_key(normalized_provider, api_key)
    now = time.time()
    timeout = int(timeout_seconds or _catalog_timeout_default())
    ttl_seconds = _catalog_ttl_default()

    with _catalog_lock:
        if not force_refresh and cache_key in _catalog_cache:
            cached_at, cached_models = _catalog_cache[cache_key]
            if now - cached_at <= ttl_seconds:
                return list(cached_models)

    models = spec.catalog_fetcher(api_key, timeout)
    cleaned = sorted({model.strip() for model in models if isinstance(model, str) and model.strip()})
    if not cleaned:
        raise RuntimeError(f"{normalized_provider} model catalog returned no models")

    with _catalog_lock:
        _catalog_cache[cache_key] = (now, cleaned)

    return cleaned


def validate_model_name(
    provider: str,
    model_name: str,
    api_key: str,
    timeout_seconds: Optional[int] = None,
) -> tuple[bool, list[str], list[str]]:
    """
    Validate a model name against the provider's live model catalog.

    Returns:
      (is_valid, catalog_models, suggestions)
    """
    requested = (model_name or "").strip()
    if not requested:
        raise ValueError("Model name cannot be empty")

    catalog_models = fetch_provider_models(
        provider=provider,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )

    for available in catalog_models:
        if _models_match(requested, available):
            return True, catalog_models, []

    requested_lower = requested.lower()
    suggestions = [
        model for model in catalog_models
        if requested_lower in model.lower() or model.lower().endswith(f"/{requested_lower}")
    ][:20]

    return False, catalog_models, suggestions
