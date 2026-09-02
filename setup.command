#!/bin/bash
"exec" "python3" "$0" "$@"
# -*- coding: utf-8 -*-
# 腾讯云 Token Plan — 小白一键接入
# Mac: 终端运行 | Windows: 右键→Python 打开
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

HOME = Path.home()
VERSION = "2.1.1"
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"
WHITE = "\033[37m"

BACKUP_DIR = HOME / ".tokenplan-backups"
DEFAULT_TIMEOUT = 10
# 安装命令(npm 等)的最长等待;超时视为网络受限而非无限转圈
INSTALL_TIMEOUT = 600


IS_WINDOWS = sys.platform == "win32"


def clear() -> None:
    """Clear the terminal (cls on Windows, ANSI reset elsewhere)."""
    if IS_WINDOWS:
        os.system("cls")
        return
    print("\033[2J\033[H", end="")


def ok(msg: str) -> None:
    """Print a green success line."""
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    """Print a yellow warning line."""
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def info(msg: str) -> None:
    """Print a blue informational line."""
    print(f"  {BLUE}→{RESET} {msg}")


def dim(msg: str) -> None:
    """Print a plain neutral line."""
    print(f"  {WHITE}{msg}{RESET}")


def ask(msg: str) -> str:
    """Prompt for input, stripped of whitespace."""
    return input(f"  {msg}").strip()


def mask_secret(secret: str, visible: int = 4) -> str:
    """Mask a secret for display, keeping only the first `visible` chars."""
    if not secret:
        return ""
    if len(secret) <= visible:
        return "*" * len(secret)
    return f"{secret[:visible]}…"


class Spinner:
    """Terminal spinner with tty detection and CJK-safe line erasing."""

    def __init__(self, msg: str):
        self.msg = msg
        self.running = False
        self.thread = None
        # CJK characters are double-width, so clearing by character count
        # never fully erases the line; use ANSI \x1b[K instead, and skip
        # animation entirely when stdout is not a terminal (pipes/logs).
        self.tty = bool(sys.stdout.isatty())

    def _spin(self) -> None:
        """Animation loop; skipped entirely when stdout is not a tty."""
        if not self.tty:
            return
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while self.running:
            sys.stdout.write(f"\r  {CYAN}{frames[i % len(frames)]}{RESET} {self.msg}")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

    def start(self) -> None:
        """Start the spinner thread."""
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self, success: bool = True) -> None:
        """Stop the spinner, erase the line with ANSI \x1b[K, print the final status."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.3)
        if self.tty:
            sys.stdout.write("\r\x1b[K")
            sys.stdout.flush()
        if success:
            ok(self.msg)
        else:
            warn(f"{self.msg} (失败)")


def enable_windows_ansi() -> None:
    """Enable VT100/ANSI escape processing on legacy Windows consoles."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0007)
    except Exception:
        pass


@dataclass(frozen=True)
class PlanSpec:
    """A Token Plan product tier: display info plus its API base URL and key console URL."""

    choice: str
    key: str
    display_name: str
    base_url: str
    key_url: str
    only_note: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Declarative registry entry: install command, config location, usage guidance."""

    key: str
    name: str
    backend: str
    check_exe: Optional[str] = None
    install_cmd: Optional[Union[tuple[str, ...], str]] = None
    install_cmd_win: Optional[Union[tuple[str, ...], str]] = None
    win_manual: bool = False
    download_url: Optional[str] = None
    start_hint: str = ""
    cfg_hint: str = ""
    usage_lines: Tuple[str, ...] = field(default_factory=tuple)


def backup_file(path: Path) -> Optional[Path]:
    """Copy path to ~/.tokenplan-backups with a timestamp and append to manifest.jsonl."""
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"{path.name}.{ts}.bak"
    shutil.copy2(path, backup)
    # 备份常含 API Key:无论源文件权限如何,一律收紧为仅属主可读写
    try:
        backup.chmod(0o600)
    except OSError:
        pass
    manifest = BACKUP_DIR / "manifest.jsonl"
    entry = {"backup": backup.name, "original": str(path), "ts": ts}
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return backup


STATE_PATH = BACKUP_DIR / "state.json"


def load_state() -> Dict[str, list]:
    """Load the side-effect ledger (rc blocks, env files, setx keys) for uninstall."""
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"rc_blocks": [], "setx_keys": [], "files_written": [], "env_files": []}


def save_state(state: Dict[str, list]) -> None:
    """Persist the side-effect ledger to state.json."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    )


def record_state(kind: str, value: object) -> None:
    """Track a side effect so `uninstall` can revert it precisely."""
    state = load_state()
    bucket = state.setdefault(kind, [])
    if value not in bucket:
        bucket.append(value)
    save_state(state)


def cfg_path(*parts: str) -> Path:
    """Resolve a path under HOME (creating parent dirs) for config files."""
    p = HOME.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _harden(path: Path) -> None:
    """Owner-only permissions for files that carry API keys."""
    try:
        path.chmod(0o600)
    except OSError:
        pass


def write_json(
    path: Path,
    data: object,
    merge: bool = False,
    merge_key: Optional[str] = None,
) -> None:
    """Backup then write JSON; hardens to 0o600.

    merge=True with dicts shallow-merges (existing.update).
    merge=True with lists and merge_key set keeps user entries and
    replaces only entries whose merge_key matches ours (list order:
    user's non-conflicting entries first, then ours).
    """
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if merge and path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            existing = None
        if isinstance(existing, dict) and isinstance(data, dict):
            existing.update(data)
            data = existing
        elif (
            isinstance(existing, list)
            and isinstance(data, list)
            and merge_key
        ):
            ours_keys = {
                str(entry.get(merge_key))
                for entry in data
                if isinstance(entry, dict)
            }
            kept = [
                entry
                for entry in existing
                if not (isinstance(entry, dict) and str(entry.get(merge_key)) in ours_keys)
            ]
            data = kept + list(data)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _harden(path)


def write_env(
    path: Path, remove_keys: Iterable[str] = (), export: bool = False, **kv: str
) -> None:
    """Backup then rewrite a dotenv file, replacing only managed keys. Hardens to 0o600.

    export=True writes `export KEY=VALUE` lines for files that are `source`d
    from shell rc files (vars must be exported to reach child processes).
    User's own unmanaged lines are preserved verbatim.
    """
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old_lines = path.read_text().splitlines() if path.exists() else []

    def _is_managed(line: str, keys: set) -> bool:
        stripped = line
        if stripped.startswith("export "):
            stripped = stripped[len("export "):]
        return any(stripped.startswith(f"{key}=") for key in keys)

    managed_keys = set(kv) | set(remove_keys)
    keep_lines = [line for line in old_lines if not _is_managed(line, managed_keys)]
    prefix = "export " if export else ""
    for key, value in kv.items():
        keep_lines.append(f"{prefix}{key}={value}")
    path.write_text("\n".join(line for line in keep_lines if line.strip()) + "\n")
    _harden(path)


def run_command(command: Union[Tuple[str, ...], str], message: str) -> bool:
    """Run an install command, streaming output; returns success."""
    print(f"  {CYAN}→{RESET} {message}")
    print()
    # Windows: npm/code etc. are .cmd shims that CreateProcess cannot launch
    # directly without a shell; resolve and reroute through the string branch.
    if isinstance(command, tuple) and IS_WINDOWS:
        exe = shutil.which(command[0])
        if exe and exe.lower().endswith((".cmd", ".bat")):
            command = subprocess.list2cmdline(command)
    try:
        if isinstance(command, tuple):
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        elif IS_WINDOWS:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        else:
            proc = subprocess.Popen(
                command,
                shell=True,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        assert proc.stdout is not None
        # 看门狗:到点 kill 进程,让阻塞中的 readline 以 EOF 退出。
        # (按行检查对无输出的静默进程无效——readline 永远等不到第一行。)
        state = {"timed_out": False}

        def _kill_on_timeout() -> None:
            state["timed_out"] = True
            try:
                proc.kill()
            except OSError:
                pass

        watchdog = threading.Timer(INSTALL_TIMEOUT, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    print(f"     {WHITE}{line}{RESET}")
            proc.wait()
        finally:
            watchdog.cancel()
        if state["timed_out"]:
            print()
            warn(f"{message} — 超时(超过 {INSTALL_TIMEOUT // 60} 分钟,已终止)")
            warn("网络可能受限;可用 --tools 跳过该工具,或先手动安装后重跑")
            return False
        print()
        if proc.returncode == 0:
            ok(f"{message} — 完成")
            return True
        warn(f"{message} — 失败")
        return False
    except Exception as exc:
        warn(f"{message} — 失败: {exc}")
        return False


MODEL_CATALOG = {
    "personal-general": {
        "default": "tc-code-latest",
        "display": (
            "Auto 智能路由: tc-code-latest",
            "DeepSeek-V4-Flash: deepseek-v4-flash-202605",
            "DeepSeek-V4-Pro: deepseek-v4-pro-202606",
            "MiniMax-M2.7: minimax-m2.7",
            "MiniMax-M3: minimax-m3",
            "GLM-5: glm-5",
            "GLM-5.1: glm-5.1",
            "GLM-5.2: glm-5.2",
            "GLM-5.3: glm-5.3",
            "Kimi-K2.7-Code: kimi-k2.7-code",
        ),
    },
    "personal-hy": {
        "default": "hy3",
        "display": (
            "Hy3: hy3",
            "Hy4-preview: hy4-preview",
        ),
    },
    "enterprise-pro": {
        "default": "auto",
        "display": (
            "Auto: auto",
            "GLM-5.3: glm-5.3",
            "GLM-5.2: glm-5.2",
            "GLM-5: glm-5",
            "GLM-5.1: glm-5.1",
            "GLM-5-Turbo: glm-5-turbo",
            "Kimi K2.7 Code: kimi-k2.7-code",
            "HighSpeed: kimi-k2.7-code-highspeed",
            "Kimi-K2.6: kimi-k2.6",
            "MiniMax-M2.7: minimax-m2.7",
            "MiniMax-M3: minimax-m3",
            "DeepSeek-V4-Flash: deepseek-v4-flash",
            "DeepSeek-V4-Pro: deepseek-v4-pro",
            "DeepSeek-V4-Flash 0731 正式版: deepseek-v4-flash-0731",
            "DeepSeek-V4-Pro 0813 正式版: deepseek-v4-pro-0813",
            "DeepSeek-V4-Flash 正式版 原厂: deepseek-v4-flash-202605",
            "Pro 原厂: deepseek-v4-pro-202606",
            "Vision-Exp 原厂(多模态): deepseek/deepseek-v4-flash-vision-exp",
        ),
    },
    "enterprise-light": {
        "default": "auto",
        "display": (
            "Auto 智能路由: auto",
        ),
    },
    # ── 国际站(新加坡地域):端点与模型来自官方文档 130659/131173 的"新加坡"章节 ──
    # 专业套餐模型表与中国站逐行一致(2026-09 官方文档核实);轻享仅 Auto。
    # 个人版模型列表参照中国站通用套餐(官方国际站文档 1300/81470 暂无法程序化访问,
    # 以 --verify-models 端到端验证兜底;远程目录 models.json 可随时修正)。
    "intl-personal": {
        "default": "tc-code-latest",
        "display": (
            "Auto 智能路由: tc-code-latest",
            "DeepSeek-V4-Flash: deepseek-v4-flash-202605",
            "DeepSeek-V4-Pro: deepseek-v4-pro-202606",
            "MiniMax-M2.7: minimax-m2.7",
            "GLM-5: glm-5",
            "GLM-5.1: glm-5.1",
            "GLM-5.2: glm-5.2",
            "Kimi-K2.5: kimi-k2.5 (已过 2026-08-31 下线日期,可能不可用)",
        ),
    },
    "intl-enterprise-pro": {
        "default": "auto",
        "display": (
            "Auto: auto",
            "GLM-5.3: glm-5.3",
            "GLM-5.2: glm-5.2",
            "GLM-5: glm-5",
            "GLM-5.1: glm-5.1",
            "GLM-5-Turbo: glm-5-turbo",
            "Kimi K2.7 Code: kimi-k2.7-code",
            "HighSpeed: kimi-k2.7-code-highspeed",
            "Kimi-K2.6: kimi-k2.6",
            "MiniMax-M2.7: minimax-m2.7",
            "MiniMax-M3: minimax-m3",
            "DeepSeek-V4-Flash: deepseek-v4-flash",
            "DeepSeek-V4-Pro: deepseek-v4-pro",
            "DeepSeek-V4-Flash 0731 正式版: deepseek-v4-flash-0731",
            "DeepSeek-V4-Pro 0813 正式版: deepseek-v4-pro-0813",
            "DeepSeek-V4-Flash 正式版 原厂: deepseek-v4-flash-202605",
            "Pro 原厂: deepseek-v4-pro-202606",
            "Vision-Exp 原厂(多模态): deepseek/deepseek-v4-flash-vision-exp",
        ),
    },
    "intl-enterprise-light": {
        "default": "auto",
        "display": (
            "Auto 智能路由: auto",
        ),
    },
    # 后付费(TokenHub 按量计费,官方文档 1823/130058):模型库动态变化,不做内置策展;
    # 运行时通过 /v3/models 实时发现(端点已验证存在),见 discover_postpaid_models()。
    "postpaid": {
        "default": "",
        "display": (),
    },
}

# Claude Code exposes three fixed custom slots. Keep these mappings separate from
# the OpenAI-compatible model catalog so other adapters remain unchanged.
CLAUDE_MODEL_SLOTS = {
    "personal-general": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
    },
    "enterprise-pro": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
    },
    "intl-personal": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
    },
    "intl-enterprise-pro": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
    },
}


