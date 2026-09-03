"""Installation detection contracts for every tool in the registry.

The registry is the source of truth for what "installed" means. These tests
exercise every configured tool so any future addition inherits the same
protections (name-collision resistance, symlink resolution, .cmd wrapper
introspection, desktop-app path probing).
"""
from dataclasses import replace
from pathlib import Path
from typing import Tuple

import pytest

from tokenplan_setup import adapters, domain

# (tool key, resolved path fragment written into the symlink target)
NPM_POSIX_FIXTURES: Tuple[Tuple[str, str], ...] = (
    ("codebuddy", "../lib/node_modules/@tencent-ai/codebuddy-code/bin/codebuddy"),
    ("claude-code", "../lib/node_modules/@anthropic-ai/claude-code/cli.mjs"),
    ("opencode", "../lib/node_modules/opencode-ai/bin/opencode"),
    ("openclaw", "../lib/node_modules/openclaw/openclaw.mjs"),
    ("dsh", "../lib/node_modules/@deepseek-ai/dsh/lib/bin.js"),
    ("codex", "../lib/node_modules/@openai/codex/bin/codex.js"),
    ("kimi", "../lib/node_modules/@moonshot-ai/kimi-code/dist/main.mjs"),
    ("grok", "../lib/node_modules/@xai-official/grok/bin/grok"),
    ("pi", "../lib/node_modules/@earendil-works/pi-coding-agent/dist/bundle/cli.js"),
)

# (tool key, textual snippet a Windows .cmd wrapper would contain)
NPM_WINDOWS_FIXTURES: Tuple[Tuple[str, str], ...] = (
    ("codebuddy", '@node "%~dp0\\node_modules\\@tencent-ai\\codebuddy-code\\bin\\codebuddy"\n'),
    ("claude-code", '@node "%~dp0\\node_modules\\@anthropic-ai\\claude-code\\cli.mjs"\n'),
    ("opencode", '@node "%~dp0\\node_modules\\opencode-ai\\bin\\opencode"\n'),
    ("openclaw", '@node "%~dp0\\node_modules\\openclaw\\openclaw.mjs"\n'),
    ("dsh", '@node "%~dp0\\node_modules\\@deepseek-ai\\dsh\\lib\\bin.js"\n'),
    ("codex", '@node "%~dp0\\node_modules\\@openai\\codex\\bin\\codex.js"\n'),
    ("kimi", '@node "%~dp0\\node_modules\\@moonshot-ai\\kimi-code\\dist\\main.mjs"\n'),
    ("grok", '@node "%~dp0\\node_modules\\@xai-official\\grok\\bin\\grok"\n'),
    ("pi", '@node "%~dp0\\node_modules\\@earendil-works\\pi-coding-agent\\dist\\bundle\\cli.js"\n'),
)


