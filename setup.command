#!/bin/bash
"exec" "python3" "$0" "$@"
# -*- coding: utf-8 -*-
# 腾讯云 Token Plan — 小白一键接入
# Mac: 终端运行 | Windows: 右键→Python 打开
import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

HOME = Path.home()
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"
WHITE = "\033[37m"

BACKUP_DIR = HOME / ".tokenplan-backups"
DEFAULT_TIMEOUT = 10


IS_WINDOWS = sys.platform == "win32"


def clear() -> None:
    if IS_WINDOWS:
        os.system("cls")
        return
    print("\033[2J\033[H", end="")


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {BLUE}→{RESET} {msg}")


def dim(msg: str) -> None:
    print(f"  {WHITE}{msg}{RESET}")


def ask(msg: str) -> str:
    return input(f"  {msg}").strip()


def mask_secret(secret: str, visible: int = 4) -> str:
    if not secret:
        return ""
    if len(secret) <= visible:
        return "*" * len(secret)
    return f"{secret[:visible]}…"


class Spinner:
    def __init__(self, msg: str):
        self.msg = msg
        self.running = False
        self.thread = None

    def _spin(self) -> None:
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while self.running:
            sys.stdout.write(f"\r  {CYAN}{frames[i % len(frames)]}{RESET} {self.msg}")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

    def start(self) -> None:
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self, success: bool = True) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.3)
        sys.stdout.write("\r" + " " * (len(self.msg) + 12) + "\r")
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
    choice: str
    key: str
    display_name: str
    base_url: str
    key_url: str
    only_note: str = ""


@dataclass(frozen=True)
class ToolSpec:
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
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"{path.name}.{ts}.bak"
    shutil.copy2(path, backup)
    manifest = BACKUP_DIR / "manifest.jsonl"
    entry = {"backup": backup.name, "original": str(path), "ts": ts}
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return backup


def cfg_path(*parts: str) -> Path:
    p = HOME.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path, data: object, merge: bool = False) -> None:
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
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_env(path: Path, remove_keys: Iterable[str] = (), **kv: str) -> None:
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old_lines = path.read_text().splitlines() if path.exists() else []
    managed_keys = set(kv) | set(remove_keys)
    keep_lines = [
        line for line in old_lines
        if not any(line.startswith(f"{key}=") for key in managed_keys)
    ]
    for key, value in kv.items():
        keep_lines.append(f"{key}={value}")
    path.write_text("\n".join(line for line in keep_lines if line.strip()) + "\n")


def write_append_patch(path: Path, block: str) -> None:
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text() if path.exists() else ""
    if "id: tokenplan" in existing or "tokenplan-quick-setup" in existing:
        return
    content = existing.rstrip()
    if content:
        content += "\n\n"
    content += block.strip() + "\n"
    path.write_text(content)


def run_command(command: Union[Tuple[str, ...], str], message: str) -> bool:
    print(f"  {CYAN}→{RESET} {message}")
    print()
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
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print(f"     {WHITE}{line}{RESET}")
        proc.wait()
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
            "GLM-5: glm-5",
            "GLM-5.1: glm-5.1",
            "GLM-5.2: glm-5.2",
            "Kimi-K2.5: kimi-k2.5 (即将下线)",
        ),
    },
    "personal-hy": {
        "default": "hy3",
        "display": (
            "Hy3: hy3",
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
            "DeepSeek-V4-Flash 原厂: deepseek-v4-flash-202605",
            "Pro 原厂: deepseek-v4-pro-202606",
        ),
    },
    "enterprise-light": {
        "default": "auto",
        "display": (
            "Auto 智能路由: auto",
        ),
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
    "plugin": {
        "label": "VS Code 插件",
        "auto_install": True,
        "manual_download": False,
        "requires": ("code",),
        "usage_template": (
            "在 VS Code 中打开插件面板",
            "配置位置: {cfg_hint}",
        ),
    },
}

def get_backend_adapter(tool: ToolSpec) -> Dict[str, object]:
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


