"""Regression tests for the 2026-09-04 security audit hardening batch.

Four findings from the adapters/infrastructure security review:
  1. state.json ledger carries old env values (often real keys) but was
     written with default permissions — now hardened to 0o600.
  2. Keys exported to os.environ during earlier tools' configuration were
     inherited by later tools' install subprocesses — child env is now
     stripped of credential-shaped variables.
  3. Model IDs from catalog/discovery are interpolated into .cmd launchers,
     TOML headers and shell scripts — now charset-validated at the exit.
  4. write_env sinks are the only unescaped key landing point — hostile
     keys are now rejected at the input gate instead.
"""
import os
from pathlib import Path
from typing import Any, Dict, Iterator, List

import pytest

from tokenplan_setup import adapters, flows, infrastructure


def test_state_ledger_is_owner_only(
    isolated_home: Path,
) -> None:
    """The uninstall ledger stores pre-existing env values; it must be 0600."""
    infrastructure.record_state("setx_keys", {"key": "OPENAI_API_KEY", "old": "sk-real-secret"})
    assert infrastructure.STATE_PATH.exists()
    if os.name == "posix":
        assert infrastructure.STATE_PATH.stat().st_mode & 0o777 == 0o600


class _FakeProc:
    """Minimal Popen stand-in: one output line, exit 0."""

    stdout: Iterator[str] = iter(["done"])
    returncode = 0

    def wait(self) -> int:
        return 0

    def kill(self) -> None:  # pragma: no cover - watchdog path only
        pass


def test_run_command_strips_credential_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Install subprocesses must not inherit credential variables."""
    captured: Dict[str, Any] = {}

    def fake_popen(cmd: Any, **kwargs: Any) -> _FakeProc:
        captured.update(kwargs)
        return _FakeProc()

    monkeypatch.setattr(infrastructure.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("TOKENPLAN_API_KEY", "sk-should-not-leak-either")
    monkeypatch.setenv("MYTOPSECRET", "also-stripped")

    assert infrastructure.run_command(("true",), "testing") is True
    child_env = captured["env"]
    assert "OPENAI_API_KEY" not in child_env
    assert "TOKENPLAN_API_KEY" not in child_env
    assert "MYTOPSECRET" not in child_env
    # 安装所需的基础变量原样保留
    assert "PATH" in child_env


def test_get_model_ids_rejects_hostile_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Poisoned catalog rows cannot smuggle metacharacters into configs."""
    hostile = {
        "default": "ok-model",
        "display": [
            "Good: ok-model",
            'TOML header break: evil"; [injected]',
            "Batch ampersand: x&calc",
            "Shell backtick: y`id`",
        ],
    }
    monkeypatch.setattr(adapters, "get_model_catalog", lambda _key: hostile)
    ids: List[str] = adapters.get_model_ids("personal-general")
    assert ids == ["ok-model"]


def test_key_charset_safe_gate() -> None:
    """Real Tencent keys pass; anything metacharacter-shaped is rejected."""
    assert infrastructure.key_charset_safe("sk-tp-giEabc123XYZ456")
    assert infrastructure.key_charset_safe("sk-LW4e9iLDv8c6DdbZU9fXB38UYyo7FllxB2WKawhdLMV6eEhK")
    for bad in ('sk-"quote', "sk back\\slash", "sk$HOME", "sk;rm", "sk`id`", "sk|pipe", "sk&amp", "sk%VAR%", "sk!bang"):
        assert not infrastructure.key_charset_safe(bad), bad


def test_setup_flow_rejects_metacharacter_key(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The flow exits before any config write when the key looks hostile."""
    monkeypatch.setattr(
        flows, "verify_api_key", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("must not reach network"))
    )
    args = flows.build_arg_parser().parse_args(
        ["setup", "--plan", "personal-general", "--api-key", 'sk-bad"key-1234567890']
    )
    code, result = flows._run_setup_flow(args)
    assert code == infrastructure.EXIT_USER_CANCEL
