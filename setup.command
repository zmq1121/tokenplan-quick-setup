#!/bin/bash
"exec" "python3" "$0" "$@"
# -*- coding: utf-8 -*-
# 腾讯云 Token Plan — 小白一键接入
# Mac: 双击此文件 | Windows: 右键→Python 打开
import json
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


def clear() -> None:
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


def write_env(path: Path, **kv: str) -> None:
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old_lines = path.read_text().splitlines() if path.exists() else []
    keep_lines = [line for line in old_lines if not any(line.startswith(f"{key}=") for key in kv)]
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
        key="codebuddy",
        name="CodeBuddy",
        backend="cli",
        check_exe="codebuddy",
        install_cmd=("npm", "install", "-g", "@tencent-ai/codebuddy-code"),
        start_hint="codebuddy",
        cfg_hint="~/.codebuddy/models.json",
        usage_lines=("终端输入: codebuddy", "输入 /model 切换模型"),
    ),
    ToolSpec(
        key="claude-code",
        name="Claude Code",
        backend="cli",
        check_exe="claude",
        install_cmd=("npm", "install", "-g", "@anthropic-ai/claude-code"),
        start_hint="claude",
        cfg_hint="~/.claude/settings.json",
        usage_lines=("终端输入: claude", "模型已配置，可直接使用"),
    ),
    ToolSpec(
        key="codex",
        name="Codex",
        backend="cli",
        check_exe="codex",
        install_cmd=("npm", "install", "-g", "@openai/codex@0.80.0"),
        start_hint="codex",
        cfg_hint="~/.codex/config.toml",
        usage_lines=("终端输入: codex", "模型已配置，可直接使用"),
    ),
    ToolSpec(
        key="hermes",
        name="Hermes Agent",
        backend="cli",
        check_exe="hermes",
        install_cmd=None,
        start_hint="hermes",
        cfg_hint="~/.hermes/.env",
        usage_lines=(
            "终端输入: hermes",
            "切换模型: 输入 /model → 选择 openai",
            "模型列表: {base_url}",
        ),
    ),
    ToolSpec(
        key="dsh",
        name="DeepSeek Harness",
        backend="cli",
        check_exe="npx",
        start_hint="npx @deepseek-ai/dsh web",
        cfg_hint="~/.dsh/cordis.patch.yml",
        usage_lines=(
            "终端输入: npx @deepseek-ai/dsh web",
            "浏览器打开: http://127.0.0.1:3080",
            "设置 → 模型 → 添加自定义提供方",
        ),
    ),
    ToolSpec(
        key="cursor",
        name="Cursor",
        backend="desktop",
        download_url="https://cursor.com/downloads",
        start_hint="cursor",
        cfg_hint="Cursor 设置文件",
        usage_lines=("打开 Cursor → 设置 → 模型",),
    ),
    ToolSpec(
        key="windsurf",
        name="Windsurf",
        backend="desktop",
        download_url="https://codeium.com/windsurf/download",
        start_hint="windsurf",
        cfg_hint="Windsurf 设置文件",
        usage_lines=("打开 Windsurf → 设置 → 模型",),
    ),
    ToolSpec(
        key="trae",
        name="TRAE",
        backend="desktop",
        download_url="https://www.trae.ai/download",
        start_hint="TRAE.app",
        cfg_hint="TRAE 设置",
        usage_lines=("打开 TRAE → 设置 → 模型",),
    ),
    ToolSpec(
        key="cline",
        name="Cline (VS Code 插件)",
        backend="plugin",
        check_exe="code",
        install_cmd=("code", "--install-extension", "saoudrizwan.claude-dev"),
        start_hint="VS Code → Cline",
        cfg_hint="Cline 插件设置",
        usage_lines=("在 VS Code 中打开 Cline 插件面板",),
    ),
    ToolSpec(
        key="kilo-code",
        name="Kilo Code",
        backend="plugin",
        check_exe="code",
        install_cmd=("code", "--install-extension", "kilocode.kilocode"),
        start_hint="VS Code → Kilo Code",
        cfg_hint="Kilo Code 插件设置",
        usage_lines=("在 VS Code 中打开 Kilo Code 插件面板",),
    ),
)


