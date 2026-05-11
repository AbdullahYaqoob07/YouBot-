# LLM Provider Plugin Guide

This project now supports plugin-based providers without changing core code.

## 1) Create a plugin module

Example file: `custom_llm_plugins/my_provider.py`

```python
from llm.factory import ProviderSpec, register_provider


def _fetch_my_provider_models(api_key: str, timeout_seconds: int) -> list[str]:
    # Call provider API here and return model IDs as strings.
    return ["my-model-1", "my-model-2"]


register_provider(
    ProviderSpec(
        name="myprovider",
        module="langchain_openai",      # Example adapter module
        class_name="ChatOpenAI",        # Example adapter class
        aliases=("my-provider",),
        model_param_names=("model",),
        api_key_param_names=("api_key",),
        max_tokens_param_names=("max_tokens",),
        timeout_param_names=("timeout",),
        catalog_fetcher=_fetch_my_provider_models,
    )
)
```

## 2) Register plugin module in environment

Set in `.env`:

```env
LLM_PROVIDER_PLUGIN_MODULES=custom_llm_plugins.my_provider
```

You can load multiple modules:

```env
LLM_PROVIDER_PLUGIN_MODULES=custom_llm_plugins.my_provider,custom_llm_plugins.other_provider
```

## 3) Restart API server

After restart, plugin providers are recognized by:
- Provider normalization and runtime model creation.
- Model catalog endpoint: `POST /admin/llm/providers/{provider}/models`
- Workspace config validation: `POST /admin/workspaces/{workspace_id}/llm-config`

## 4) Model validation behavior

When `LLM_MODEL_VALIDATION_REQUIRED=True`, workspace config save will fail if:
- provider is unknown, or
- model is not in provider catalog.

Catalog fetch settings:

```env
LLM_PROVIDER_CATALOG_TIMEOUT_SECONDS=12
LLM_PROVIDER_CATALOG_CACHE_TTL_SECONDS=300
```
