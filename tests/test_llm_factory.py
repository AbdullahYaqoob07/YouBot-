import pytest

from llm.factory import (
    ProviderSpec,
    get_registered_providers,
    normalize_provider,
    register_provider,
    validate_model_name,
)


def test_normalize_provider_valid_values():
    assert normalize_provider("groq") == "groq"
    assert normalize_provider(" OPENAI ") == "openai"
    assert normalize_provider("Anthropic") == "anthropic"
    assert normalize_provider("gemini") == "gemini"


def test_normalize_provider_invalid_value():
    with pytest.raises(ValueError):
        normalize_provider("provider-does-not-exist")


def test_register_provider_with_alias_support():
    register_provider(
        ProviderSpec(
            name="acme_test_provider",
            module="builtins",
            class_name="object",
            aliases=("acme", "acme-ai"),
            catalog_fetcher=lambda _api_key, _timeout: ["acme-large", "acme-small"],
        )
    )

    assert normalize_provider("ACME") == "acme_test_provider"
    assert "acme_test_provider" in get_registered_providers()


def test_validate_model_name_with_catalog():
    register_provider(
        ProviderSpec(
            name="acme_catalog_provider",
            module="builtins",
            class_name="object",
            aliases=("acme-catalog",),
            catalog_fetcher=lambda _api_key, _timeout: ["acme-chat-1", "acme-chat-2"],
        )
    )

    valid, catalog, suggestions = validate_model_name(
        provider="acme-catalog",
        model_name="acme-chat-1",
        api_key="test-key-123456",
    )
    assert valid is True
    assert "acme-chat-1" in catalog
    assert suggestions == []

    invalid, catalog2, suggestions2 = validate_model_name(
        provider="acme-catalog",
        model_name="missing-model",
        api_key="test-key-123456",
    )
    assert invalid is False
    assert len(catalog2) == 2
    assert isinstance(suggestions2, list)


def test_validate_model_name_accepts_short_form_against_prefixed_catalog():
    register_provider(
        ProviderSpec(
            name="gemini_style_test_provider",
            module="builtins",
            class_name="object",
            aliases=("gemini-style",),
            catalog_fetcher=lambda _api_key, _timeout: ["models/gemini-2.0-flash"],
        )
    )

    valid, _, _ = validate_model_name(
        provider="gemini-style",
        model_name="gemini-2.0-flash",
        api_key="test-key-abcdef",
    )
    assert valid is True
