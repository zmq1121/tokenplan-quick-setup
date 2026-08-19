#!/usr/bin/env python3
"""
腾讯云 Token Plan — 小白一键接入

只需一个 API Key。自动下载、安装、配置、启动。

用法:
    python3 setup.py
"""

import os
import sys
import json
import shutil
import subprocess
import platform
from pathlib import Path

HOME = Path.home()
OS = sys.platform  # darwin / linux / win32

# ── 颜色输出 ──────────────────────────────────────────
G = "\033[32m"  # 绿
Y = "\033[33m"  # 黄
B = "\033[36m"  # 青
R = "\033[0m"   # 重置

def ok(msg):    print(f"  {G}✅{R} {msg}")
def warn(msg):  print(f"  {Y}⚠️{R}  {msg}")
def info(msg):  print(f"  {B}📌{R} {msg}")
def step(n, msg): print(f"\n  [{n}] {msg}")

# ── 工具定义 ──────────────────────────────────────────
# 每个工具：名称、安装命令、配置路径、配置写入函数
TOOLS = {
    "codebuddy": {
        "name": "CodeBuddy",
        "desc": "腾讯云 AI 编程助手",
        "type": "cli",
        "install": "npm install -g @tencent-ai/codebuddy-code",
        "check": lambda: shutil.which("codebuddy") is not None,
        "config": {
            "darwin": HOME / ".codebuddy" / "models.json",
            "linux": HOME / ".codebuddy" / "models.json",
            "win32": HOME / "AppData" / "Roaming" / ".codebuddy" / "models.json",
        },
        "write": lambda p, u, k: _write_json(p, [{"id": "auto", "name": "Auto", "vendor": "Tencent Cloud", "apiKey": k, "url": u}]),
    },
    "claude-code": {
        "name": "Claude Code",
        "desc": "Anthropic 终端 AI 编程助手",
        "type": "cli",
        "install": "npm install -g @anthropic-ai/claude-code",
        "check": lambda: shutil.which("claude") is not None,
        "config": {
            "darwin": HOME / ".claude" / "settings.json",
            "linux": HOME / ".claude" / "settings.json",
        },
        "write": lambda p, u, k: _write_json(p, {"env": {"ANTHROPIC_AUTH_TOKEN": k, "ANTHROPIC_BASE_URL": u, "ANTHROPIC_MODEL": "auto"}}, merge=True),
    },
    "codex": {
        "name": "Codex",
        "desc": "OpenAI 终端 AI 编程代理",
        "type": "cli",
        "install": "npm install -g @openai/codex@0.80.0",
        "check": lambda: shutil.which("codex") is not None,
        "config": {
            "darwin": HOME / ".codex" / "config.toml",
            "linux": HOME / ".codex" / "config.toml",
        },
        "write": lambda p, u, k: p.write_text(f'model_provider = "TencentCloud"\nmodel = "auto"\n\n[model_providers.TencentCloud]\nname = "TencentCloud"\nbase_url = "{u}"\nenv_key = "Token_Plan_API_KEY"\nwire_api = "chat"\n'),
    },
    "hermes": {
        "name": "Hermes Agent",
        "desc": "Nous Research 开源 AI 智能体",
        "type": "cli",
        "install": "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash",
        "check": lambda: shutil.which("hermes") is not None,
        "config": {
            "darwin": HOME / ".hermes" / ".env",
            "linux": HOME / ".hermes" / ".env",
        },
        "write": lambda p, u, k: _write_env(p, {"OPENAI_API_KEY": k, "OPENAI_BASE_URL": u}),
    },
    "dsh": {
        "name": "DeepSeek Harness",
        "desc": "DeepSeek AI 智能体框架",
        "type": "cli",
        "install": None,  # npx 不需要安装
        "check": lambda: shutil.which("npx") is not None,
        "config": {
            "darwin": HOME / ".dsh" / "cordis.patch.yml",
            "linux": HOME / ".dsh" / "cordis.patch.yml",
        },
        "write": lambda p, u, k: _write_dsh_config(p, u, k),
        "start": "npx @deepseek-ai/dsh web",
        "start_note": "启动后打开 http://127.0.0.1:3080，在 设置→模型 中完成配置",
    },
    "cursor": {
        "name": "Cursor",
        "desc": "AI 原生代码编辑器",
        "type": "desktop",
        "download": "https://cursor.com/downloads",
        "check": lambda: shutil.which("cursor") is not None or Path("/Applications/Cursor.app").exists(),
        "config": {
            "darwin": HOME / "Library" / "Application Support" / "Cursor" / "User" / "settings.json",
            "linux": HOME / ".config" / "Cursor" / "User" / "settings.json",
        },
        "write": lambda p, u, k: _write_json(p, {"openai.customURL": u, "openai.customAPIKey": k}, merge=True),
        "gui_hint": "打开 Settings → Models，确认 OpenAI API Key 和 Base URL 已填入",
    },
    "windsurf": {
        "name": "Windsurf",
        "desc": "Codeium AI IDE",
        "type": "desktop",
        "download": "https://codeium.com/windsurf/download",
        "check": lambda: shutil.which("windsurf") is not None or Path("/Applications/Windsurf.app").exists(),
        "config": {
            "darwin": HOME / "Library" / "Application Support" / "Windsurf" / "User" / "settings.json",
        },
        "write": lambda p, u, k: _write_json(p, {"codeium.apiEndpoint": u, "codeium.apiKey": k}, merge=True),
        "gui_hint": "打开 Settings，搜索 codeium，确认 API Endpoint 和 API Key 已填入",
    },
    "trae": {
        "name": "TRAE",
        "desc": "字节跳动 AI IDE",
        "type": "desktop",
        "download": "https://www.trae.ai/download",
        "check": lambda: Path("/Applications/TRAE.app").exists(),
        "config": None,
        "gui_hint": "打开设置 → 模型 → 添加模型 → 自定义配置 → 填入 Base URL 和 API Key",
    },
    "cline": {
        "name": "Cline (VS Code 插件)",
        "desc": "VS Code AI 编码助手",
        "type": "plugin",
        "install": "code --install-extension saoudrizwan.claude-dev",
        "check": lambda: (HOME / ".vscode").exists(),
        "config": None,
        "gui_hint": "打开 Cline 插件 → 设置 → API Provider: OpenAI Compatible → 填入 Base URL 和 API Key",
    },
    "kilo-code": {
        "name": "Kilo Code",
        "desc": "轻量 VS Code AI 插件",
        "type": "plugin",
        "install": "code --install-extension kilocode.kilocode",
        "check": lambda: (HOME / ".vscode").exists(),
        "config": None,
        "gui_hint": "打开 Kilo Code 设置 → 填入 Base URL 和 API Key",
    },
}