PLAN_CATALOG: Dict[str, PlanSpec] = {
    "1": PlanSpec(
        choice="1",
        key="personal-general",
        display_name="个人版 - 通用",
        base_url="https://api.lkeap.cloud.tencent.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/tokenplan/common/api-key",
    ),
    "2": PlanSpec(
        choice="2",
        key="personal-hy",
        display_name="个人版 - Hy（混元）",
        base_url="https://api.lkeap.cloud.tencent.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/tokenplan/hy/api-key",
        only_note="该套餐仅支持 Hy3 模型",
    ),
    "3": PlanSpec(
        choice="3",
        key="enterprise-pro",
        display_name="企业版 - 专业套餐",
        base_url="https://tokenhub.tencentmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/tokenplan-e/api-key",
    ),
    "4": PlanSpec(
        choice="4",
        key="enterprise-light",
        display_name="企业版 - 轻享套餐",
        base_url="https://tokenhub.tencentmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/tokenplan-e/api-key",
        only_note="该套餐仅支持 Auto 模型",
    ),
    "5": PlanSpec(
        choice="5",
        key="intl-personal",
        display_name="国际站 - 个人版（新加坡）",
        base_url="https://tokenhub-intl.tencentmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="新加坡地域,不支持跨地域调用;模型列表参照中国站个人版通用套餐",
    ),
    "6": PlanSpec(
        choice="6",
        key="intl-enterprise-pro",
        display_name="国际站 - 企业版专业套餐（新加坡）",
        base_url="https://tokenhub-intl.tencentmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="新加坡地域,不支持跨地域调用",
    ),
    "7": PlanSpec(
        choice="7",
        key="intl-enterprise-light",
        display_name="国际站 - 企业版轻享套餐（新加坡）",
        base_url="https://tokenhub-intl.tencentmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="新加坡地域;该套餐仅支持 Auto 模型",
    ),
    "8": PlanSpec(
        choice="8",
        key="postpaid",
        display_name="后付费 - 按量计费（大模型服务平台）",
        base_url="https://tokenhub.tencentmaas.com/v1",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="按 token 计费(非套餐订阅);模型列表由 API 实时发现,需联网",
    ),
}


TOOLS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        key="hermes",
        name="Hermes Agent",
        backend="cli",
        check_exe="hermes",
        start_hint="hermes",
        cfg_hint="~/.hermes/.env",
        install_cmd=(
            "bash",
            "-c",
            "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser --skip-computer-use --skip-setup",
        ),
        win_manual=True,
        download_url="https://hermes-agent.nousresearch.com",
        usage_lines=(
            "终端输入: hermes",
            "切换模型: 输入 /model",
            "模型列表: 由 Hermes 从当前 custom 端点自动发现",
            "Windows: 暂不支持自动安装，请参考官网手动安装后重跑修复模式",
        ),
    ),
    ToolSpec(
        key="codebuddy",
        name="CodeBuddy Code",
        backend="cli",
        check_exe="codebuddy",
        install_cmd=("npm", "install", "-g", "@tencent-ai/codebuddy-code"),
        start_hint="codebuddy",
        cfg_hint="~/.codebuddy/models.json",
        usage_lines=(
            "终端输入: codebuddy",
            "Token Plan 使用 API Key，无需腾讯账号网页登录",
            "如果新窗口提示 command not found，请先执行: source ~/.zshrc",
            "输入 /model 切换模型",
        ),
    ),
    ToolSpec(
        key="claude-code",
        name="Claude Code",
        backend="cli",
        check_exe="claude",
        install_cmd=("npm", "install", "-g", "@anthropic-ai/claude-code"),
        start_hint="claude",
        cfg_hint="~/.claude/settings.json",
        usage_lines=(
            "终端输入: claude",
            "切换模型: claude --model <模型ID>",
            "完整模型选择器: claude-tokenplan",
            "重要: Claude 内置 /model 只显示固定槽位，不能显示全部 Token Plan 模型",
            "其它模型请用 claude --model <模型ID>，或运行 claude-tokenplan 选择",
            "glm-5.3 始终思考：已启用 Thinking mode，并默认使用 high effort",
            "模型与强度需分别执行：先提交 /model <模型ID>，成功后再单独提交 /effort low|high|max",
            "不要一次粘贴两行，也不要使用 /model <模型ID> low；它们都会被当成模型 ID",
        ),
    ),
    ToolSpec(
        key="opencode",
        name="OpenCode",
        backend="cli",
        check_exe="opencode",
        start_hint="opencode",
        cfg_hint="~/.config/opencode/opencode.json",
        install_cmd=("npm", "install", "-g", "opencode-ai"),
        usage_lines=(
            "终端输入: opencode",
            "项目初始化: 在 OpenCode 中输入 /init",
            "切换模型: 输入 /models",
            "Token Plan 使用 OpenAI-compatible Chat Completions 端点",
        ),
    ),
    ToolSpec(
        key="openclaw",
        name="OpenClaw",
        backend="cli",
        check_exe="openclaw",
        start_hint="openclaw",
        cfg_hint="~/.openclaw/openclaw.json",
        install_cmd=(
            "bash",
            "-c",
            "curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard",
        ),
        install_cmd_win=("npm", "install", "-g", "openclaw@latest"),
        download_url="https://openclaw.ai",
        usage_lines=(
            "终端输入: openclaw",
            "检查配置: openclaw config validate",
            "仅看套餐模型: openclaw models list --provider tencent-tokenplan",
            "切换模型: openclaw models set tencent-tokenplan/<模型ID>",
            "不要运行 /auth tencent-token-plan；该名称不是本安装器配置的 Provider",
            "Token Plan 使用 API Key，无需 ChatGPT 或其他网页登录",
        ),
    ),
    ToolSpec(
        key="dsh",
        name="DeepSeek Harness",
        backend="cli",
        check_exe="dsh",
        install_cmd=("npm", "install", "-g", "@deepseek-ai/dsh@latest"),
        start_hint="dsh web",
        cfg_hint="~/.dsh/settings.yaml",
        usage_lines=(
            "终端输入: dsh web",
            "浏览器打开: http://127.0.0.1:3080",
            "如果提示 ~/.dsh/cordis.patch.yml 格式错误，未使用自定义 patch 时可删除它",
            "修复: rm ~/.dsh/cordis.patch.yml",
            "或保留文件: printf '%s\\n' '[]' > ~/.dsh/cordis.patch.yml",
        ),
    ),
    ToolSpec(
        key="codex",
        name="Codex CLI",
        backend="cli",
        check_exe="codex",
        install_cmd=("npm", "install", "-g", "@openai/codex"),
        start_hint="codex",
        cfg_hint="~/.codex/config.toml",
        usage_lines=(
            "终端输入: codex",
            "切换模型: 会话中输入 /model，或编辑 ~/.codex/config.toml 的 model 字段",
            "Token Plan 走 Responses 协议(wire_api = responses)，已自动配置",
            "API Key 环境变量: TOKENPLAN_API_KEY",
        ),
    ),
    ToolSpec(
        key="workbuddy",
        name="WorkBuddy",
        backend="desktop",
        check_exe=None,
        download_url="https://workbuddy.qq.com",
        cfg_hint="~/.workbuddy/models.json",
        usage_lines=(
            "下载安装: https://workbuddy.qq.com（腾讯云 AI 桌面智能体）",
            "模型配置: 安装器已自动写入当前套餐全部模型到 ~/.workbuddy/models.json",
            "打开 WorkBuddy → 模型选择,即可看到 TokenPlan 开头的模型",
            "如需手动添加: 设置 → 模型/服务商,Base URL: {base_url}",
        ),
    ),
    ToolSpec(
        key="kimi",
        name="Kimi Code",
        backend="cli",
        check_exe="kimi",
        install_cmd=("npm", "install", "-g", "@moonshot-ai/kimi-code"),
        start_hint="kimi",
        cfg_hint="~/.kimi-code/config.toml",
        usage_lines=(
            "终端输入: kimi",
            "安装器已写入 tokenplan provider 与套餐模型(config.toml),默认模型已设为套餐默认",
            "切换模型: 会话内 /model,或 kimi -m <模型别名>",
            "配置文件: ~/.kimi-code/config.toml",
        ),
    ),
    ToolSpec(
        key="grok",
        name="Grok CLI",
        backend="cli",
        check_exe="grok",
        install_cmd=("npm", "install", "-g", "@xai-official/grok"),
        start_hint="grok",
        cfg_hint="~/.grok/config.toml",
        usage_lines=(
            "终端输入: grok",
            "安装器已写入套餐模型到 ~/.grok/config.toml 的 [model.*] 段",
            "切换模型: 会话内 /model,或 grok -m <模型名>",
        ),
    ),
    ToolSpec(
        key="pi",
        name="Pi",
        backend="cli",
        check_exe="pi",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", "@earendil-works/pi-coding-agent"),
        start_hint="pi",
        cfg_hint="~/.pi/agent/models.json",
        usage_lines=(
            "终端输入: pi",
            "安装器已写入 tokenplan provider 与套餐模型(models.json)",
            "切换模型: 会话内 /model,或 pi --model tokenplan/<模型>",
        ),
    ),
    ToolSpec(
        key="zcode",
        name="ZCode",
        backend="desktop",
        check_exe=None,
        download_url="https://zcode.ai",
        cfg_hint="~/.zcode/v2/config.json",
        usage_lines=(
            "下载安装: https://zcode.ai(智谱 ZCode 客户端)",
            "安装器已写入自定义 provider 与套餐模型到 ~/.zcode/v2/config.json",
            "启动 ZCode 后在模型选择中使用 Tencent Cloud Token Plan 条目",
            "该客户端为闭源应用,配置写入未经官方端到端验证,如异常请在应用内手动添加",
        ),
    ),
)


TOOL_BY_INDEX = {str(i + 1): tool for i, tool in enumerate(TOOLS)}
TOOL_BY_KEY = {tool.key: tool for tool in TOOLS}

TOOL_DEPENDENCY_REGISTRY = {
    "hermes": ("curl",),
    "openclaw": ("curl",),
    "dsh": ("npx",),
}

BACKEND_REGISTRY = {
    "cli": {
        "label": "命令行工具",
        "auto_install": True,
        "manual_download": False,
        "requires": (),
        "usage_template": (
            "启动命令: {start_hint}",
            "配置位置: {cfg_hint}",
        ),
    },
    "desktop": {
        "label": "桌面应用",
        "auto_install": False,
        "manual_download": True,
        "requires": (),
        "usage_template": (
            "打开 {name} → 设置 → 模型",
            "Base URL: {base_url}",
            "API Key:  {api_key_mask}",
        ),
    },
}

