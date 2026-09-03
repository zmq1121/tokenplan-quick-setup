"""Behavioural tests for the failure and fallback branches of risky operations.

These paths (remote catalog integrity, postpaid discovery, third-party script
execution, install failures, Windows environment writes) are the ones that
touch the network, the user's shell or the registry, so they are asserted here
against explicit stubs rather than left to the interactive flow.
"""
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

import pytest

from tokenplan_setup import adapters, domain, flows, infrastructure

CATALOG_BODY = json.dumps({
    "latest_version": "9.9.9",
    "plans": {"personal-hy": {"default": "remote-model", "display": ["remote-model"]}},
}).encode("utf-8")


def _catalog_responses(
    body: bytes,
    digest: str,
    catalog_status: int = 0,
    digest_status: int = 0,
) -> Dict[str, Tuple[int, bytes]]:
    return {
        adapters.REMOTE_CATALOG_URL: (catalog_status, body),
        adapters.REMOTE_CATALOG_SHA256_URL: (
            digest_status,
            f"{digest}  models.json\n".encode(),
        ),
    }


@pytest.fixture
def clean_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset remote catalog globals so each case starts from the built-in state."""
    monkeypatch.setattr(adapters, "_REMOTE_CATALOG", None)
    monkeypatch.setattr(adapters, "_REMOTE_LATEST_VERSION", None)


# ── 远程模型目录:完整性三态与回退 ──────────────────────────────────────


def test_remote_catalog_is_adopted_when_digest_matches(
    clean_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    digest = hashlib.sha256(CATALOG_BODY).hexdigest()
    responses = _catalog_responses(CATALOG_BODY, digest)
    monkeypatch.setattr(
        adapters, "_http_request", lambda url, **_kwargs: responses[url]
    )

    adapters.refresh_remote_catalog()

    assert adapters.remote_catalog_size() == 1
    assert adapters.get_model_catalog("personal-hy")["default"] == "remote-model"


def test_digest_mismatch_falls_back_to_builtin_catalog(
    clean_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A wrong digest must never be trusted, even though the payload parses."""
    responses = _catalog_responses(CATALOG_BODY, "0" * 64)
    monkeypatch.setattr(
        adapters, "_http_request", lambda url, **_kwargs: responses[url]
    )

    adapters.refresh_remote_catalog()

    assert adapters.remote_catalog_size() == 0
    assert "SHA256 不匹配" in capsys.readouterr().out
    assert adapters.get_model_catalog("personal-hy")["default"] != "remote-model"