# ── 配置写入辅助 ──────────────────────────────────────
def _write_json(path, data, merge=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if merge and path.exists():
        existing = json.loads(path.read_text())
        if isinstance(existing, dict):
            existing.update(data)
            data = existing
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def _write_env(path, kv):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [l for l in (path.read_text().split("\n") if path.exists() else [])
             if not any(l.startswith(f"{k}=") for k in kv)]
    for k, v in kv.items():
        lines.append(f"{k}={v}")
    path.write_text("\n".join(l for l in lines if l) + "\n")

def _write_dsh_config(path, base_url, api_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"""# 腾讯云 Token Plan
- insert:
    - id: llm-deepseek
      name: '@deepseek-ai/dsh-llm-pi-ai'
      config:
        providers:
          - id: tokenplan
            name: Tencent Cloud Token Plan
            apiKey: "{api_key}"
            baseURL: "{base_url}"
""")

# ── 安装辅助 ──────────────────────────────────────────
def run(cmd, shell=False):
    """运行命令，返回是否成功"""
    try:
        subprocess.run(cmd, shell=shell, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False

def ensure_npm():
    """确保 npm 可用"""
    if shutil.which("npm"):
        return True
    if shutil.which("node"):
        return True
    warn("需要 Node.js。正在尝试安装...")
    if OS == "darwin":
        if shutil.which("brew"):
            return run(["brew", "install", "node"])
        warn("请先安装 Node.js: https://nodejs.org")
        return False
    return False

def ensure_python():
    return shutil.which("python3") or shutil.which("python")

# ── 主流程 ──────────────────────────────────────────
def main():
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 小白一键接入          ║")
    print("  ║   只需 API Key，其余全自动                  ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()

    # 1. 选版本
    print("  你的 Token Plan 版本？")
    print("    [1] 个人版 (通用/Hy)")
    print("    [2] 企业版 (专业/轻享)")
    edition = input("  > ").strip()
    edition = "personal" if edition == "1" else "enterprise"
    print()

    if edition == "personal":
        openai_url = "https://api.lkeap.cloud.tencent.com/plan/v3"
        anthropic_url = "https://api.lkeap.cloud.tencent.com/plan/anthropic"
    else:
        openai_url = "https://tokenhub.tencentmaas.com/plan/v3"
        anthropic_url = "https://tokenhub.tencentmaas.com/plan/anthropic"

    # 2. 输入 Key
    print("  🔑 请输入 API Key")
    print("     (获取: https://console.cloud.tencent.com/tokenhub/api-key)")
    api_key = input("  > ").strip()
    if len(api_key) < 10:
        print(f"  ❌ Key 无效"); return
    print()

    # 3. 选工具
    print("  你想配置哪些工具？(可多选，用空格分隔，直接回车=全部)")
    print("    [1] CodeBuddy      [2] Claude Code")
    print("    [3] Codex           [4] Hermes Agent")
    print("    [5] DeepSeek Harness")
    print("    [6] Cursor          [7] Windsurf")
    print("    [8] TRAE            [9] Cline")
    print("    [10] Kilo Code")
    print()
    choices = input("  > ").strip().split()
    print()

    # 确定要配置的工具
    selected = []
    if not choices:
        selected = list(TOOLS.keys())
    else:
        idx_map = {"1":"codebuddy","2":"claude-code","3":"codex","4":"hermes","5":"dsh",
                    "6":"cursor","7":"windsurf","8":"trae","9":"cline","10":"kilo-code"}
        for c in choices:
            if c in idx_map:
                selected.append(idx_map[c])

    # 4. 逐个处理
    configured = 0
    for key in selected:
        tool = TOOLS[key]
        step(key, tool["name"])

        # 检查是否已安装
        installed = False
        try:
            installed = tool["check"]()
        except Exception:
            pass

        if not installed:
            # CLI 工具自动安装
            if tool["type"] == "cli" and tool.get("install"):
                if key in ("codebuddy", "claude-code", "codex"):
                    if not ensure_npm():
                        warn(f"无法安装 npm 包，请手动安装: {tool['install']}")
                        continue
                info(f"正在安装 {tool['name']}...")
                if run(tool["install"], shell=True):
                    ok(f"已安装 {tool['name']}")
                else:
                    warn(f"安装失败，请手动执行: {tool['install']}")
                    continue
            elif tool["type"] == "desktop":
                info(f"请先下载 {tool['name']}: {tool['download']}")
                info(f"下载安装后重新运行本工具即可自动配置")
                continue
            elif tool["type"] == "plugin" and tool.get("install"):
                if run(tool["install"], shell=True):
                    ok(f"已安装 {tool['name']}")
                else:
                    warn(f"安装失败，请在 VS Code 扩展商店搜索安装")
                    continue

        # 写配置
        if tool.get("config") and tool["config"].get(OS):
            cfg_path = tool["config"][OS]
            try:
                tool["write"](cfg_path, openai_url if key != "claude-code" else anthropic_url, api_key)
                ok(f"已配置: {cfg_path}")
                configured += 1
            except Exception as e:
                warn(f"配置失败: {e}")
        elif tool.get("gui_hint"):
            info(tool["gui_hint"])
            info(f"  Base URL: {openai_url}")
            info(f"  API Key:  {api_key[:8]}...")

        # 启动提示
        if tool.get("start"):
            info(f"启动命令: {tool['start']}")
            if tool.get("start_note"):
                info(tool["start_note"])

    print()
    print("  ══════════════════════════════════════════")
    print(f"  ✅ 完成！{configured} 个工具已自动配置。")
    print("  ══════════════════════════════════════════")
    print()

if __name__ == "__main__":
    main()