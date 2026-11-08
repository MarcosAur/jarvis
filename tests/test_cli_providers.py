from pipeline.adapters.cli_providers import (
    AgyCliProvider,
    ClaudeCliProvider,
    CodexCliProvider,
    GeminiCliProvider,
)
from pipeline.domain.ports.cli_provider import CliModelProvider


def test_cli_providers_conform_to_protocol():
    providers = [
        AgyCliProvider(),
        GeminiCliProvider(),
        ClaudeCliProvider(),
        CodexCliProvider(),
    ]
    for p in providers:
        assert isinstance(p, CliModelProvider)
        assert p.provider_key != ""
        assert p.display_name != ""
        assert p.binary_name != ""


def test_installed_clis_detected_on_system():
    # All 4 binaries are in $PATH on this environment
    agy = AgyCliProvider()
    assert agy.is_installed() is True

    gemini = GeminiCliProvider()
    assert gemini.is_installed() is True

    claude = ClaudeCliProvider()
    assert claude.is_installed() is True

    codex = CodexCliProvider()
    assert codex.is_installed() is True


def test_agy_list_models():
    agy = AgyCliProvider()
    models = agy.list_models()
    assert len(models) > 0
    # At least gemini-4-argon or flash should be present
    model_ids = [m.id for m in models]
    assert any("gemini" in m_id or "claude" in m_id for m_id in model_ids)


def test_fallback_models_when_not_installed():
    agy = AgyCliProvider()
    agy.binary_name = "non_existent_binary_xyz_123"
    assert agy.is_installed() is False
    models = agy.list_models()
    assert len(models) > 0
    assert any("gemini" in m.id for m in models)
