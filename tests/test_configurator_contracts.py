"""Parameterized filesystem contracts for all twelve configurators."""
import json
from pathlib import Path

import pytest

from tokenplan_setup import adapters, domain

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("tool_key", tuple(adapters.CONFIGURATOR_REGISTRY))
def test_configurator_writes_detectable_tokenhub_config(
    tool_key: str,
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapters, "_REMOTE_CATALOG", None)
    monkeypatch.setattr(adapters, "patch_hermes_model_routing", lambda: None)
    monkeypatch.setattr(adapters, "install_codebuddy_shell_env", lambda *_: None)
    monkeypatch.setattr(adapters, "install_codex_shell_env", lambda *_: None)
    monkeypatch.setattr(adapters, "install_claude_tokenhub_path", lambda: None)
    monkeypatch.setattr(
        adapters.shutil,
        "which",
        lambda command: None if command == "pgrep" else f"/mock/{command}",
    )

    relative_path, marker, _legacy_marker = adapters.CONFIG_SIGNATURES[tool_key]
    config_path = isolated_home / relative_path
    if tool_key == "opencode":
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_bytes((FIXTURES / "legacy-opencode.json").read_bytes())

    plan = domain.PLAN_BY_KEY["personal-hy"]
    adapters.CONFIGURATOR_REGISTRY[tool_key](
        plan.base_url,
        "sk-pytest-isolated-1234567890",
        plan,
    )

    assert config_path.is_file()
    first_write = config_path.read_bytes()
    assert marker in first_write.decode("utf-8")
    assert adapters.probe_config(domain.TOOL_BY_KEY[tool_key]) is True

    adapters.CONFIGURATOR_REGISTRY[tool_key](
        plan.base_url,
        "sk-pytest-isolated-1234567890",
        plan,
    )
    assert config_path.read_bytes() == first_write


def test_legacy_provider_is_migrated_without_losing_user_provider(
    isolated_home: Path,
) -> None:
    path = isolated_home / ".config" / "opencode" / "opencode.json"
    path.parent.mkdir(parents=True)
    path.write_bytes((FIXTURES / "legacy-opencode.json").read_bytes())
    plan = domain.PLAN_BY_KEY["personal-hy"]

    adapters.configure_opencode(plan.base_url, "sk-pytest-1234567890", plan)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert "tokenplan" not in data["provider"]
    assert "tokenhub" in data["provider"]
    assert data["provider"]["openai"]["name"] == "User provider"


def test_hermes_patch_rewrites_routing_inside_isolated_home(
    isolated_home: Path,
) -> None:
    """The Hermes patch must resolve through HOME, never the real user home."""
    target = isolated_home / ".hermes" / "hermes-agent" / "hermes_cli" / "model_switch.py"
    target.parent.mkdir(parents=True)
    target.write_text(
        "def resolve(entry, name, matches):\n"
        '            slug = f"custom:{name}"\n'
        "            if slug in matches:\n"
        "                return slug\n"
    )

    adapters.patch_hermes_model_routing()

    patched = target.read_text()
    assert "custom_provider_slug(name" in patched
    assert 'f"custom:{name}"' not in patched
    assert (isolated_home / ".tokenplan-backups").is_dir()


def test_hermes_patch_skips_when_not_installed(isolated_home: Path) -> None:
    """A missing Hermes install must be skipped, not crash the configurator."""
    adapters.patch_hermes_model_routing()

    assert not (isolated_home / ".hermes").exists()


def test_corrupt_json_is_replaced_inside_isolated_home(isolated_home: Path) -> None:
    path = isolated_home / ".zcode" / "v2" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_bytes((FIXTURES / "corrupt.json").read_bytes())
    plan = domain.PLAN_BY_KEY["personal-hy"]

    adapters.configure_zcode(plan.base_url, "sk-pytest-1234567890", plan)

    assert json.loads(path.read_text(encoding="utf-8"))["provider"]