TOOL_BY_INDEX = {str(i + 1): tool for i, tool in enumerate(TOOLS)}
TOOL_BY_KEY = {tool.key: tool for tool in TOOLS}

TOOL_DEPENDENCY_REGISTRY = {
    "hermes": ("curl",),
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


def is_tool_installed(tool: ToolSpec) -> bool:
    return bool(tool.check_exe and shutil.which(tool.check_exe))


def requires_backend_dependency(tool: ToolSpec, dependency: str) -> bool:
    adapter = get_backend_adapter(tool)
    if dependency in adapter.get("requires", ()):
        return True
    return dependency in TOOL_DEPENDENCY_REGISTRY.get(tool.key, ())


def should_manual_download(tool: ToolSpec) -> bool:
    return bool(get_backend_adapter(tool).get("manual_download"))


def supports_auto_install(tool: ToolSpec) -> bool:
    adapter = get_backend_adapter(tool)
    return bool(adapter.get("auto_install")) and tool.key != "hermes"


def install_tool(tool: ToolSpec) -> bool:
    if not tool.install_cmd:
        return True
    if should_manual_download(tool):
        return False
    if requires_backend_dependency(tool, "code") and not shutil.which("code"):
        warn("未找到 code 命令，无法自动安装 VS Code 插件")
        return False
    return run_command(tool.install_cmd, f"正在安装 {tool.name}...")


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


def check_prerequisites(selected_tools: Iterable[ToolSpec]) -> None:
    print("  ── 前置检查 ──")
    print()

    needs_node = any(
        tool.backend in {"cli", "plugin"}
        and tool.install_cmd
        and any("npm" in part or "npx" in part for part in tool.install_cmd)
        for tool in selected_tools
    )
    needs_code = any(requires_backend_dependency(tool, "code") for tool in selected_tools)
    needs_curl = any(requires_backend_dependency(tool, "curl") for tool in selected_tools)
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
            warn("未安装 npx，DeepSeek Harness 将无法启动")
        if not node_ok or not npm_ok:
            warn("当前环境缺少 Node 依赖，部分工具将跳过自动安装")

    if needs_code:
        if shutil.which("code"):
            ok("VS Code CLI (code)")
        else:
            warn("未找到 VS Code CLI：插件类工具将无法自动安装")

    if needs_curl:
        if shutil.which("curl"):
            ok("curl")
        else:
            warn("未安装 curl，Hermes 自动安装可能失败")

    if shutil.which("git"):
        ok("git")

    print()


def get_model_catalog(plan_key: str) -> Dict[str, object]:
    return MODEL_CATALOG.get(plan_key, {"default": "auto", "display": ()})


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
    write_json(
        cfg_path(".codebuddy", "models.json"),
        {
            "models": [
                {
                    "id": "auto",
                    "name": "Auto",
                    "vendor": "Tencent Cloud",
                    "apiKey": api_key,
                    "url": base_url,
                }
            ]
        },
    )


def configure_claude_code(base_url: str, api_key: str, plan: PlanSpec) -> None:
    anthropic_url = base_url.replace("/plan/v3", "/plan/anthropic")
    write_json(
        cfg_path(".claude", "settings.json"),
        {
            "env": {
                "ANTHROPIC_AUTH_TOKEN": api_key,
                "ANTHROPIC_BASE_URL": anthropic_url,
                "ANTHROPIC_MODEL": get_model_catalog(plan.key)["default"],
            }
        },
        merge=True,
    )


def configure_codex(base_url: str, api_key: str, plan: PlanSpec) -> None:
    path = cfg_path(".codex", "config.toml")
    backup_file(path)
    path.write_text(
        'model_provider = "TencentCloud"\n'
        'model = "auto"\n\n'
        '[model_providers.TencentCloud]\n'
        'name = "TencentCloud"\n'
        f'base_url = "{base_url}"\n'
        'env_key = "Token_Plan_API_KEY"\n'
        'wire_api = "chat"\n'
    )
    write_env(cfg_path(".codex", ".env"), Token_Plan_API_KEY=api_key, OPENAI_BASE_URL=base_url)


def configure_hermes(base_url: str, api_key: str, plan: PlanSpec) -> None:
    hermes_dir = cfg_path(".hermes")
    config_path = hermes_dir / "config.yaml"
    backup_file(config_path)
    default_model = get_model_catalog(plan.key)["default"]
    config_path.write_text(
        "model:\n"
        "  provider: custom\n"
        f"  default: {default_model}\n"
        f"  base_url: {base_url}/chat/completions\n"
        "\n"
    )
    write_env(cfg_path(".hermes", ".env"), OPENAI_API_KEY=api_key)
    info("Hermes 已预置为 TokenPlan 自定义端点")
    info("如果首次启动仍显示 provider 列表，请直接选择 custom 这一项")


def configure_dsh(base_url: str, api_key: str, plan: PlanSpec) -> None:
    path = cfg_path(".dsh", "cordis.patch.yml")
    block = f"""
- insert:
    - id: tokenplan
      name: '@deepseek-ai/dsh-llm-pi-ai'
      config:
        providers:
          - id: tokenplan
            name: Tencent Cloud
            apiKey: \"{api_key}\"
            baseURL: \"{base_url}\"
"""
    write_append_patch(path, block)


CONFIGURATOR_REGISTRY: Dict[str, Callable[[str, str, PlanSpec], None]] = {
    "codebuddy": configure_codebuddy,
    "claude-code": configure_claude_code,
    "codex": configure_codex,
    "hermes": configure_hermes,
    "dsh": configure_dsh,
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


def main() -> None:
    clear()
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 小白一键接入          ║")
    print("  ║   只需 API Key，其余尽可能自动              ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  四步完成：选套餐 → 输 Key → 选模式 → 选工具")
    print()
    print("  外部客户使用建议：")
    print("    1. 请确保在可信网络环境下运行")
    print("    2. 请优先使用官方渠道安装依赖")
    print("    3. 如为企业电脑，建议由 IT 管理员协助安装 Node.js / VS Code")
    print()

    plan = choose_plan()
    base_url = plan.base_url
    key_url = plan.key_url

    print("  ── 第二步：输入 API Key ──")
    print()
    info(f"获取地址: {key_url}")
    print()
    info("建议使用有权限的完整 API Key，粘贴时请避免前后空格")
    print()
    api_key = ask("  请粘贴 API Key: ")
    api_key = api_key.strip()
    if len(api_key) < 10:
        print(f"\n  {YELLOW}❌ API Key 无效，请重新运行。{RESET}")
        return
    print()

    if not verify_api_key(base_url, api_key, plan):
        warn("API Key 验证失败，请检查 Key 是否正确")
        print()
        if ask("  是否继续？(y/n): ").lower() != "y":
            return
    else:
        ok("API Key 验证通过")
    print()

    repair_mode = choose_run_mode()
    selected_tools = choose_tools()
    if not selected_tools:
        warn("未选择任何工具，脚本已结束")
        return

    check_prerequisites(selected_tools)

    print(f"  ── 正在配置 {len(selected_tools)} 个工具 ──")
    print()

    installed: List[ToolSpec] = []
    failed: List[Tuple[ToolSpec, str]] = []
    skipped: List[ToolSpec] = []

    total = len(selected_tools)
    bar_len = 20

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
            failed.append((tool, "缺少 npx，无法启动 DeepSeek Harness"))
            warn("DeepSeek Harness 需要 Node.js / npx")
            print()
            continue

        if tool.key == "hermes" and not already_installed:
            skipped.append(tool)
            warn("Hermes 需要先手动下载或安装")
            info("请参考 Hermes 官方安装文档，再运行本脚本完成配置")
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
        elif not already_installed and tool.install_cmd:
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
        input("  按回车退出...")
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}已取消{RESET}")
    except EOFError:
        pass
