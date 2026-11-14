from typing import Any

_DISABLED_PROJECT_PROVIDERS_KEY = "disabled_project_providers"
_DISABLED_CLI_PROVIDERS_KEY = "disabled_cli_providers"


def _normalize_disabled_set(provider_settings: dict[str, Any] | None, storage_key: str) -> set[str]:
    if not provider_settings:
        return set()
    raw = provider_settings.get(storage_key, [])
    if not isinstance(raw, (list, tuple, set)):
        return set()
    return {str(item).strip() for item in raw if str(item).strip()}


def is_project_provider_enabled(provider_key: str, provider_settings: dict[str, Any] | None) -> bool:
    """Return True unless the project provider has been explicitly disabled."""
    return provider_key.strip() not in _normalize_disabled_set(provider_settings, _DISABLED_PROJECT_PROVIDERS_KEY)


def is_cli_provider_enabled(provider_key: str, provider_settings: dict[str, Any] | None) -> bool:
    """Return True unless the CLI model provider has been explicitly disabled."""
    return provider_key.strip() not in _normalize_disabled_set(provider_settings, _DISABLED_CLI_PROVIDERS_KEY)


def set_project_provider_enabled(
    provider_settings: dict[str, Any] | None,
    provider_key: str,
    enabled: bool,
) -> dict[str, Any]:
    """Return an updated copy of provider_settings toggling a project provider."""
    updated = dict(provider_settings or {})
    disabled = _normalize_disabled_set(updated, _DISABLED_PROJECT_PROVIDERS_KEY)
    key = provider_key.strip()
    if enabled:
        disabled.discard(key)
    else:
        disabled.add(key)
    updated[_DISABLED_PROJECT_PROVIDERS_KEY] = sorted(disabled)
    return updated


def set_cli_provider_enabled(
    provider_settings: dict[str, Any] | None,
    provider_key: str,
    enabled: bool,
) -> dict[str, Any]:
    """Return an updated copy of provider_settings toggling a CLI model provider."""
    updated = dict(provider_settings or {})
    disabled = _normalize_disabled_set(updated, _DISABLED_CLI_PROVIDERS_KEY)
    key = provider_key.strip()
    if enabled:
        disabled.discard(key)
    else:
        disabled.add(key)
    updated[_DISABLED_CLI_PROVIDERS_KEY] = sorted(disabled)
    return updated


def get_disabled_cli_providers(provider_settings: dict[str, Any] | None) -> set[str]:
    return _normalize_disabled_set(provider_settings, _DISABLED_CLI_PROVIDERS_KEY)


def get_disabled_project_providers(provider_settings: dict[str, Any] | None) -> set[str]:
    return _normalize_disabled_set(provider_settings, _DISABLED_PROJECT_PROVIDERS_KEY)