def test_unavailable_digest_blocks_adoption(
    clean_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fail closed: content that cannot be proven intact is not used."""
    digest = hashlib.sha256(CATALOG_BODY).hexdigest()
    responses = _catalog_responses(CATALOG_BODY, digest, digest_status=404)
    monkeypatch.setattr(
        adapters, "_http_request", lambda url, **_kwargs: responses[url]
    )

    adapters.refresh_remote_catalog()

    assert adapters.remote_catalog_size() == 0
    assert "完整性无法校验" in capsys.readouterr().out


def test_malformed_payload_after_valid_digest_is_reported(
    clean_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hash-valid but unparseable means the upstream artifact itself is broken."""
    body = b"{not json"
    responses = _catalog_responses(body, hashlib.sha256(body).hexdigest())
    monkeypatch.setattr(
        adapters, "_http_request", lambda url, **_kwargs: responses[url]
    )

    adapters.refresh_remote_catalog()

    assert adapters.remote_catalog_size() == 0
    assert "解析失败" in capsys.readouterr().out


def test_offline_catalog_fetch_is_silent_and_harmless(
    clean_catalog: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(_url: str, **_kwargs: object) -> Tuple[int, bytes]:
        raise RuntimeError("Network is unreachable")

    monkeypatch.setattr(adapters, "_http_request", _raise)

    adapters.refresh_remote_catalog()

    assert adapters.remote_catalog_size() == 0


# ── 后付费模型发现 ────────────────────────────────────────────────────


def test_postpaid_discovery_returns_ids_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapters, "_POSTPAID_DISCOVERED", None)
    payload = json.dumps({"data": [{"id": "model-a"}, {"id": "model-b"}]}).encode()
    monkeypatch.setattr(
        adapters, "_http_request", lambda *_a, **_k: (0, payload)
    )

    assert adapters.discover_postpaid_models("https://x/v1", "sk-x") == [
        "model-a",
        "model-b",
    ]
    assert adapters.postpaid_discovered_count() == 2


@pytest.mark.parametrize(
    ("label", "response", "expected_output"),
    [
        ("http-error", (401, b'{"error": {"message": "bad key"}}'), "bad key"),
        ("malformed", (0, b"<html>not json</html>"), "解析失败"),
    ],
)
def test_postpaid_discovery_failures_return_none(
    label: str,
    response: Tuple[int, bytes],
    expected_output: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Discovery doubles as key verification, so failures must not be swallowed."""
    monkeypatch.setattr(adapters, "_POSTPAID_DISCOVERED", None)
    monkeypatch.setattr(adapters, "_http_request", lambda *_a, **_k: response)

    assert adapters.discover_postpaid_models("https://x/v1", "sk-x") is None
    assert expected_output in capsys.readouterr().out
    assert adapters.postpaid_discovered_count() == 0


def test_postpaid_discovery_reports_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(adapters, "_POSTPAID_DISCOVERED", None)

    def _raise(*_a: object, **_k: object) -> Tuple[int, bytes]:
        raise RuntimeError("timed out")

    monkeypatch.setattr(adapters, "_http_request", _raise)

    assert adapters.discover_postpaid_models("https://x/v1", "sk-x") is None
    assert "连接失败" in capsys.readouterr().out


# ── 远程第三方脚本:fail-closed 与执行留痕 ─────────────────────────────


def test_remote_script_download_failure_does_not_execute(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        infrastructure, "_http_request", lambda *_a, **_k: (503, b"upstream down")
    )
    monkeypatch.setattr(
        infrastructure,
        "run_command",
        lambda *_a: pytest.fail("must not execute after a failed download"),
    )

    assert infrastructure.run_remote_script("https://x/i.sh", (), "Demo") is False
    assert "下载失败" in capsys.readouterr().out


def test_remote_script_requires_confirmation(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-interactive or declined confirmation must abort, never auto-run."""
    monkeypatch.setattr(
        infrastructure, "_http_request", lambda *_a, **_k: (0, b"echo hi\n")
    )
    monkeypatch.setattr(infrastructure, "_ASSUME_YES", False)
    monkeypatch.setattr(infrastructure, "ask", lambda _prompt: "n")
    monkeypatch.setattr(
        infrastructure,
        "run_command",
        lambda *_a: pytest.fail("declined script must not execute"),
    )

    assert infrastructure.run_remote_script("https://x/i.sh", (), "Demo") is False
    assert "未获确认" in capsys.readouterr().out
    assert not infrastructure.STATE_PATH.exists()


def test_executed_remote_script_is_recorded_for_audit(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Upstream publishes no fixed hash, so what ran must stay auditable."""
    body = b"echo installing\n"
    executed: List[Tuple[str, ...]] = []
    monkeypatch.setattr(
        infrastructure, "_http_request", lambda *_a, **_k: (0, body)
    )
    monkeypatch.setattr(infrastructure, "_ASSUME_YES", True)
    monkeypatch.setattr(
        infrastructure,
        "run_command",
        lambda command, _message: executed.append(command) is None,
    )

    assert infrastructure.run_remote_script(
        "https://x/i.sh", ("--yes",), "Demo"
    ) is True

    assert executed and executed[0][0] == "bash"
    assert executed[0][-1] == "--yes"
    ledger = json.loads(infrastructure.STATE_PATH.read_text())["remote_scripts"]
    assert ledger == [{
        "tool": "Demo",
        "url": "https://x/i.sh",
        "sha256": hashlib.sha256(body).hexdigest(),
        "bytes": len(body),
    }]
    # 脚本本身必须在执行后清理,不留可写的临时载荷。
    assert not list(Path(infrastructure.tempfile.gettempdir()).glob(
        "*-tokenplan-install.sh"
    ))


# ── 安装命令失败 ──────────────────────────────────────────────────────


def test_failing_install_command_returns_false(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert infrastructure.run_command(
        ("python3", "-c", "import sys; sys.exit(7)"), "失败用例"
    ) is False
    assert "失败" in capsys.readouterr().out


def test_unlaunchable_install_command_is_reported(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A missing executable must degrade to a warning, not an unhandled traceback."""
    assert infrastructure.run_command(
        ("tokenplan-nonexistent-binary",), "缺失用例"
    ) is False
    assert "失败" in capsys.readouterr().out


@pytest.mark.parametrize(
    "tool_key",
    [tool.key for tool in domain.TOOLS if adapters.should_manual_download(tool)],
)
def test_desktop_tool_never_triggers_an_install_command(
    tool_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Desktop tools are user-downloaded; install_tool reports 'nothing to run'."""
    monkeypatch.setattr(
        adapters,
        "run_command",
        lambda *_a: pytest.fail("desktop tools must never be auto-installed"),
    )

    assert adapters.install_tool(domain.TOOL_BY_KEY[tool_key]) is True


def test_npm_install_is_pinned_ignores_scripts_and_uses_private_cache(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The install command is the supply-chain boundary; assert its exact shape."""
    tool = domain.TOOL_BY_KEY["codex"]
    seen: List[Tuple[str, ...]] = []
    monkeypatch.setattr(
        adapters,
        "run_command",
        lambda command, _message: seen.append(command) is None,
    )

    assert adapters.install_tool(tool) is True

    command = seen[0]
    assert command[:4] == ("npm", "install", "-g", "--ignore-scripts")
    assert command[4] == domain.verified_npm_spec("@openai/codex")
    assert "@latest" not in command[4]
    assert command[-2] == "--cache"
    # 私有 cache 必须落在隔离 HOME 内,不污染用户全局 npm 缓存。
    assert Path(command[-1]) == isolated_home / ".tokenplan-npm-cache"


# ── Windows 环境变量写入与还原台账 ────────────────────────────────────


def test_windows_env_write_records_previous_value(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """setx writes must be journalled with the old value so uninstall can revert."""
    monkeypatch.setattr(adapters, "IS_WINDOWS", True)
    monkeypatch.setenv("CODEBUDDY_API_KEY", "previous-value")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("OPENAI_BASE_URL", "")
    calls: List[List[str]] = []

    def fake_run(command: List[str], **_kwargs: object) -> object:
        calls.append(command)
        if command[:2] == ["reg", "query"]:
            key = command[-1]
            return subprocess.CompletedProcess(
                command, 0, f"    {key}    REG_SZ    previous-{key}\n", ""
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(adapters.subprocess, "run", fake_run)

    adapters.install_codebuddy_shell_env("sk-new", "https://api.example/v1")

    setx_calls = [c for c in calls if c[0] == "setx"]
    assert [c[1] for c in setx_calls] == [
        "CODEBUDDY_API_KEY",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
    ]
    journal = json.loads(infrastructure.STATE_PATH.read_text())["setx_keys"]
    assert {entry["key"]: entry["old"] for entry in journal} == {
        "CODEBUDDY_API_KEY": "previous-CODEBUDDY_API_KEY",
        "OPENAI_API_KEY": "previous-OPENAI_API_KEY",
        "OPENAI_BASE_URL": "previous-OPENAI_BASE_URL",
    }


def test_absent_windows_env_is_journalled_as_none(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key that did not exist must be journalled as None so uninstall deletes it."""
    monkeypatch.setattr(adapters, "IS_WINDOWS", True)
    monkeypatch.setenv("CODEBUDDY_API_KEY", "")

    monkeypatch.setattr(
        adapters.subprocess,
        "run",
        lambda command, **_k: subprocess.CompletedProcess(command, 1, "", "not found"),
    )

    adapters.install_codebuddy_shell_env("sk-new", "https://api.example/v1")

    journal = json.loads(infrastructure.STATE_PATH.read_text())["setx_keys"]
    assert all(entry["old"] is None for entry in journal)


def test_windows_env_query_survives_missing_reg_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*_a: object, **_k: object) -> object:
        raise OSError("reg not found")

    monkeypatch.setattr(adapters.subprocess, "run", _raise)

    assert adapters.query_windows_user_env("ANY_KEY") is None


# ── 卸载:如实披露不可回滚的副作用 ────────────────────────────────────


@pytest.mark.parametrize("has_revertible_record", [False, True])
def test_uninstall_discloses_remote_scripts_on_both_exit_paths(
    has_revertible_record: bool,
    isolated_home: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Whether or not anything is revertible, executed scripts must be disclosed."""
    infrastructure.record_state("remote_scripts", {
        "tool": "Hermes",
        "url": "https://example/install.sh",
        "sha256": "a" * 64,
        "bytes": 12,
    })
    if has_revertible_record:
        generated = isolated_home / ".demo" / "generated.json"
        generated.parent.mkdir(parents=True)
        generated.write_text("{}")
        infrastructure.record_state("files_written", str(generated))

    result: Dict[str, object] = {}
    code = flows.run_uninstall(True, result=result)

    output = capsys.readouterr().out
    assert code == infrastructure.EXIT_OK
    assert "无法自动回滚" in output
    assert "https://example/install.sh" in output
    assert "a" * 64 in output
    assert result["remote_scripts"] == [{
        "tool": "Hermes",
        "url": "https://example/install.sh",
        "sha256": "a" * 64,
        "bytes": 12,
    }]


def test_uninstall_json_shape_is_stable_without_any_records(
    isolated_home: Path,
) -> None:
    result: Dict[str, object] = {}

    assert flows.run_uninstall(True, result=result) == infrastructure.EXIT_OK
    assert set(result) == {"operations", "failures", "remote_scripts"}
    assert result["remote_scripts"] == []