@pytest.mark.parametrize(("tool_key", "target_suffix"), NPM_POSIX_FIXTURES)
def test_npm_posix_symlink_is_recognised(
    tool_key: str,
    target_suffix: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSIX npm layout: bin/<name> is a symlink into lib/node_modules/<pkg>/…"""
    tool = domain.TOOL_BY_KEY[tool_key]
    # Simulate `~/.npm-global/lib/node_modules/<pkg>/…` on disk.
    target = tmp_path / "lib" / target_suffix.lstrip("./")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("#!/usr/bin/env node\n")
    launcher = tmp_path / "bin" / (tool.check_exe or "")
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.symlink_to(target)
    monkeypatch.setattr(adapters.shutil, "which", lambda _n, _p=launcher: str(_p))

    assert adapters.is_tool_installed(tool) is True


@pytest.mark.parametrize(("tool_key", "wrapper"), NPM_WINDOWS_FIXTURES)
def test_npm_windows_cmd_wrapper_is_recognised(
    tool_key: str,
    wrapper: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows npm shim: bin/<name>.cmd is a text file referencing the pkg path."""
    tool = domain.TOOL_BY_KEY[tool_key]
    launcher = tmp_path / f"{tool.check_exe}.cmd"
    launcher.write_text(wrapper)
    monkeypatch.setattr(adapters.shutil, "which", lambda _n, _p=launcher: str(_p))

    assert adapters.is_tool_installed(tool) is True


AMBIGUOUS_TOOLS: Tuple[str, ...] = tuple(
    tool.key for tool in domain.TOOLS if tool.check_markers and tool.check_exe
)


@pytest.mark.parametrize("tool_key", AMBIGUOUS_TOOLS)
def test_same_name_binary_from_unrelated_project_is_rejected(
    tool_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A homebrew/system executable that just happens to share the CLI name must not spoof detection."""
    tool = domain.TOOL_BY_KEY[tool_key]
    # install_paths 优先级最高,若开发机上恰好存在这些路径会遮蔽本用例想
    # 触发的 marker 判断。用 replace 隔离掉,让检测只走命令名 + marker 路径。
    tool_no_paths = replace(tool, install_paths=())
    unrelated = tmp_path / (tool.check_exe or "x")
    unrelated.write_text("#!/bin/sh\necho 'not the real tool'\n")
    monkeypatch.setattr(adapters.shutil, "which", lambda _n, _p=unrelated: str(_p))

    assert adapters.is_tool_installed(tool_no_paths) is False


def test_every_cli_tool_has_check_markers() -> None:
    """Design invariant: any CLI tool that ships an executable should declare
    markers to disambiguate common command names (`hermes`, `codex`, `grok`,
    `pi`, `dsh`, ...). Desktop-only tools are exempt because their identity
    is the install path, not a PATH command.
    """
    weak_cli = [
        tool.key
        for tool in domain.TOOLS
        if tool.check_exe and not tool.check_markers
    ]
    assert not weak_cli, (
        "CLI tools without check_markers are vulnerable to PATH name "
        f"collisions: {weak_cli}"
    )


DESKTOP_TOOLS: Tuple[str, ...] = tuple(
    tool.key for tool in domain.TOOLS if tool.backend == "desktop"
)


@pytest.mark.parametrize("tool_key", DESKTOP_TOOLS)
def test_desktop_app_paths_probe_all_variants(
    tool_key: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every desktop app must have at least one probable install path per platform."""
    tool = domain.TOOL_BY_KEY[tool_key]
    assert tool.install_paths, f"desktop tool '{tool_key}' must declare install_paths"

    # Redirect one candidate into tmp_path and materialize it.
    candidate = tool.install_paths[0]
    fake = tmp_path / Path(candidate).name
    fake.mkdir()
    replaced = replace(tool, install_paths=(str(fake),))
    monkeypatch.setattr(adapters.shutil, "which", lambda _n: None)

    assert adapters.is_tool_installed(replaced) is True

    replaced_missing = replace(tool, install_paths=(str(tmp_path / "does-not-exist"),))
    assert adapters.is_tool_installed(replaced_missing) is False


def test_claude_standalone_installer_matches_share_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Anthropic ships a self-contained installer; detection must not require npm."""
    versioned = tmp_path / ".local" / "share" / "claude" / "versions" / "2.1.259"
    versioned.mkdir(parents=True)
    launcher = tmp_path / ".local" / "bin" / "claude"
    launcher.parent.mkdir(parents=True)
    launcher.symlink_to(versioned)
    # 屏蔽 install_paths (可能在开发机上真实存在) 以只验 marker 分支。
    tool = replace(domain.TOOL_BY_KEY["claude-code"], install_paths=())
    monkeypatch.setattr(adapters.shutil, "which", lambda _n, _p=launcher: str(_p))

    assert adapters.is_tool_installed(tool) is True


def test_claude_windows_standalone_installer_matches_anthropic_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows standalone 布局:%LOCALAPPDATA%\\AnthropicClaude\\claude.exe,
    应被 install_paths(优先)或 `anthropic` marker(命令名 fallback)命中。"""
    fake_localappdata = tmp_path / "AppData" / "Local"
    exe = fake_localappdata / "AnthropicClaude" / "claude.exe"
    exe.parent.mkdir(parents=True)
    exe.write_text("MZ")
    monkeypatch.setenv("LOCALAPPDATA", str(fake_localappdata))
    monkeypatch.setattr(adapters.shutil, "which", lambda _n: None)

    assert adapters.is_tool_installed(domain.TOOL_BY_KEY["claude-code"]) is True


def test_hermes_launcher_content_identifies_nous_hermes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实的 hermes launcher 是一段引用 `.hermes/hermes-agent` 的 shell 脚本;
    必须在 install_paths 屏蔽后仍能通过启动器内容识别。"""
    launcher = tmp_path / "hermes"
    launcher.write_text(
        'exec "$HOME/.hermes/hermes-agent/venv/bin/python" '
        '"$HOME/.hermes/hermes-agent/hermes" "$@"\n'
    )
    tool = replace(domain.TOOL_BY_KEY["hermes"], install_paths=())
    monkeypatch.setattr(adapters.shutil, "which", lambda _n, _p=launcher: str(_p))

    assert adapters.is_tool_installed(tool) is True


def test_unrelated_hermes_binary_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Python `hermes` 库或其它命名为 hermes 的工具不应误报为已安装。"""
    fake = tmp_path / "hermes"
    fake.write_text("#!/usr/bin/env python3\nprint('unrelated hermes library')\n")
    tool = replace(domain.TOOL_BY_KEY["hermes"], install_paths=())
    monkeypatch.setattr(adapters.shutil, "which", lambda _n, _p=fake: str(_p))

    assert adapters.is_tool_installed(tool) is False


def test_undefined_windows_env_var_on_posix_is_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POSIX 上 `${LOCALAPPDATA}` 不会展开;`Path.exists()` 判 False,不抛异常。

    这是跨平台声明"Windows 专属安装路径"的正确姿势——我们依赖 expandvars
    在未定义变量时原样返回,而不是 raise。
    """
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(adapters.shutil, "which", lambda _n: None)
    tool = replace(
        domain.TOOL_BY_KEY["workbuddy"],
        install_paths=("${LOCALAPPDATA}/Programs/WorkBuddy/WorkBuddy.exe",),
    )

    assert adapters.is_tool_installed(tool) is False


def test_install_paths_expand_env_and_user_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """~ and ${VAR} expansion is central to Windows LOCALAPPDATA probing."""
    fake_app_data = tmp_path / "AppData" / "Local"
    programs = fake_app_data / "Programs" / "WorkBuddy" / "WorkBuddy.exe"
    programs.parent.mkdir(parents=True)
    programs.write_text("MZ")  # arbitrary bytes
    monkeypatch.setenv("LOCALAPPDATA", str(fake_app_data))

    tool = replace(
        domain.TOOL_BY_KEY["workbuddy"],
        install_paths=("${LOCALAPPDATA}/Programs/WorkBuddy/WorkBuddy.exe",),
    )
    monkeypatch.setattr(adapters.shutil, "which", lambda _n: None)

    assert adapters.is_tool_installed(tool) is True


def test_every_tool_has_a_detectable_identity() -> None:
    """Guardrail: every registered tool must be discoverable somehow.

    Without this contract a future tool could ship with neither check_exe nor
    install_paths and quietly report "installed" or "not installed" based on
    unrelated global state.
    """
    weak = []
    for tool in domain.TOOLS:
        has_exe = bool(tool.check_exe)
        has_paths = bool(tool.install_paths)
        if not (has_exe or has_paths):
            weak.append(tool.key)
    assert not weak, f"tools without detection identity: {weak}"