def install_codebuddy_shell_env(api_key: str, base_url: str) -> None:
    """Provide CodeBuddy Code's documented API-key authentication path."""
    if IS_WINDOWS:
        for key, value in (
            ("CODEBUDDY_API_KEY", api_key),
            ("OPENAI_API_KEY", api_key),
            ("OPENAI_BASE_URL", base_url),
        ):
            os.environ[key] = value
            subprocess.run(["setx", key, value], capture_output=True, check=False)
        info("已写入 Windows 用户环境变量，重新打开终端后生效")
        return
    env_path = cfg_path(".codebuddy", "tokenplan.env")
    env_path.write_text(
        f"export CODEBUDDY_API_KEY={json.dumps(api_key)}\n"
        f"export OPENAI_API_KEY={json.dumps(api_key)}\n"
        f"export OPENAI_BASE_URL={json.dumps(base_url)}\n"
    )
    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan CodeBuddy Code API-key authentication"
    existing = rc_path.read_text() if rc_path.exists() else ""
    source_line = f'[ -f "{env_path}" ] && source "{env_path}"'
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(existing.rstrip() + f"\n{marker}\n{source_line}\n")
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
    info(f"npm 全局命令路径已加入: {npm_bin}")


PLUGIN_EXTENSION_IDS = {
    "cline": "saoudrizwan.claude-dev",
    "kilo-code": "kilocode.kilocode",
}


def is_tool_installed(tool: ToolSpec) -> bool:
    if tool.backend == "plugin":
        code = shutil.which("code")
        extension_id = PLUGIN_EXTENSION_IDS.get(tool.key)
        if not code or not extension_id:
            return False
        try:
            result = subprocess.run(
                [code, "--list-extensions"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False
        return extension_id.lower() in {
            line.strip().lower() for line in result.stdout.splitlines()
        }
    return bool(tool.check_exe and shutil.which(tool.check_exe))


def requires_backend_dependency(tool: ToolSpec, dependency: str) -> bool:
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
    if IS_WINDOWS and tool.win_manual:
        return True
    return bool(get_backend_adapter(tool).get("manual_download"))


def supports_auto_install(tool: ToolSpec) -> bool:
    adapter = get_backend_adapter(tool)
    return bool(adapter.get("auto_install")) and bool(get_install_command(tool))


def install_tool(tool: ToolSpec) -> bool:
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
        tool.backend in {"cli", "plugin"}
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
        elif any(requires_backend_dependency(tool, "npx") for tool in selected_tools):
            warn("未安装 npx，DeepSeek Harness 将无法启动")
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


def get_model_catalog(plan_key: str) -> Dict[str, object]:
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


def verify_api_key(base_url: str, api_key: str, plan: PlanSpec) -> bool:
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
        body = exc.read().decode(errors="ignore")[:200] if exc.fp else ""
        warn(f"API 返回错误 [{exc.code}]: {body}")
        return False
    except Exception as exc:
        spinner.stop(success=False)
        warn(f"连接失败: {exc}")
        return False


def configure_codebuddy(base_url: str, api_key: str, plan: PlanSpec) -> None:
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
    anthropic_url = base_url.replace("/plan/v3", "/plan/anthropic")
    catalog = get_model_catalog(plan.key)
    default_model = str(catalog["default"])
    model_ids = get_model_ids(plan.key)
    claude_slots = CLAUDE_MODEL_SLOTS.get(plan.key, {})
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


def configure_dsh(base_url: str, api_key: str, plan: PlanSpec) -> None:
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


CONFIGURATOR_REGISTRY: Dict[str, Callable[[str, str, PlanSpec], None]] = {
    "codebuddy": configure_codebuddy,
    "claude-code": configure_claude_code,
    "hermes": configure_hermes,
    "dsh": configure_dsh,
    "openclaw": configure_openclaw,
    "opencode": configure_opencode,
}


def configure_tool(tool: ToolSpec, base_url: str, api_key: str, plan: PlanSpec) -> None:
    configurator = CONFIGURATOR_REGISTRY.get(tool.key)
    if configurator:
        configurator(base_url, api_key, plan)


def choose_plan() -> PlanSpec:
    while True:
        print("  ── 第一步：选择套餐 ──")
        print()
        for item in PLAN_CATALOG.values():
            print(f"     [{item.choice}] {item.display_name}")
        print()
        choice = ask("  请输入数字 (1-4): ")
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
    print("  ── 第三步：选择运行模式 ──")
    print()
    print("  [1] 标准安装 / 补全配置（推荐）")
    print("  [2] 仅修复已有安装的配置")
    print()
    while True:
        choice = ask("  请输入数字 (1-2): ")
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
            "plugin": f"{CYAN}VS Code{RESET}",
        }.get(tool.backend, f"{WHITE}{adapter.get('label', tool.backend)}{RESET}")
        print(f"     [{idx}] {tool.name:26s} {tag}")
    print()

    while True:
        raw = ask("  > ")
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
    print(f"  {tool.name}:")
    for line in render_usage_lines(tool, base_url, api_key):
        print(f"    {line}")
    print()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tokenplan-setup",
        description="腾讯云 Token Plan 一键接入 CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("setup", "repair", "doctor"),
        default="setup",
        help="setup=安装配置（默认），repair=仅修复已安装工具，doctor=仅检查环境",
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
        "--yes",
        action="store_true",
        help="尽量跳过确认提示（适合自动化）",
    )
    return parser


