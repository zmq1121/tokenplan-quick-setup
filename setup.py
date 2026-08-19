#!/usr/bin/env python3
"""
腾讯云 Token Plan — 一键接入工具

只需 API Key，自动检测并配置所有已安装的 AI 工具。

用法:
    python3 setup.py                    # 交互模式
    python3 setup.py enterprise KEY     # 命令行模式
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

HOME = Path.home()

# ── 工具检测规则 ──────────────────────────────────────
TOOLS = {
    "codebuddy": {
        "name": "CodeBuddy",
        "check": lambda: shutil.which("codebuddy") is not None,
        "config": {
            "darwin": HOME / ".codebuddy" / "models.json",
            "linux": HOME / ".codebuddy" / "models.json",
            "win32": HOME / "AppData" / "Roaming" / ".codebuddy" / "models.json",
        },
        "writer": "write_json_config",
        "format": "json",
    },
    "claude-code": {
        "name": "Claude Code",
        "check": lambda: shutil.which("claude") is not None,
        "config": {
            "darwin": HOME / ".claude" / "settings.json",
            "linux": HOME / ".claude" / "settings.json",
        },
        "writer": "write_claude_config",
        "format": "json",
    },
    "codex": {
        "name": "Codex",
        "check": lambda: shutil.which("codex") is not None,
        "config": {
            "darwin": HOME / ".codex" / "config.toml",
            "linux": HOME / ".codex" / "config.toml",
        },
        "writer": "write_codex_config",
        "format": "toml",
    },
    "hermes": {
        "name": "Hermes Agent",
        "check": lambda: shutil.which("hermes") is not None,
        "config": {
            "darwin": HOME / ".hermes" / ".env",
            "linux": HOME / ".hermes" / ".env",
        },
        "writer": "write_env_config",
        "format": "env",
    },
    "cursor": {
        "name": "Cursor",
        "check": lambda: shutil.which("cursor") is not None or Path("/Applications/Cursor.app").exists(),
        "gui": True,
    },
    "windsurf": {
        "name": "Windsurf",
        "check": lambda: shutil.which("windsurf") is not None or Path("/Applications/Windsurf.app").exists(),
        "gui": True,
    },
    "trae": {
        "name": "TRAE",
        "check": lambda: Path("/Applications/TRAE.app").exists(),
        "gui": True,
    },
    "dsh": {
        "name": "DeepSeek Harness",
        "check": lambda: shutil.which("dsh") is not None,
        "gui": True,
    },
    "cline": {
        "name": "Cline (VS Code)",
        "check": lambda: (HOME / ".vscode").exists(),
        "gui": True,
    },
    "kilo-code": {
        "name": "Kilo Code",
        "check": lambda: (HOME / ".vscode").exists(),
        "gui": True,
    },
}

# ── 配置写入 ──────────────────────────────────────────
def write_json_config(path, base_url, api_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = {"models": [{"id": "auto", "name": "Auto", "vendor": "Tencent Cloud", "apiKey": api_key, "url": base_url}]}
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

def write_claude_config(path, base_url, api_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    cfg = json.loads(path.read_text()) if path.exists() else {}
    cfg.setdefault("env", {}).update({"ANTHROPIC_AUTH_TOKEN": api_key, "ANTHROPIC_BASE_URL": base_url, "ANTHROPIC_MODEL": "auto"})
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))

def write_codex_config(path, base_url, api_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'model_provider = "TencentCloud"\nmodel = "auto"\n\n[model_providers.TencentCloud]\nname = "TencentCloud"\nbase_url = "{base_url}"\nenv_key = "Token_Plan_API_KEY"\nwire_api = "chat"\n')

def write_env_config(path, base_url, api_key):
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [l for l in (path.read_text().split("\n") if path.exists() else []) if not l.startswith(("OPENAI_API_KEY=", "OPENAI_BASE_URL="))]
    lines += [f"OPENAI_API_KEY={api_key}", f"OPENAI_BASE_URL={base_url}"]
    path.write_text("\n".join(l for l in lines if l) + "\n")

# ── 主流程 ──────────────────────────────────────────
def main():
    # 命令行模式
    if len(sys.argv) >= 3:
        edition = sys.argv[1]
        api_key = sys.argv[2]
        if edition not in ("personal", "enterprise") or len(api_key) < 10:
            print("用法: python3 setup.py <personal|enterprise> <API_KEY>")
            sys.exit(1)
    else:
        edition = None
        api_key = None

    print()
    print("  ╔══════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 一键接入          ║")
    print("  ╚══════════════════════════════════════════╝")
    print()

    # 检测工具
    print("  🔍 扫描已安装的 AI 工具...")
    platform = sys.platform if sys.platform in ("darwin", "linux") else "win32"
    auto_tools = []
    gui_tools = []

    for key, tool in TOOLS.items():
        try:
            if tool["check"]():
                if tool.get("gui"):
                    gui_tools.append(tool["name"])
                else:
                    auto_tools.append((key, tool))
        except Exception:
            pass

    if not auto_tools and not gui_tools:
        print("  ⚠️  未检测到工具。请先安装 AI 工具后再运行。")
        return

    if auto_tools:
        print(f"  ✅ 可自动配置: {len(auto_tools)} 个")
        for _, t in auto_tools:
            print(f"       - {t['name']}")
    if gui_tools:
        print(f"  📝 需手动配置: {len(gui_tools)} 个")
        for n in gui_tools:
            print(f"       - {n}")
    print()

    # 选版本
    if not edition:
        print("  你的 Token Plan 版本？")
        print("    [1] 个人版")
        print("    [2] 企业版")
        edition = "personal" if input("  > ").strip() == "1" else "enterprise"
        print()

    if edition == "personal":
        url = "https://api.lkeap.cloud.tencent.com/plan/v3"
        a_url = "https://api.lkeap.cloud.tencent.com/plan/anthropic"
    else:
        url = "https://tokenhub.tencentmaas.com/plan/v3"
        a_url = "https://tokenhub.tencentmaas.com/plan/anthropic"

    # 输 Key
    if not api_key:
        print("  🔑 请输入 API Key")
        print("     (获取: https://console.cloud.tencent.com/tokenhub/api-key)")
        api_key = input("  > ").strip()
        print()

    if len(api_key) < 10:
        print("  ❌ Key 无效")
        return

    # 自动配置
    if auto_tools:
        print("  ⚙️  正在自动配置...")
        for key, tool in auto_tools:
            cfg_path = tool["config"].get(platform)
            if not cfg_path:
                continue
            try:
                globals()[tool["writer"]](cfg_path, url, api_key)
                print(f"  ✅ {tool['name']}")
            except Exception as e:
                print(f"  ❌ {tool['name']}: {e}")
        print()

    # GUI 提示
    if gui_tools:
        print("  📝 以下工具需手动配置，请打开对应工具设置：")
        print(f"     Base URL:  {url}")
        print(f"     API Key:   {api_key[:8]}...")
        for n in gui_tools:
            print(f"     → {n}")
        print()

    print("  ══════════════════════════════════════════")
    print("  ✅ 完成！打开工具，选择模型即可使用。")
    print()

if __name__ == "__main__":
    main()