def get_backend_adapter(tool: ToolSpec) -> Dict[str, object]:
    """Look up the backend adapter config, defaulting to a generic one."""
    return BACKEND_REGISTRY.get(tool.backend, {
        "label": tool.backend,
        "auto_install": False,
        "manual_download": False,
        "requires": (),
        "usage_template": (),
    })


def get_npm_prefix_dir() -> Optional[Path]:
    """Return the npm global prefix directory, or None if unavailable."""
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        prefix = subprocess.check_output(
            [npm, "config", "get", "prefix"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not prefix or prefix in {"null", "undefined"}:
        return None
    return Path(prefix)


def query_windows_user_env(key: str) -> Optional[str]:
    """Best-effort read of a current-user env var from the registry."""
    try:
        result = subprocess.run(
            ["reg", "query", "HKCU\\Environment", "/v", key],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if key in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        return " ".join(parts[2:])
    except (OSError, ValueError):
        pass
    return None


def install_codebuddy_shell_env(api_key: str, base_url: str) -> None:
    """Provide CodeBuddy Code's documented API-key authentication path."""
    if IS_WINDOWS:
        for key, value in (
            ("CODEBUDDY_API_KEY", api_key),
            ("OPENAI_API_KEY", api_key),
            ("OPENAI_BASE_URL", base_url),
        ):
            old_value = query_windows_user_env(key)
            record_state("setx_keys", {"key": key, "old": old_value})
            os.environ[key] = value
            subprocess.run(["setx", key, value], capture_output=True, check=False)
        info("已写入 Windows 用户环境变量，重新打开终端后生效")
        return
    env_path = cfg_path(".codebuddy", "tokenplan.env")
    write_env(
        env_path,
        export=True,
        CODEBUDDY_API_KEY=api_key,
        OPENAI_API_KEY=api_key,
        OPENAI_BASE_URL=base_url,
    )
    record_state("env_files", str(env_path))
    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan CodeBuddy Code API-key authentication"
    existing = rc_path.read_text() if rc_path.exists() else ""
    source_line = f'[ -f "{env_path}" ] && source "{env_path}"'
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(existing.rstrip() + f"\n{marker}\n{source_line}\n")
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    os.environ["CODEBUDDY_API_KEY"] = api_key
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url


def install_claude_tokenplan_path() -> None:
    """Expose the full Token Plan model selector in future shells."""
    launcher_dir = cfg_path(".local", "bin")
    launcher_dir.mkdir(parents=True, exist_ok=True)
    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan Claude model selector"
    existing = rc_path.read_text() if rc_path.exists() else ""
    path_line = f'export PATH="{launcher_dir}:$PATH"'
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(existing.rstrip() + f"\n{marker}\n{path_line}\n")
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    record_state("files_written", str(launcher_dir / "claude-tokenplan"))
    current_path = os.environ.get("PATH", "")
    if str(launcher_dir) not in current_path.split(":"):
        os.environ["PATH"] = f"{launcher_dir}:{current_path}"


def _claude_tokenplan_cmd(model_ids: List[str]) -> str:
    """Render a Windows batch launcher for the Token Plan model selector."""
    models = " ".join(model_ids)
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal enabledelayedexpansion",
        f"set MODELS={models}",
        "echo Token Plan models:",
        "set /a IDX=0",
        "for %%M in (%MODELS%) do (",
        "  set /a IDX+=1",
        "  echo   !IDX!. %%M",
        ")",
        "set /p CHOICE=Select number or type full model ID: ",
        "set MODEL=",
        "set /a IDX=0",
        "for %%M in (%MODELS%) do (",
        "  set /a IDX+=1",
        '  if "!CHOICE!"=="!IDX!" set MODEL=%%M',
        ")",
        "if not defined MODEL set MODEL=%CHOICE%",
        'if "%MODEL%"=="" (',
        "  echo Invalid selection",
        "  endlocal & exit /b 1",
        ")",
        "endlocal & claude --model %MODEL% %*",
    ]
    return "\r\n".join(lines) + "\r\n"


def install_claude_tokenplan_launcher_win(model_ids: List[str]) -> None:
    """Write claude-tokenplan.cmd into the npm global dir (already on PATH)."""
    prefix = get_npm_prefix_dir()
    target_dir = prefix if prefix and prefix.is_dir() else cfg_path(".local", "bin")
    target_dir.mkdir(parents=True, exist_ok=True)
    launcher = target_dir / "claude-tokenplan.cmd"
    launcher.write_text(_claude_tokenplan_cmd(model_ids), encoding="utf-8")
    record_state("files_written", str(launcher))
    if prefix:
        info(f"已写入模型选择器: {launcher}")
    else:
        warn(f"未检测到 npm 全局目录，请手动将该目录加入 PATH: {target_dir}")


def ensure_npm_bin_on_path() -> None:
    """Make globally installed npm CLI commands available in future shells."""
    prefix = get_npm_prefix_dir()
    if not prefix:
        return

    if IS_WINDOWS:
        # Windows npm shims (.cmd) live in the prefix root itself.
        path_value = str(prefix)
        current_path = os.environ.get("PATH", "")
        parts = [p for p in current_path.split(";") if p]
        if path_value.lower() not in [p.lower() for p in parts]:
            os.environ["PATH"] = f"{path_value};{current_path}"
        return

    npm_bin = prefix / "bin"
    if not npm_bin.is_dir():
        return

    path_value = str(npm_bin)
    current_path = os.environ.get("PATH", "")
    if path_value not in current_path.split(":"):
        os.environ["PATH"] = f"{path_value}:{current_path}"

    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan npm global CLI path"
    existing = rc_path.read_text() if rc_path.exists() else ""
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        block = f'\n{marker}\nexport PATH="{npm_bin}:$PATH"\n'
        rc_path.write_text(existing.rstrip() + block)
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    info(f"npm 全局命令路径已加入: {npm_bin}")


def is_tool_installed(tool: ToolSpec) -> bool:
    """Detect installation via executable on PATH."""
    return bool(tool.check_exe and shutil.which(tool.check_exe))


def requires_backend_dependency(tool: ToolSpec, dependency: str) -> bool:
    """True if the backend adapter or TOOL_DEPENDENCY_REGISTRY requires it."""
    adapter = get_backend_adapter(tool)
    if dependency in adapter.get("requires", ()):
        return True
    return dependency in TOOL_DEPENDENCY_REGISTRY.get(tool.key, ())


def get_install_command(tool: ToolSpec) -> Optional[Union[Tuple[str, ...], str]]:
    """Return the install command for the current platform.

    Windows prefers an explicit install_cmd_win when present; otherwise it
    falls back to install_cmd only when that command is platform-neutral
    (e.g. npm tuples), never for bash/curl pipelines.
    """
    if IS_WINDOWS:
        if tool.install_cmd_win is not None:
            return tool.install_cmd_win
        cmd = tool.install_cmd
        if isinstance(cmd, tuple) and cmd and cmd[0] not in {"bash", "sh"}:
            return cmd
        return None
    return tool.install_cmd


def should_manual_download(tool: ToolSpec) -> bool:
    """True when the user must fetch the app manually (platform or backend)."""
    if IS_WINDOWS and tool.win_manual:
        return True
    return bool(get_backend_adapter(tool).get("manual_download"))


def supports_auto_install(tool: ToolSpec) -> bool:
    """True when the backend allows auto-install and a command is available."""
    adapter = get_backend_adapter(tool)
    return bool(adapter.get("auto_install")) and bool(get_install_command(tool))


def install_tool(tool: ToolSpec) -> bool:
    """Run the install command (npm gets a private cache; .cmd shims rerouted on Windows)."""
    command = get_install_command(tool)
    if not command:
        return True
    if should_manual_download(tool):
        return False
    if requires_backend_dependency(tool, "code") and not shutil.which("code"):
        warn("未找到 code 命令，无法自动安装 VS Code 插件")
        return False
    if isinstance(command, tuple) and command and command[0] == "npm":
        npm_cache = cfg_path(".tokenplan-npm-cache")
        npm_cache.mkdir(parents=True, exist_ok=True)
        command = (*command, "--cache", str(npm_cache))
    return run_command(command, f"正在安装 {tool.name}...")


def render_usage_lines(tool: ToolSpec, base_url: str, api_key: str) -> List[str]:
    """Render backend template + tool usage_lines, filling base_url/api_key placeholders."""
    rendered: List[str] = []
    adapter = get_backend_adapter(tool)
    template_lines = adapter.get("usage_template", ())
    for line in template_lines:
        rendered.append(
            line.format(
                name=tool.name,
                base_url=base_url,
                api_key_mask=mask_secret(api_key),
                start_hint=tool.start_hint,
                cfg_hint=tool.cfg_hint,
            )
        )
    for line in tool.usage_lines:
        rendered.append(line.format(base_url=base_url, api_key_mask=mask_secret(api_key)))
    return rendered


def check_prerequisites(selected_tools: Iterable[ToolSpec]) -> bool:
    """Check OS/Node/npm/npx/code/curl for the selected tools; returns readiness."""
    print("  ── 前置检查 ──")
    print()

    if sys.platform == "darwin":
        architecture = os.uname().machine
        macos_version = "未知"
        try:
            macos_version = subprocess.check_output(
                ["sw_vers", "-productVersion"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.SubprocessError):
            pass
        ok(f"macOS {macos_version} ({architecture})")
        if architecture not in {"arm64", "x86_64"}:
            warn(f"未验证的 Mac 架构: {architecture}")
    elif IS_WINDOWS:
        try:
            win_ver = sys.getwindowsversion()  # type: ignore[attr-defined]
            info(f"Windows {win_ver.major}.{win_ver.minor} (build {win_ver.build})")
        except AttributeError:
            info("Windows")
    else:
        info(f"当前平台: {sys.platform}")

    needs_node = any(
        tool.backend == "cli"
        and get_install_command(tool)
        and any("npm" in part or "npx" in part for part in (get_install_command(tool) or ("",)))
        for tool in selected_tools
    )
    needs_code = any(requires_backend_dependency(tool, "code") for tool in selected_tools)
    needs_curl = (
        not IS_WINDOWS
        and any(requires_backend_dependency(tool, "curl") for tool in selected_tools)
    )
    prerequisites_ready = True
    ok("Python 3")

    if needs_node:
        node_ok = bool(shutil.which("node"))
        npm_ok = bool(shutil.which("npm"))
        npx_ok = bool(shutil.which("npx"))
        if node_ok:
            ok("Node.js")
        else:
            warn("未安装 Node.js，依赖 npm/npx 的工具可能无法安装或运行")
            info("安装地址: https://nodejs.org/en/download")
            info("Windows 也可使用: winget install OpenJS.NodeJS.LTS")
            info("macOS 也可使用: brew install node")
            info("Ubuntu/Debian 也可使用: sudo apt install nodejs npm")
            info("如果您没有安装权限，请联系企业 IT 管理员")
        if npm_ok:
            ok("npm")
        else:
            warn("未安装 npm，Node 工具安装可能失败")
        if npx_ok:
            ok("npx")
        else:
            npx_tools = [t.name for t in selected_tools if requires_backend_dependency(t, "npx")]
            if npx_tools:
                warn(f"未安装 npx，{('、'.join(npx_tools))} 将无法启动")
        if not node_ok or not npm_ok:
            prerequisites_ready = False
            warn("当前环境缺少 Node 依赖，所选 Node 工具无法安装")
            info("请安装 Node.js LTS 后重新运行本安装器")
            if sys.platform == "darwin":
                info("推荐地址: https://nodejs.org/en/download")

    if needs_code:
        if shutil.which("code"):
            ok("VS Code CLI (code)")
        else:
            warn("未找到 VS Code CLI：插件类工具将无法自动安装")

    if needs_curl:
        if shutil.which("curl"):
            ok("curl")
        else:
            prerequisites_ready = False
            warn("未安装 curl，Hermes 自动安装可能失败")

    if shutil.which("git"):
        ok("git")

    print()
    return prerequisites_ready


# 远程模型目录:优先于内置 MODEL_CATALOG,由 refresh_remote_catalog() 填充。
# 仓库根目录的 models.json 通过 jsDelivr CDN 分发,更新模型只需提交一次 JSON。
REMOTE_CATALOG_URL = (
    "https://cdn.jsdelivr.net/gh/zmq1121/tokenplan-quick-setup@main/models.json"
)
_REMOTE_CATALOG: Optional[Dict[str, Dict[str, object]]] = None
_REMOTE_LATEST_VERSION: Optional[str] = None


def refresh_remote_catalog() -> None:
    """Fetch the remote model catalog; keep built-in catalog on any failure."""
    global _REMOTE_CATALOG, _REMOTE_LATEST_VERSION
    try:
        req = urllib.request.Request(
            REMOTE_CATALOG_URL, headers={"User-Agent": f"tokenplan-setup/{VERSION}"}
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode(errors="ignore"))
        plans = payload.get("plans") if isinstance(payload, dict) else None
        if isinstance(plans, dict) and plans:
            _REMOTE_CATALOG = plans
        latest = payload.get("latest_version") if isinstance(payload, dict) else None
        if isinstance(latest, str) and latest:
            _REMOTE_LATEST_VERSION = latest
    except Exception:
        pass


def _version_tuple(version: str) -> Tuple[int, ...]:
    """Parse '1.2.3' into (1, 2, 3); non-numeric parts are ignored."""
    parts = []
    for chunk in version.split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            break
    return tuple(parts) or (0,)


def notify_upgrade_available() -> None:
    """Old distributed files learn about new releases via the remote catalog."""
    if not _REMOTE_LATEST_VERSION:
        return
    if _version_tuple(VERSION) >= _version_tuple(_REMOTE_LATEST_VERSION):
        return
    dim(f"发现新版本: 当前 v{VERSION},最新 v{_REMOTE_LATEST_VERSION}")
    dim("建议重新获取安装文件,或使用: npx tokenplan-setup@latest")


# 后付费:运行时通过 /v3/models 发现的模型列表(verify 阶段填充)
_POSTPAID_DISCOVERED: Optional[List[str]] = None

# 后付费默认模型的挑选优先级(基于 tokenhub /v1/models 实测列表)
_POSTPAID_PREFERRED = ("glm-5.3", "glm-5.3-flash", "deepseek-v4-pro", "hy4-preview")

# 后付费非聊天能力排除(视频/图像/语音/embedding/音乐/翻译/3D 等;
# 命中的模型不写入聊天类工具,避免淹没模型下拉框)
_POSTPAID_EXCLUDE = re.compile(
    r"video|image|embed|tts|speech|asr|whisper|rerank|dubbing|3d|mt2|-mt-|actor|"
    r"-as-fast|voice|speak|listen|txt2img|caption|ocr|seedream|pixverse|vidu|"
    r"kling|tripo|wand|youtu-vita|hi3d|hy-mt|music|world2|tokenhub-",
    re.I,
)


def discover_postpaid_models(base_url: str, api_key: str) -> Optional[List[str]]:
    """Fetch the live model list from the postpaid /models endpoint.

    Also serves as key verification for the postpaid plan: a 200 with a
    model list means the key is valid. Returns None on any failure.
    """
    global _POSTPAID_DISCOVERED
    try:
        req = urllib.request.Request(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode(errors="ignore"))
        data = payload.get("data") if isinstance(payload, dict) else None
        ids = [
            item["id"]
            for item in (data or [])
            if isinstance(item, dict) and item.get("id")
        ]
        if ids:
            _POSTPAID_DISCOVERED = ids
            return ids
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="ignore")[:400] if exc.fp else ""
        warn(f"API 返回错误 [{exc.code}]: {_format_api_error(body)}")
    except Exception as exc:
        warn(f"连接失败: {exc}")
    return None


# 后付费:用户自选的模型子集(None = 全部聊天模型)
_POSTPAID_SELECTED: Optional[List[str]] = None


def postpaid_chat_models() -> List[str]:
    """Discovered postpaid models filtered to chat capability (raw fallback)."""
    assert _POSTPAID_DISCOVERED is not None
    chat = [m for m in _POSTPAID_DISCOVERED if not _POSTPAID_EXCLUDE.search(m)]
    return chat or list(_POSTPAID_DISCOVERED)


def set_postpaid_selection(models: List[str]) -> List[str]:
    """Restrict the postpaid catalog to a user-chosen subset (validated)."""
    global _POSTPAID_SELECTED
    chat = postpaid_chat_models()
    chosen = [m for m in chat if m in models]  # 保持发现顺序
    if not chosen:
        warn("所选模型均不在发现列表中,保持全部")
        return chat
    dropped = [m for m in models if m not in chat]
    if dropped:
        warn(f"忽略未知模型: {', '.join(dropped)}")
    _POSTPAID_SELECTED = chosen
    return chosen


def choose_postpaid_models() -> None:
    """Interactive model selection for postpaid; Enter/EOF = all chat models."""
    chat = postpaid_chat_models()
    print()
    print("  ── 选择要配置的模型 ──")
    print()
    print("  直接回车 = 全部聊天模型;输入编号(空格/逗号分隔)只配置所选")
    print()
    for i, m in enumerate(chat, 1):
        print(f"     [{i:2d}] {m}")
    print()
    try:
        raw = ask("编号(回车=全部): ")
    except EOFError:
        return
    tokens = [t for t in re.split(r"[\s,，]+", raw) if t]
    if not tokens or raw in {"all", "*", "全部"}:
        return
    picked: List[str] = []
    for tok in tokens:
        if tok.isdigit():
            idx = int(tok)
            if 1 <= idx <= len(chat):
                picked.append(chat[idx - 1])
                continue
        hit = next((m for m in chat if tok == m), None)
        if hit:
            picked.append(hit)
    if picked:
        global _POSTPAID_SELECTED
        _POSTPAID_SELECTED = picked
        ok(f"已选择 {len(picked)} 个模型")


def _postpaid_catalog() -> Optional[Dict[str, object]]:
    """Build a catalog view from the discovered postpaid models (chat-capable only)."""
    if not _POSTPAID_DISCOVERED:
        return None
    if _POSTPAID_SELECTED:
        ids = list(_POSTPAID_SELECTED)
    else:
        ids = postpaid_chat_models()
    preferred = next((m for m in _POSTPAID_PREFERRED if m in ids), ids[0])
    return {
        "default": preferred,
        "display": tuple(f"{mid}: {mid}" for mid in ids),
    }


def get_model_catalog(plan_key: str) -> Dict[str, object]:
    """Remote catalog first (when refreshed), built-in MODEL_CATALOG as fallback.

    Postpaid is special: its model list is discovered live from the API
    (dynamic catalog, no built-in curation); discovery result wins.
    """
    if plan_key == "postpaid":
        discovered = _postpaid_catalog()
        if discovered:
            return discovered
        return MODEL_CATALOG.get(plan_key, {"default": "", "display": ()})
    remote = (_REMOTE_CATALOG or {}).get(plan_key)
    if isinstance(remote, dict) and remote.get("default") and remote.get("display"):
        return remote
    return MODEL_CATALOG.get(plan_key, {"default": "auto", "display": ()})


def get_model_ids(plan_key: str) -> List[str]:
    """Return the canonical model IDs shared by every tool adapter."""
    catalog = get_model_catalog(plan_key)
    result: List[str] = []
    for line in catalog.get("display", ()):
        if ":" not in line:
            continue
        model_id = line.split(":", 1)[1].strip().split(" ", 1)[0]
        if model_id and model_id not in result:
            result.append(model_id)
    return result


def _format_api_error(body: str, limit: int = 160) -> str:
    """Humanize an API error body: prefer the JSON message field, truncate cleanly."""
    msg = body.strip()
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or msg)
                code = err.get("code")
                if code:
                    msg = f"[{code}] {msg}"
    except ValueError:
        pass
    if len(msg) > limit:
        msg = msg[: limit - 1].rstrip() + "…"
    return msg


def verify_api_key(base_url: str, api_key: str, plan: PlanSpec) -> bool:
    """Probe the endpoint with a 1-token chat completion using the plan's default model."""
    if plan.key == "postpaid":
        # 后付费:GET /models 即验证(200+列表 = Key 有效),同时完成模型发现
        spinner = Spinner("验证 API Key 并发现模型...")
        spinner.start()
        ids = discover_postpaid_models(base_url, api_key)
        spinner.stop(success=ids is not None)
        if ids:
            ok(f"Key 有效,发现 {len(ids)} 个可用模型")
            return True
        warn("后付费 Key 验证失败或模型列表获取失败(需联网)")
        return False
    spinner = Spinner("验证 API Key...")
    spinner.start()
    try:
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": get_model_catalog(plan.key)["default"],
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                }
            ).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT)
        spinner.stop(success=True)
        return True
    except urllib.error.HTTPError as exc:
        spinner.stop(success=False)
        body = exc.read().decode(errors="ignore")[:400] if exc.fp else ""
        warn(f"API 返回错误 [{exc.code}]: {_format_api_error(body)}")
        return False
    except Exception as exc:
        spinner.stop(success=False)
        warn(f"连接失败: {exc}")
        return False