def resolve_plan_from_arg(plan_key: Optional[str]) -> Optional[PlanSpec]:
    if not plan_key:
        return None
    for item in PLAN_CATALOG.values():
        if plan_key in {item.key, item.choice}:
            return item
    return None


def resolve_tools_from_arg(raw: Optional[str]) -> Optional[List[ToolSpec]]:
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
        status = "已安装" if installed else "未安装"
        print(f"  {tool.name}: {status}")
        print(f"    配置位置: {tool.cfg_hint}")
        if not installed and should_manual_download(tool):
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


def main() -> None:
    enable_windows_ansi()
    parser = build_arg_parser()
    args = parser.parse_args()
    selected_tools = resolve_tools_from_arg(args.tools)
    if selected_tools is None:
        selected_tools = list(TOOLS)
    if args.command == "doctor":
        run_doctor(selected_tools)
        return

    clear()
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 一键接入 CLI         ║")
    print("  ║   只需 API Key，其余尽可能自动              ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  命令: setup / repair / doctor")
    print("  默认: setup")
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
    api_key = args.api_key.strip() if args.api_key else ask("  请粘贴 API Key: ")
    api_key = api_key.strip()
    if len(api_key) < 10:
        print(f"\n  {YELLOW}❌ API Key 无效，请重新运行。{RESET}")
        return
    print()

    if not verify_api_key(base_url, api_key, plan):
        warn("API Key 验证失败，请检查 Key 是否正确")
        print()
        if not args.yes and ask("  是否继续？(y/n): ").lower() != "y":
            return
    else:
        ok("API Key 验证通过")
    print()

    repair_mode = args.command == "repair" or (args.command == "setup" and choose_run_mode())
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
            skipped.append(tool)
            warn(f"请先下载 {tool.name}")
            if tool.download_url:
                info(f"下载: {tool.download_url}")
            info("下载安装后重新运行即可自动完成其余支持工具的配置")
            print()
            continue

        if repair_mode and not already_installed:
            skipped.append(tool)
            warn(f"{tool.name} 尚未安装，已跳过修复")
            print()
            continue

        if requires_backend_dependency(tool, "npx") and not shutil.which("npx"):
            if args.command == "setup":
                warn("检测到缺少 npx，先自动安装 DeepSeek Harness 所需 Node.js 依赖")
                if not install_tool(tool):
                    failed.append((tool, "缺少 npx，无法启动 DeepSeek Harness"))
                    print()
                    continue
            else:
                failed.append((tool, "缺少 npx，无法启动 DeepSeek Harness"))
                warn("DeepSeek Harness 需要 Node.js / npx")
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
            print(f"       {tool.name} — {tool.download_url or ''}")
    if failed:
        print(f"  {YELLOW}❌ 失败 {len(failed)} 个工具:{RESET}")
        for tool, reason in failed:
            print(f"       {tool.name} — {reason}")
    if BACKUP_DIR.exists():
        backups = list(BACKUP_DIR.glob("*.bak"))
        if backups:
            print(f"  {WHITE}💾 原有配置已备份到: {BACKUP_DIR}{RESET}")
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


if __name__ == "__main__":
    try:
        main()
        if sys.stdin.isatty():
            input("  按回车退出...")
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}已取消{RESET}")
    except EOFError:
        pass