def configure_codebuddy(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.codebuddy/models.json (per-model provider entries)."""
    model_ids = get_model_ids(plan.key)
    default_model = str(get_model_catalog(plan.key)["default"])
    write_json(
        cfg_path(".codebuddy", "models.json"),
        {
            "models": [
                {
                    "id": model_id,
                    "name": model_id,
                    "vendor": "Tencent Cloud",
                    "apiKey": api_key,
                    "url": base_url,
                }
                for model_id in model_ids
            ]
        },
    )
    write_json(
        cfg_path(".codebuddy", "settings.json"),
        {
            "env": {
                "CODEBUDDY_API_KEY": api_key,
                "OPENAI_API_KEY": api_key,
                "OPENAI_BASE_URL": base_url,
            },
            "model": default_model,
        },
        merge=True,
    )
    install_codebuddy_shell_env(api_key, base_url)


def configure_claude_code(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.claude/settings.json env block + model slots + tokenplan launcher."""
    if base_url.rstrip("/").endswith("/v1"):
        # 后付费(tokenhub /v1):Anthropic SDK 硬拼 /v1/messages,
        # base 必须写到域名根(不带 /v1),否则会请求 /v1/v1/messages → 404
        anthropic_url = base_url.rstrip("/")[: -len("/v1")]
    else:
        # 套餐版:官方文档规定 ANTHROPIC_BASE_URL = <host>/plan/anthropic
        # (SDK 拼接 /v1/messages 后即 <host>/plan/anthropic/v1/messages,已探活验证)
        anthropic_url = base_url.replace("/plan/v3", "/plan/anthropic")
    catalog = get_model_catalog(plan.key)
    default_model = str(catalog["default"])
    model_ids = get_model_ids(plan.key)
    claude_slots = CLAUDE_MODEL_SLOTS.get(plan.key, {})
    if not claude_slots and plan.key == "postpaid" and model_ids:
        # 后付费无固定槽位映射:从发现列表按能力倾向挑选
        def _pick(*keywords: str) -> str:
            for kw in keywords:
                hit = next((m for m in model_ids if m == kw), "")
                if not hit:
                    hit = next((m for m in model_ids if kw in m), "")
                if hit:
                    return hit
            return model_ids[0]
        claude_slots = {
            "opus": _pick("glm-5.3", "pro", "r1"),
            "sonnet": _pick("glm-5.3", "chat", "v3"),
            "haiku": _pick("flash", "lite", "turbo"),
        }
    env = {
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_BASE_URL": anthropic_url,
        "ANTHROPIC_MODEL": default_model,
        "CLAUDE_CODE_EFFORT_LEVEL": "high",
    }
    if claude_slots:
        env.update(
            {
                "ANTHROPIC_DEFAULT_OPUS_MODEL": claude_slots["opus"],
                "ANTHROPIC_DEFAULT_SONNET_MODEL": claude_slots["sonnet"],
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": claude_slots["haiku"],
            }
        )
    write_json(
        cfg_path(".claude", "settings.json"),
        {
            "env": env,
            "model": default_model,
            "alwaysThinkingEnabled": True,
            "tokenplan": {
                "provider": "anthropic",
                "base_url": anthropic_url,
                "models": model_ids,
            },
        },
        merge=True,
    )
    write_json(
        cfg_path(".claude", "tokenplan-models.json"),
        {
            "provider": "anthropic",
            "base_url": anthropic_url,
            "models": model_ids,
            "default": default_model,
        },
    )
    if IS_WINDOWS:
        install_claude_tokenplan_launcher_win(model_ids)
        return
    launcher = cfg_path(".local", "bin", "claude-tokenplan")
    launcher.write_text(
        "#!/bin/sh\n"
        f"models={' '.join(model_ids)!r}\n"
        "printf 'Token Plan 模型列表:\\n'\n"
        "i=1; for model in $models; do printf '  %s. %s\\n' \"$i\" \"$model\"; i=$((i + 1)); done\n"
        "printf '请选择序号或输入完整模型 ID: '\n"
        "read -r choice\n"
        "case $choice in\n"
        "  ''|*[!0-9]*) model=$choice ;;\n"
        "  *) model=$(printf '%s\\n' $models | sed -n \"${choice}p\") ;;\n"
        "esac\n"
        "[ -n \"$model\" ] || { printf '无效选择\\n' >&2; exit 1; }\n"
        "CLAUDE_CODE_EFFORT_LEVEL=\"${CLAUDE_CODE_EFFORT_LEVEL:-high}\" exec claude --model \"$model\" \"$@\"\n"
    )
    launcher.chmod(0o755)
    install_claude_tokenplan_path()


def patch_hermes_model_routing() -> None:
    """Patch Hermes' model_switch.py so custom providers resolve their own slug."""
    install_dir = Path.home() / ".hermes" / "hermes-agent"
    target = install_dir / "hermes_cli" / "model_switch.py"
    if not target.exists():
        warn("未找到 Hermes 模型切换文件，跳过兼容补丁")
        return
    source = target.read_text()
    old = '            slug = f"custom:{name}"\n            if slug in matches:\n'
    new = '            slug = custom_provider_slug(name, str(entry.get("provider_key") or ""))\n            if slug in matches:\n'
    if old in source:
        backup_file(target)
        target.write_text(source.replace(old, new, 1))
    info("Hermes 模型切换兼容已启用")


def configure_hermes(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.hermes/.env custom provider and patch model routing."""
    patch_hermes_model_routing()
    write_env(
        cfg_path(".hermes", ".env"),
        remove_keys=("TERMINAL_CWD",),
        OPENAI_API_KEY=api_key,
    )
    default_model = get_model_catalog(plan.key)["default"]
    models = tuple(get_model_ids(plan.key))
    config_path = cfg_path(".hermes", "config.yaml")
    backup_file(config_path)
    model_entries = ", ".join(
        f'"{model}": {{}}' for model in models
    )
    config_path.write_text(
        "model:\n"
        f"  default: {default_model}\n"
        "  provider: token-plan\n"
        f"  base_url: {base_url}\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "providers:\n"
        "  token-plan:\n"
        "    name: Token Plan\n"
        f"    api: {base_url}\n"
        "    api_key: ${OPENAI_API_KEY}\n"
        f"    default_model: {default_model}\n"
        "    discover_models: false\n"
        f"    models: {{{model_entries}}}\n"
    )
    info("Hermes 已配置为 Token Plan custom 端点")
    info(f"当前产品线: {plan.display_name}")
    info(f"已写入模型数量: {len(models)}")
    info(f"默认模型: {default_model}")


def get_openai_compatible_default_model(plan_key: str) -> str:
    """Resolve 'auto' defaults to a concrete preferred model for tools that need one."""
    catalog = get_model_catalog(plan_key)
    default_model = str(catalog["default"])
    if default_model != "auto":
        return default_model
    model_ids = get_model_ids(plan_key)
    preferred_models = ("glm-5.2", "deepseek-v4-pro-202606", "hy3")
    return next(
        (model for model in preferred_models if model in model_ids),
        next((model for model in model_ids if model not in {"auto", "glm-5.3"}), default_model),
    )


def configure_openclaw(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.openclaw/openclaw.json provider and .env key."""
    model_ids = get_model_ids(plan.key)
    default_model = get_openai_compatible_default_model(plan.key)
    config_path = cfg_path(".openclaw", "openclaw.json")
    write_env(cfg_path(".openclaw", ".env"), TOKENPLAN_API_KEY=api_key)
    full_model_ids = [f"tencent-tokenplan/{model_id}" for model_id in model_ids]
    write_json(
        config_path,
        {
            "models": {
                "mode": "merge",
                "providers": {
                    "tencent-tokenplan": {
                        "baseUrl": base_url,
                        "apiKey": "${TOKENPLAN_API_KEY}",
                        "api": "openai-completions",
                        "models": [
                            {
                                "id": model_id,
                                "name": model_id,
                                "reasoning": model_id not in {"auto"},
                            }
                            for model_id in model_ids
                        ],
                    }
                },
            },
            "agents": {
                "defaults": {
                    "model": {"primary": f"tencent-tokenplan/{default_model}"},
                    "models": {
                        full_model_id: {
                            "alias": full_model_id.split("/", 1)[1],
                            "agentRuntime": {"id": "openclaw"},
                        }
                        for full_model_id in full_model_ids
                    },
                }
            },
        },
        merge=True,
    )
    info("OpenClaw 已写入 Token Plan 自定义 Provider")


def configure_opencode(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.config/opencode/opencode.json provider entry."""
    model_ids = get_model_ids(plan.key)
    default_model = get_openai_compatible_default_model(plan.key)
    config_dir = cfg_path(".config", "opencode")
    config_path = config_dir / "opencode.json"
    write_json(
        config_path,
        {
            "$schema": "https://opencode.ai/config.json",
            "model": f"tokenplan/{default_model}",
            "provider": {
                "tokenplan": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "Tencent Cloud Token Plan",
                    "options": {
                        "baseURL": base_url,
                        "apiKey": api_key,
                    },
                    "models": {
                        model_id: {"name": model_id}
                        for model_id in model_ids
                    },
                }
            },
        },
        merge=True,
    )
    info("OpenCode 已写入 Token Plan 自定义 Provider")


def _workbuddy_model_entry(
    model_id: str, plan: PlanSpec, base_url: str, api_key: str
) -> Dict[str, object]:
    """Build one WorkBuddy models.json entry (format reverse-engineered
    from a real user's hand-added entry; fields verified against it)."""
    catalog = get_model_catalog(plan.key)
    display = tuple(catalog.get("display", ()))
    # 显示名优先用目录里的友好名;找不到就裸 ID
    friendly = ""
    for line in display:
        if ":" in line and line.split(":", 1)[1].strip().split(" ")[0] == model_id:
            friendly = line.split(":", 1)[0].strip()
            break
    plan_short = plan.display_name.split(" - ")[-1].split("（")[0]
    # 多模态模型(如 deepseek-vision-exp)开图片;其余企业/个人模型按文本对话模型处理
    multimodal = "vision" in model_id.lower()
    return {
        "id": model_id,
        "name": f"TokenPlan{plan_short} / {friendly or model_id}",
        "vendor": "Tencent Cloud Token Plan",
        "url": f"{base_url}/chat/completions",
        "apiKey": api_key,
        "supportsToolCall": True,
        "supportsImages": multimodal,
        "supportsReasoning": True,
        "maxInputTokens": 1000000,
        "maxOutputTokens": 131072,
    }


def configure_workbuddy(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write all plan models into ~/.workbuddy/models.json in one shot.

    WorkBuddy's manual UI adds models one field-form at a time; this
    writes the whole plan catalog at once. User's own entries in the
    list are preserved (merge by id); if WorkBuddy is running we ask
    the user to quit first so it doesn't overwrite the file on exit.
    """
    try:
        running = any(
            proc
            for proc in ("WorkBuddy",)
            if shutil.which("pgrep") and subprocess.run(
                ["pgrep", "-f", proc], capture_output=True
            ).returncode == 0
        )
    except Exception:
        running = False
    if running:
        warn("检测到 WorkBuddy 正在运行;请先完全退出(菜单栏图标 → 退出)后重跑")
        warn("否则 WorkBuddy 退出时会用内存中的旧模型列表覆盖本次写入")
        raise RuntimeError("WorkBuddy 正在运行,请退出后重试")

    entries = [
        _workbuddy_model_entry(m, plan, base_url, api_key)
        for m in get_model_ids(plan.key)
    ]
    write_json(
        cfg_path(".workbuddy", "models.json"),
        entries,
        merge=True,
        merge_key="id",
    )
    ok(f"已写入 {len(entries)} 个模型到 ~/.workbuddy/models.json(原有自建模型已保留)")


def configure_dsh(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.dsh/settings.yaml pi-ai provider and credentials."""
    settings_path = cfg_path(".dsh", "settings.yaml")
    credentials_path = cfg_path(".dsh", ".credentials.yaml")
    patch_path = cfg_path(".dsh", "cordis.patch.yml")
    model_entries = "\n".join(
        f"              - id: {model}\n                name: {model}"
        for model in get_model_ids(plan.key)
    )
    backup_file(settings_path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        "llm-pi-ai:\n"
        "  providers:\n"
        "    tokenplan:\n"
        "      displayName: Tencent Cloud Token Plan\n"
        "      apiKeyEnv: TOKENPLAN_API_KEY\n"
        "      api: openai-completions\n"
        f"      baseURL: {base_url}\n"
        "      models:\n"
        f"{model_entries}\n"
        "agent-default-model:\n"
        "  provider: tokenplan\n"
        f"  model: {get_model_catalog(plan.key)['default']}\n"
    )
    backup_file(credentials_path)
    credentials_path.write_text(
        json.dumps({"TOKENPLAN_API_KEY": api_key}, ensure_ascii=False, indent=2) + "\n"
    )
    _harden(credentials_path)
    backup_file(patch_path)
    patch_path.write_text("[]\n")
    info("DeepSeek Harness 已更新内置 pi-ai Provider 设置")
    warn("若启动时提示 cordis.patch.yml 格式错误，可执行：")
    if IS_WINDOWS:
        info(r"del %USERPROFILE%\.dsh\cordis.patch.yml")
        info("然后重新运行: dsh web")
    else:
        info("rm ~/.dsh/cordis.patch.yml")
        info("然后重新运行: dsh web")
        info("也可以保留文件并执行: printf '%s\\n' '[]' > ~/.dsh/cordis.patch.yml")


def install_codex_shell_env(api_key: str) -> None:
    """Expose TOKENPLAN_API_KEY to Codex via a sourced env file (or setx)."""
    if IS_WINDOWS:
        old_value = query_windows_user_env("TOKENPLAN_API_KEY")
        record_state("setx_keys", {"key": "TOKENPLAN_API_KEY", "old": old_value})
        os.environ["TOKENPLAN_API_KEY"] = api_key
        subprocess.run(
            ["setx", "TOKENPLAN_API_KEY", api_key], capture_output=True, check=False
        )
        info("已写入 Windows 用户环境变量 TOKENPLAN_API_KEY，重新打开终端后生效")
        return
    env_path = cfg_path(".codex", "tokenplan.env")
    write_env(env_path, export=True, TOKENPLAN_API_KEY=api_key)
    record_state("env_files", str(env_path))
    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan Codex API key"
    existing = rc_path.read_text() if rc_path.exists() else ""
    source_line = f'[ -f "{env_path}" ] && source "{env_path}"'
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(existing.rstrip() + f"\n{marker}\n{source_line}\n")
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    os.environ["TOKENPLAN_API_KEY"] = api_key


_ZCODE_PROVIDER_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "tokenplan"))


def _display_name(catalog: Dict[str, object], model_id: str) -> str:
    """Human label for a model id from the catalog display lines."""
    for line in catalog.get("display", ()):
        if ":" not in line:
            continue
        label, mid = line.split(":", 1)
        if mid.strip().split(" ", 1)[0] == model_id:
            return label.strip()
    return model_id


def _read_json_object(path: Path) -> Dict[str, object]:
    """Read a JSON object, tolerating missing/corrupt files (start fresh)."""
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _strip_managed_block(lines: List[str], begin: str, end: str) -> List[str]:
    """Remove an inclusive managed marker block from TOML lines."""
    out: List[str] = []
    inside = False
    for line in lines:
        if line.strip() == begin:
            inside = True
            continue
        if line.strip() == end:
            inside = False
            continue
        if not inside:
            out.append(line)
    return out


def _toml_upsert_root_key(lines: List[str], key: str, value: str) -> List[str]:
    """Set a root-level TOML key (before the first table header), preserving the rest."""
    rendered = f'{key} = "{value}"'
    root_end = len(lines)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("["):
            root_end = i
            break
    for i in range(root_end):
        stripped = lines[i].strip()
        if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
            lines[i] = rendered
            return lines
    lines.insert(root_end, rendered)
    return lines


def _toml_upsert_section(
    lines: List[str], header: str, entries: Dict[str, str]
) -> List[str]:
    """Create or update a [table] section; unknown lines inside are preserved."""
    def _render(k: str, v: object) -> str:
        if isinstance(v, bool):
            return f"{k} = {'true' if v else 'false'}"
        if isinstance(v, (int, float)):
            return f"{k} = {v}"
        return f'{k} = "{v}"'

    rendered_entries = [_render(k, v) for k, v in entries.items()]
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        block = ["", header, *rendered_entries]
        return lines + block
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break
    section = lines[start + 1:end]
    kept: List[str] = []
    handled = set()
    for line in section:
        stripped = line.strip()
        matched = False
        for k, v in entries.items():
            if stripped.startswith(f"{k} ") or stripped.startswith(f"{k}="):
                if k not in handled:
                    kept.append(_render(k, v))
                    handled.add(k)
                matched = True
                break
        if not matched:
            kept.append(line)
    for k, v in entries.items():
        if k not in handled:
            kept.append(_render(k, v))
    return lines[:start + 1] + kept + lines[end:]


def configure_codex(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure Codex CLI against the Token Plan Responses endpoint.

    Codex only supports wire_api = "responses"; Token Plan exposes
    /plan/v3/responses on every site (verified by endpoint probing).
    """
    config_path = cfg_path(".codex", "config.toml")
    default_model = str(get_model_catalog(plan.key)["default"])
    existing_lines = (
        config_path.read_text().splitlines() if config_path.exists() else []
    )
    backup_file(config_path)
    lines = _toml_upsert_root_key(existing_lines, "model_provider", "tokenplan")
    lines = _toml_upsert_root_key(lines, "model", default_model)
    lines = _toml_upsert_section(
        lines,
        "[model_providers.tokenplan]",
        {
            "name": "Tencent Cloud Token Plan",
            "base_url": base_url,
            "wire_api": "responses",
            "env_key": "TOKENPLAN_API_KEY",
        },
    )
    config_path.write_text("\n".join(lines).rstrip() + "\n")
    install_codex_shell_env(api_key)
    info(f"Codex 已配置: {config_path} (model = {default_model})")


def _kimi_home() -> Path:
    home = os.environ.get("KIMI_CODE_HOME")
    return Path(home) if home else HOME / ".kimi-code"


def configure_kimi(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure Kimi Code CLI (~/.kimi-code/config.toml) as an OpenAI-compatible provider.

    Schema (kimi-code 0.40.x): top-level default_provider/default_model must
    appear BEFORE any [table] header (TOML rule); [providers.<id>] carries
    type/base_url/api_key; [models.<id>] requires provider + model +
    max_context_size (display_name optional). Verified end-to-end against
    the Token Plan chat-completions endpoint.
    """
    home = _kimi_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.toml"
    existing_lines = (
        config_path.read_text().splitlines() if config_path.exists() else []
    )
    backup_file(config_path)
    catalog = get_model_catalog(plan.key)
    default_model = str(catalog["default"])
    lines = _toml_upsert_root_key(existing_lines, "default_provider", "tokenplan")
    lines = _toml_upsert_root_key(lines, "default_model", default_model)
    lines = _toml_upsert_section(
        lines,
        "[providers.tokenplan]",
        {
            "type": "openai",
            "base_url": base_url,
            "api_key": api_key,
        },
    )
    for model_id in get_model_ids(plan.key):
        display = _display_name(catalog, model_id)
        lines = _toml_upsert_section(
            lines,
            f"[models.{model_id}]",
            {
                "provider": "tokenplan",
                "model": model_id,
                "display_name": display,
                "max_context_size": 128000,
            },
        )
    config_path.write_text("\n".join(lines).rstrip() + "\n")
    _harden(config_path)
    info(f"Kimi Code 已配置: {config_path} ({len(get_model_ids(plan.key))} 个模型)")


def _grok_home() -> Path:
    home = os.environ.get("GROK_HOME")
    return Path(home) if home else HOME / ".grok"


def configure_grok(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure Grok CLI (~/.grok/config.toml) custom models.

    Grok models are flat [model.<id>] tables; api_backend defaults to
    chat_completions, which Token Plan exposes on every site. Verified
    end-to-end: grok sent requests to <base_url>/chat/completions.
    """
    home = _grok_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.toml"
    existing = config_path.read_text() if config_path.exists() else ""
    backup_file(config_path)
    catalog = get_model_catalog(plan.key)
    # 移除旧的 tokenplan 托管块(模型集合可能变化),再重写
    lines = _strip_managed_block(existing.splitlines(), "# Token Plan models begin", "# Token Plan models end")
    block: List[str] = ["", "# Token Plan models begin"]
    for model_id in get_model_ids(plan.key):
        display = _display_name(catalog, model_id)
        block.append(f"[model.{model_id}]")
        block.append(f'model = "{model_id}"')
        block.append(f'base_url = "{base_url}"')
        block.append(f'name = "{display}"')
        block.append(f'api_key = "{api_key}"')
        block.append("")
    block.append("# Token Plan models end")
    lines = lines + block
    config_path.write_text("\n".join(lines).rstrip() + "\n")
    _harden(config_path)
    info(f"Grok 已配置: {config_path} ({len(get_model_ids(plan.key))} 个模型)")


def _pi_agent_dir() -> Path:
    override = os.environ.get("PI_CODING_AGENT_DIR")
    if override:
        return Path(override)
    config_dir = os.environ.get("PI_CONFIG_DIR")
    base = Path(config_dir) if config_dir else HOME / ".pi"
    return base / "agent"


def configure_pi(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure the Pi coding agent (~/.pi/agent/models.json).

    Provider entry under providers.tokenplan with api openai-completions;
    models need only id (name/context defaults apply). Verified
    end-to-end: pi listed the provider and reached the Token Plan endpoint.
    """
    agent_dir = _pi_agent_dir()
    agent_dir.mkdir(parents=True, exist_ok=True)
    models_path = agent_dir / "models.json"
    data = _read_json_object(models_path)
    backup_file(models_path)
    catalog = get_model_catalog(plan.key)
    models = []
    for model_id in get_model_ids(plan.key):
        entry: Dict[str, object] = {"id": model_id, "name": _display_name(catalog, model_id)}
        models.append(entry)
    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    providers["tokenplan"] = {
        "baseUrl": base_url,
        "api": "openai-completions",
        "apiKey": api_key,
        "models": models,
    }
    data["providers"] = providers
    models_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _harden(models_path)
    info(f"Pi 已配置: {models_path} ({len(models)} 个模型)")


def _zcode_v2_dir() -> Path:
    home = os.environ.get("ZCODE_HOME")
    base = Path(home) if home else HOME / ".zcode"
    return base / "v2"


def configure_zcode(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure ZCode (~/.zcode/v2/config.json) as a custom provider.

    ZCode (z.ai coding client) keeps custom providers in config.json:
    provider.<id> = {name, kind, options{baseURL, apiKey}, models{<id>}}.
    ids must not start with builtin:; a deterministic UUID keeps reruns
    idempotent. Config-layer tested (format cross-confirmed by two
    third-party ZCode tools); the closed client itself is not verified.
    """
    v2 = _zcode_v2_dir()
    v2.mkdir(parents=True, exist_ok=True)
    config_path = v2 / "config.json"
    data = _read_json_object(config_path)
    backup_file(config_path)
    catalog = get_model_catalog(plan.key)
    models: Dict[str, object] = {}
    for model_id in get_model_ids(plan.key):
        models[model_id] = {
            "name": _display_name(catalog, model_id),
            "limit": {"context": 128000, "output": 16384},
        }
    providers = data.get("provider")
    if not isinstance(providers, dict):
        providers = {}
    providers[_ZCODE_PROVIDER_ID] = {
        "name": "Tencent Cloud Token Plan",
        "kind": "openai-compatible",
        "options": {"baseURL": base_url, "apiKey": api_key},
        "models": models,
    }
    data["provider"] = providers
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _harden(config_path)
    info(f"ZCode 已配置: {config_path} ({len(models)} 个模型,客户端未实测)")


CONFIGURATOR_REGISTRY: Dict[str, Callable[[str, str, PlanSpec], None]] = {
    "workbuddy": configure_workbuddy,
    "codebuddy": configure_codebuddy,
    "claude-code": configure_claude_code,
    "hermes": configure_hermes,
    "dsh": configure_dsh,
    "openclaw": configure_openclaw,
    "opencode": configure_opencode,
    "codex": configure_codex,
    "kimi": configure_kimi,
    "grok": configure_grok,
    "pi": configure_pi,
    "zcode": configure_zcode,
}

# doctor 用来判断"我们的配置块是否还在"的签名:工具 key -> (HOME 相对路径, 特征串)。
# 必须与对应 configurator 实际写入的内容保持同步(有测试守着)。
CONFIG_SIGNATURES: Dict[str, Tuple[str, str]] = {
    "codebuddy": (".codebuddy/settings.json", "CODEBUDDY_API_KEY"),
    "claude-code": (".claude/settings.json", "tokenplan"),
    "hermes": (".hermes/config.yaml", "token-plan"),
    "openclaw": (".openclaw/openclaw.json", "tokenplan"),
    "opencode": (".config/opencode/opencode.json", "tokenplan"),
    "dsh": (".dsh/settings.yaml", "tokenplan"),
    "codex": (".codex/config.toml", "[model_providers.tokenplan]"),
    "workbuddy": (".workbuddy/models.json", "Tencent Cloud Token Plan"),
    "kimi": (".kimi-code/config.toml", "[providers.tokenplan]"),
    "grok": (".grok/config.toml", "# Token Plan models begin"),
    "pi": (".pi/agent/models.json", '"tokenplan"'),
    "zcode": (".zcode/v2/config.json", "Tencent Cloud Token Plan"),
}


def probe_config(tool: ToolSpec) -> Optional[bool]:
    """Check whether this installer's config block still exists.

    Returns None when the tool has no auto-config (guided only); True/False
    when the signature file exists and contains/misses our marker.
    """
    signature = CONFIG_SIGNATURES.get(tool.key)
    if not signature:
        return None
    rel_path, marker = signature
    path = HOME / rel_path
    if not path.exists():
        return False
    try:
        return marker in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def configure_tool(tool: ToolSpec, base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Dispatch to the tool's configurator if one is registered."""
    configurator = CONFIGURATOR_REGISTRY.get(tool.key)
    if configurator:
        configurator(base_url, api_key, plan)


def choose_plan() -> PlanSpec:
    """Interactive plan selection (第一步); EOF without --plan is an error."""
    while True:
        print("  ── 第一步：选择套餐 ──")
        print()
        for item in PLAN_CATALOG.values():
            print(f"     [{item.choice}] {item.display_name}")
        print()
        try:
            choice = ask("  请输入数字 (1-4): ")
        except EOFError:
            print()
            print(f"  {YELLOW}❌ 非交互环境无法选择套餐，请用 --plan 指定（如 --plan enterprise-pro）{RESET}")
            raise SystemExit(1)
        plan = PLAN_CATALOG.get(choice)
        if plan:
            print()
            ok(f"已选择: {plan.display_name}")
            if plan.only_note:
                warn(plan.only_note)
            print()
            return plan
        warn("请输入 1-4 之间的有效数字")
        print()


def choose_run_mode() -> bool:
    """Interactive mode selection (第三步); EOF defaults to standard."""
    print("  ── 第三步：选择运行模式 ──")
    print()
    print("  [1] 标准安装 / 补全配置（推荐）")
    print("  [2] 仅修复已有安装的配置")
    print()
    while True:
        try:
            choice = ask("  请输入数字 (1-2): ")
        except EOFError:
            print()
            info("（无输入，默认: 标准安装 / 补全配置）")
            print()
            return False
        if choice == "1" or choice == "":
            print()
            ok("已选择: 标准安装 / 补全配置")
            print()
            return False
        if choice == "2":
            print()
            ok("已选择: 仅修复已有安装的配置")
            warn("此模式不会安装缺失依赖，只会修复已安装工具的配置")
            print()
            return True
        warn("请输入 1 或 2")
        print()


def choose_tools() -> List[ToolSpec]:
    """Interactive tool selection menu (第四步); EOF/empty selects all."""
    print("  ── 第四步：选择工具 ──")
    print()
    print("  输入编号选择，空格分隔；直接回车 = 全部")
    print("  支持输入 all 或 * 选择全部，输入 none 取消选择")
    print()
    for idx, tool in enumerate(TOOLS, start=1):
        adapter = get_backend_adapter(tool)
        tag = {
            "cli": f"{GREEN}自动安装{RESET}",
            "desktop": f"{YELLOW}需先下载{RESET}",
        }.get(tool.backend, f"{WHITE}{adapter.get('label', tool.backend)}{RESET}")
        print(f"     [{idx}] {tool.name:26s} {tag}")
    print()

    while True:
        try:
            raw = ask("  > ")
        except EOFError:
            info("（无输入，默认选择全部工具）")
            print()
            return list(TOOLS)
        if not raw:
            return list(TOOLS)
        tokens = raw.replace(",", " ").split()
        lowered = {token.lower() for token in tokens}
        if lowered & {"all", "*"}:
            return list(TOOLS)
        if lowered & {"none", "0"}:
            return []
        selected: List[ToolSpec] = []
        invalid: List[str] = []
        for token in tokens:
            tool = TOOL_BY_INDEX.get(token) or TOOL_BY_KEY.get(token)
            if tool and tool not in selected:
                selected.append(tool)
            elif not tool:
                invalid.append(token)
        if selected:
            if invalid:
                warn(f"已忽略无效项: {', '.join(invalid)}")
            print()
            return selected
        warn("未识别有效工具编号，请重新输入，或直接回车选择全部")
        print()


def print_usage(tool: ToolSpec, base_url: str, api_key: str) -> None:
    """Print one tool's usage block in the final summary."""
    print(f"  {tool.name}:")
    for line in render_usage_lines(tool, base_url, api_key):
        print(f"    {line}")
    print()


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argparse CLI (subcommands, plan/key/tools/yes/verify-models)."""
    parser = argparse.ArgumentParser(
        prog="tokenplan-setup",
        description="腾讯云 Token Plan 一键接入 CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tokenplan-setup {VERSION}",
        help="显示版本号并退出",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("setup", "repair", "doctor", "uninstall"),
        default="setup",
        help="setup=安装配置（默认），repair=仅修复已安装工具，doctor=仅检查环境，\nuninstall=还原配置并清理安装器写入的修改",
    )
    parser.add_argument(
        "--plan",
        choices=tuple(item.key for item in PLAN_CATALOG.values()),
        help="套餐 key，例如 enterprise-pro",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="直接传入 API Key；不传则交互输入",
    )
    parser.add_argument(
        "--tools",
        help="要处理的工具，支持编号或 key，逗号/空格分隔；不传则交互选择",
    )
    parser.add_argument(
        "--models",
        help="只配置指定模型(逗号分隔;后付费套餐按发现列表校验,其余套餐暂不支持)",
        default=None,
        dest="models",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="尽量跳过确认提示（适合自动化）",
    )
    parser.add_argument(
        "--verify-models",
        dest="verify_models",
        choices=("off", "default", "all"),
        default="default",
        help="配置完成后的端到端验证：off=关闭，default=只验默认模型，all=验证全部模型（默认 default）",
    )
    return parser


def resolve_plan_from_arg(plan_key: Optional[str]) -> Optional[PlanSpec]:
    """Map --plan value (key or choice number) to a PlanSpec."""
    if not plan_key:
        return None
    for item in PLAN_CATALOG.values():
        if plan_key in {item.key, item.choice}:
            return item
    return None


def resolve_tools_from_arg(raw: Optional[str]) -> Optional[List[ToolSpec]]:
    """Parse --tools (indices or keys, comma/space) into ToolSpec list."""
    if raw is None:
        return None
    tokens = raw.replace(",", " ").split()
    if not tokens:
        return []
    lowered = {token.lower() for token in tokens}
    if lowered & {"all", "*"}:
        return list(TOOLS)
    if lowered & {"none", "0"}:
        return []
    selected: List[ToolSpec] = []
    invalid: List[str] = []
    for token in tokens:
        tool = TOOL_BY_INDEX.get(token) or TOOL_BY_KEY.get(token) or TOOL_BY_KEY.get(token.lower())
        if tool and tool not in selected:
            selected.append(tool)
        elif not tool:
            invalid.append(token)
    if invalid:
        warn(f"已忽略无效工具项: {', '.join(invalid)}")
    return selected


def run_doctor(selected_tools: List[ToolSpec]) -> int:
    """Read-only diagnosis: prerequisites plus per-tool install status."""
    clear()
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║           Token Plan 环境诊断               ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    check_prerequisites(selected_tools)
    print()
    print("  ── 工具状态 ──")
    print()
    for tool in selected_tools:
        installed = is_tool_installed(tool)
        configured = probe_config(tool)
        if configured is True and not installed:
            # 配置已写好但应用本体不在(桌面应用手动安装类,如 WorkBuddy)
            status = "未安装应用,但 Token Plan 模型配置已就绪"
        elif installed and configured is True:
            status = "已安装,Token Plan 配置有效"
        elif installed and configured is False:
            status = "已安装,Token Plan 配置缺失"
        elif installed:
            status = "已安装"
        else:
            status = "未安装"
        print(f"  {tool.name}: {status}")
        print(f"    配置位置: {tool.cfg_hint}")
        if installed and configured is False:
            print("    建议: 运行 repair 子命令恢复配置(不会重装程序)")
        if not installed and should_manual_download(tool):
            if tool.backend == "desktop":
                print("    接入方式: 手动获取应用，运行 setup 查看分步引导")
            else:
                print("    将自动安装: 否（当前平台需手动安装）")
            if tool.download_url:
                print(f"    手动安装: {tool.download_url}")
        elif not installed and supports_auto_install(tool):
            print("    将自动安装: 是")
            command = get_install_command(tool)
            if command:
                if isinstance(command, tuple):
                    print(f"    安装命令: {' '.join(command)}")
                else:
                    print(f"    安装命令: {command}")
        elif not installed:
            print("    将自动安装: 否")
        print()
    return 0


def collect_latest_backups() -> Dict[str, str]:
    """Group manifest entries by original path, keeping the newest backup."""
    manifest = BACKUP_DIR / "manifest.jsonl"
    newest: Dict[str, Tuple[str, str]] = {}  # original -> (ts, backup_name)
    if not manifest.exists():
        return {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        original = entry.get("original")
        backup = entry.get("backup")
        ts = entry.get("ts", "")
        if not original or not backup:
            continue
        current = newest.get(original)
        if current is None or ts >= current[0]:
            newest[original] = (ts, backup)
    return {original: backup for original, (_, backup) in newest.items()}


def strip_rc_block(rc_path_str: str, marker: str) -> bool:
    """Remove the marker line plus its single following line from an rc file."""
    rc_path = Path(rc_path_str)
    if not rc_path.exists() or not marker:
        return False
    lines = rc_path.read_text().splitlines()
    if marker not in lines:
        return False
    out: List[str] = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.strip() == marker:
            skip_next = True
            continue
        out.append(line)
    rc_path.write_text("\n".join(out).rstrip() + "\n")
    return True


def run_uninstall(yes: bool) -> int:
    """Restore backups, strip rc blocks, remove generated files and env vars."""
    clear()
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║        Token Plan 接入卸载 / 还原            ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    info("卸载范围：配置还原 + 安装器写入的文件/环境变量/PATH 修改")
    warn("不会卸载工具本体（npm 包、CLI 程序不会被删除）")
    print()

    state = load_state()
    latest = collect_latest_backups()
    rc_blocks = state.get("rc_blocks", [])
    files_written = state.get("files_written", [])
    env_files = state.get("env_files", [])
    setx_keys = state.get("setx_keys", [])

    if not latest and not rc_blocks and not files_written and not env_files and not setx_keys:
        warn("没有可还原的记录（~/.tokenplan-backups 为空或缺少清单）")
        return 0

    print(f"  可还原配置文件: {len(latest)} 个")
    print(f"  可移除 rc 修改: {len(rc_blocks)} 处")
    print(f"  可删除生成文件: {len(files_written) + len(env_files)} 个")
    if IS_WINDOWS:
        print(f"  可还原环境变量: {len(setx_keys)} 个")
    print()

    if not yes:
        confirm = ask("  确认执行卸载还原？(y/n): ")
        if confirm.lower() != "y":
            print(f"\n  {YELLOW}已取消{RESET}")
            return 0
        print()

    print("  ── 还原配置文件 ──")
    print()
    for original, backup_name in latest.items():
        backup = BACKUP_DIR / backup_name
        target = Path(original)
        if backup.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
                ok(f"已还原: {original}")
            except OSError as exc:
                warn(f"还原失败: {original} ({exc})")
        else:
            warn(f"备份文件缺失，跳过: {backup_name}")
    print()

    if rc_blocks:
        print("  ── 移除 rc 文件修改 ──")
        print()
        cleaned = 0
        for block in rc_blocks:
            if isinstance(block, dict) and strip_rc_block(block.get("file", ""), block.get("marker", "")):
                cleaned += 1
        if cleaned:
            ok(f"已清理 {cleaned} 处 rc 修改")
        else:
            info("没有需要清理的 rc 修改")
        print()

    if files_written or env_files:
        print("  ── 删除安装器生成的文件 ──")
        print()
        for path_str in list(files_written) + list(env_files):
            p = Path(path_str)
            if p.exists():
                try:
                    p.unlink()
                    ok(f"已删除: {path_str}")
                except OSError as exc:
                    warn(f"删除失败: {path_str} ({exc})")
        print()

    if IS_WINDOWS and setx_keys:
        print("  ── 还原 Windows 环境变量 ──")
        print()
        for item in setx_keys:
            if not isinstance(item, dict):
                continue
            key = item.get("key", "")
            old = item.get("old")
            if old:
                subprocess.run(["setx", key, old], capture_output=True, check=False)
                ok(f"已还原原值: {key}")
            else:
                subprocess.run(
                    ["reg", "delete", "HKCU\\Environment", "/v", key, "/f"],
                    capture_output=True, check=False,
                )
                ok(f"已删除: {key}")
        print()

    print("  ── 完成 ──")
    print()
    info(f"备份目录保留在 {BACKUP_DIR}，确认无误后可手动删除")
    return 0


def fetch_remote_models(base_url: str, api_key: str) -> Optional[List[str]]:
    """Fetch the model list from the OpenAI-compatible /models endpoint.

    Note: only lkeap (personal plans) and the postpaid tokenhub /v1
    expose /models; the tokenhub plan/v3 domains return 404. Callers
    treat None as "skip the cross-check" — cosmetic only.
    """
    if "/plan/v3" in base_url and "lkeap" not in base_url:
        return None  # tokenhub plan 域不提供 /models(已探活确认)
    try:
        req = urllib.request.Request(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode(errors="ignore"))
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            ids = [item.get("id") for item in data if isinstance(item, dict) and item.get("id")]
            if ids:
                return sorted(ids)
    except Exception:
        pass
    return None


def _test_model_once(
    base_url: str, api_key: str, model: str, retry_no5xx: bool = True,
    prev_error: str = "",
) -> Tuple[bool, str]:
    """Single verification attempt; optionally retry once on 5xx gateway errors."""
    try:
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps(
                {
                    "model": model,
                    "max_tokens": 1,
                    "messages": [{"role": "user", "content": "hi"}],
                }
            ).encode(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT)
        return True, ""
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="ignore")[:400] if exc.fp else ""
        if retry_no5xx and 500 <= exc.code <= 599:
            # 网关瞬时错误(upstream_error 等):稍候重试一次,避免误报
            time.sleep(2)
            return _test_model_once(base_url, api_key, model, retry_no5xx=False,
                                    prev_error=f"HTTP {exc.code}")
        detail = f"HTTP {exc.code}: {_format_api_error(body, limit=100)}"
        if prev_error and 500 <= exc.code <= 599:
            return False, f"{detail}（重试后仍失败,疑似服务端瞬时故障）"
        return False, detail
    except Exception as exc:
        return False, str(exc)


def test_model(base_url: str, api_key: str, model: str) -> Tuple[bool, str]:
    """Verify a model end to end (with one retry on transient 5xx)."""
    return _test_model_once(base_url, api_key, model)


def verify_models(
    base_url: str, api_key: str, plan: PlanSpec, mode: str = "default"
) -> Dict[str, Tuple[bool, str]]:
    """End-to-end verification of the model IDs that were written to configs."""
    catalog_ids = get_model_ids(plan.key)
    default_model = str(get_model_catalog(plan.key)["default"])
    if mode == "all":
        targets = catalog_ids or [default_model]
    else:
        targets = [default_model]
    print("  ── 端到端验证（真实调用 /chat/completions） ──")
    print()
    results: Dict[str, Tuple[bool, str]] = {}
    for model in targets:
        passed, reason = test_model(base_url, api_key, model)
        results[model] = (passed, reason)
        if passed:
            ok(f"{model}")
        else:
            warn(f"{model} — {reason}")
    print()
    failed = [m for m, (p, _) in results.items() if not p]
    if failed:
        warn(f"{len(failed)} 个模型验证失败；配置仍已写入，请检查模型 ID 或套餐权限")
    else:
        ok(f"全部 {len(targets)} 个模型验证通过，配置立即可用")
    print()
    return results


def main() -> None:
    """CLI entry: parse args, verify key, install and configure selected tools."""
    enable_windows_ansi()
    parser = build_arg_parser()
    args = parser.parse_args()
    if args.command == "doctor":
        doctor_tools = resolve_tools_from_arg(args.tools)
        if doctor_tools is None:
            doctor_tools = list(TOOLS)
        run_doctor(doctor_tools)
        return
    if args.command == "uninstall":
        run_uninstall(args.yes)
        return

    clear()
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 一键接入 CLI         ║")
    print("  ║   只需 API Key，其余尽可能自动              ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  命令: setup / repair / doctor / uninstall")
    print(f"  版本: v{VERSION}（默认: setup）")
    print()

    plan = resolve_plan_from_arg(args.plan) or choose_plan()
    base_url = plan.base_url
    key_url = plan.key_url

    print("  ── 第二步：输入 API Key ──")
    print()
    info(f"获取地址: {key_url}")
    print()
    info("建议使用有权限的完整 API Key，粘贴时请避免前后空格")
    print()
    api_key = args.api_key.strip() if args.api_key else ""
    if api_key and len(api_key) < 10:
        print(f"\n  {YELLOW}❌ --api-key 传入的 Key 无效（长度过短），请检查后重试。{RESET}")
        return
    while not api_key:
        try:
            api_key = ask("  请粘贴 API Key: ").strip()
        except EOFError:
            print(f"\n  {YELLOW}未输入 API Key，已取消。{RESET}")
            return
        if not api_key:
            print(f"\n  {YELLOW}未输入 API Key，已取消。{RESET}")
            return
        if len(api_key) < 10:
            warn("API Key 看起来不完整（长度过短），请重新粘贴完整 Key")
            print()
            api_key = ""
            continue
    print()

    if not verify_api_key(base_url, api_key, plan):
        warn("API Key 验证失败，请检查 Key 是否正确")
        print()
        try:
            confirmed = ask("  是否继续？(y/n): ").lower()
        except EOFError:
            confirmed = "n"
        if not args.yes and confirmed != "y":
            return
    else:
        ok("API Key 验证通过")
    print()

    refresh_remote_catalog()
    if _REMOTE_CATALOG:
        info(f"模型目录已更新（远程 {sum(len(p.get('display', ())) for p in _REMOTE_CATALOG.values())} 条）")
    else:
        info("使用内置模型目录（远程目录不可用或未配置）")
    notify_upgrade_available()
    print()

    if plan.key == "postpaid":
        # 后付费:目录即发现结果,无交叉检查
        if not _POSTPAID_DISCOVERED:
            # verify 失败后用户仍选择继续:再试一次发现,失败则中止
            ids = discover_postpaid_models(base_url, api_key)
            if not ids:
                warn("后付费模式需要联网获取模型列表,无法继续")
                return
        chat = postpaid_chat_models()
        ok(f"后付费模型列表已获取（{len(_POSTPAID_DISCOVERED)} 个,其中聊天模型 {len(chat)} 个）")
        if args.models:
            chosen = set_postpaid_selection(
                [t for t in re.split(r"[\s,，]+", args.models) if t]
            )
            ok(f"按 --models 配置 {len(chosen)} 个模型")
        elif not args.yes:
            choose_postpaid_models()
    else:
        remote_models = fetch_remote_models(base_url, api_key)
        if remote_models:
            catalog_ids = get_model_ids(plan.key)
            missing = [m for m in catalog_ids if m not in remote_models]
            if missing:
                warn(f"以下目录模型未出现在 API 模型列表中（可能已下线）: {', '.join(missing)}")
            else:
                ok(f"API 模型列表可用（{len(remote_models)} 个），目录模型全部在列")
    print()

    if args.models and plan.key != "postpaid":
        warn("--models 目前仅支持后付费套餐,已忽略")

    repair_mode = args.command == "repair" or (args.command == "setup" and choose_run_mode())

    selected_tools = resolve_tools_from_arg(args.tools)
    if selected_tools is None:
        # choose_tools handles EOF (non-interactive) by defaulting to all.
        selected_tools = choose_tools()
    if not selected_tools:
        warn("未选择任何工具，脚本已结束")
        return

    prerequisites_ready = check_prerequisites(selected_tools)
    if not prerequisites_ready:
        warn("关键前置条件未满足，请先按上面的提示完成安装，再重新运行本安装器")
        return

    print(f"  ── 正在配置 {len(selected_tools)} 个工具 ──")
    print()

    installed: List[ToolSpec] = []
    failed: List[Tuple[ToolSpec, str]] = []
    skipped: List[ToolSpec] = []

    total = len(selected_tools)
    bar_len = 20

    ensure_npm_bin_on_path()
    for index, tool in enumerate(selected_tools, start=1):
        filled = int((index / total) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  [{bar}] {index}/{total}")
        print(f"  📦 {tool.name}")
        print()

        already_installed = is_tool_installed(tool)

        if should_manual_download(tool):
            # 桌面应用无法自动安装,但配置可写的工具(如 WorkBuddy)仍要写配置:
            # 用户装好应用后打开即用,不需要重跑安装器
            if tool.key in CONFIGURATOR_REGISTRY:
                try:
                    configure_tool(tool, base_url, api_key, plan)
                    installed.append(tool)
                    ok("配置已写入(应用本体需自行下载安装)")
                except Exception as exc:
                    failed.append((tool, str(exc)))
                    warn(f"配置失败: {exc}")
            else:
                skipped.append(tool)
                warn(f"请先下载 {tool.name}")
            if tool.download_url:
                info(f"下载: {tool.download_url}")
            if tool.backend == "desktop" and tool.key not in CONFIGURATOR_REGISTRY:
                info("手动接入步骤:")
                for line in render_usage_lines(tool, base_url, api_key):
                    info(f"  {line}")
            print()
            continue

        if repair_mode and not already_installed:
            skipped.append(tool)
            warn(f"{tool.name} 尚未安装，已跳过修复")
            print()
            continue

        if requires_backend_dependency(tool, "npx") and not shutil.which("npx"):
            failed.append((tool, f"缺少 npx，无法启动 {tool.name}"))
            warn(f"{tool.name} 需要 Node.js / npx（含 npm 的 LTS 版本即可）")
            info("安装地址: https://nodejs.org/en/download")
            print()
            continue

        if not already_installed and supports_auto_install(tool):
            if repair_mode:
                skipped.append(tool)
                warn(f"{tool.name} 未检测到已安装状态，修复模式已跳过安装")
                print()
                continue
            if not install_tool(tool):
                failed.append((tool, "安装失败"))
                print()
                continue
        elif not already_installed and get_install_command(tool):
            if repair_mode:
                skipped.append(tool)
                warn(f"{tool.name} 未检测到已安装状态，修复模式已跳过安装")
                print()
                continue
            failed.append((tool, "当前环境不支持自动安装"))
            warn(f"{tool.name} 无法在当前环境自动安装")
            print()
            continue
        else:
            dim("已安装")

        try:
            configure_tool(tool, base_url, api_key, plan)
            installed.append(tool)
            ok("配置完成")
        except Exception as exc:
            failed.append((tool, str(exc)))
            warn(f"配置失败: {exc}")

        if should_manual_download(tool):
            info(f"打开 {tool.name} → 设置 → 模型")
            info(f"Base URL: {base_url}")
            info(f"API Key:  {mask_secret(api_key)}")
        print()

    print(f"  [{'█' * bar_len}] {total}/{total}")
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║                 配 置 完 成                 ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()

    if repair_mode:
        print("  本次运行采用的是修复模式，只会修复已安装工具的配置。")
        print()
    if installed:
        print(f"  {GREEN}✅ 已配置 {len(installed)} 个工具:{RESET}")
        for tool in installed:
            print(f"       {tool.name}")
            for line in render_usage_lines(tool, base_url, api_key):
                print(f"         {line}")
    if skipped:
        print(f"  {YELLOW}📝 需手动下载 {len(skipped)} 个工具:{RESET}")
        for tool in skipped:
            print(f"       {tool.name} — {tool.download_url or '见使用说明'}")
            if tool.backend == "desktop":
                for line in render_usage_lines(tool, base_url, api_key):
                    print(f"         {line}")
    if failed:
        print(f"  {YELLOW}❌ 失败 {len(failed)} 个工具:{RESET}")
        for tool, reason in failed:
            print(f"       {tool.name} — {reason}")
    if BACKUP_DIR.exists():
        backups = list(BACKUP_DIR.glob("*.bak"))
        if backups:
            print(f"  {WHITE}💾 原有配置已备份到: {BACKUP_DIR}{RESET}")
    if load_state().get("rc_blocks"):
        shell = os.environ.get("SHELL", "")
        rc_name = ".zshrc" if shell.endswith("/zsh") else ".bashrc"
        print(f"  {WHITE}💡 新装命令在新开终端中生效；当前终端可先执行: source ~/{rc_name}{RESET}")
    print()
    print("  ── 如何使用 ──")
    print()

    for tool in installed:
        print_usage(tool, base_url, api_key)

    print(f"  API 端点: {base_url}")
    print(f"  模型参考: {key_url.replace('api-key', '')}")
    print()

    catalog = get_model_catalog(plan.key)
    models = catalog.get("display", ())
    if models:
        count = len(models)
        print(f"  可用模型 ({count}个):")
        for model_line in models:
            print(f"    {model_line}")
        print()

    if installed and args.verify_models != "off":
        verify_models(base_url, api_key, plan, mode=args.verify_models)


if __name__ == "__main__":
    try:
        main()
        if sys.stdin.isatty():
            input("  按回车退出...")
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}已取消{RESET}")
    except EOFError:
        pass
