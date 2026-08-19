#!/usr/bin/env python3
"""
腾讯云 Token Plan — 小白一键接入
GitHub Pages: https://zmq1121.github.io/tokenplan-quick-setup

只需 API Key，自动下载+配置所有 AI 工具。
"""

import os, sys, json, shutil, subprocess
from pathlib import Path

HOME = Path.home()
G, Y, B, R = "\033[32m", "\033[33m", "\033[36m", "\033[0m"

def ok(msg):    print(f"  {G}✓{R} {msg}")
def warn(msg):  print(f"  {Y}⚠{R}  {msg}")
def info(msg):  print(f"  {B}→{R} {msg}")
def title(msg): print(f"\n  {msg}")
def ask(msg):   return input(f"  {msg}").strip()

# ── 工具定义 ──────────────────────────────────────────
TOOLS = {
    "1": {"key":"codebuddy",   "name":"CodeBuddy",       "type":"cli",     "install":"npm install -g @tencent-ai/codebuddy-code",       "check":"codebuddy"},
    "2": {"key":"claude-code", "name":"Claude Code",      "type":"cli",     "install":"npm install -g @anthropic-ai/claude-code",        "check":"claude"},
    "3": {"key":"codex",       "name":"Codex",            "type":"cli",     "install":"npm install -g @openai/codex@0.80.0",             "check":"codex"},
    "4": {"key":"hermes",      "name":"Hermes Agent",     "type":"cli",     "install":"curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash", "check":"hermes"},
    "5": {"key":"dsh",         "name":"DeepSeek Harness", "type":"cli",     "install":None,                                              "check":"npx"},
    "6": {"key":"cursor",      "name":"Cursor",           "type":"desktop", "download":"https://cursor.com/downloads"},
    "7": {"key":"windsurf",    "name":"Windsurf",         "type":"desktop", "download":"https://codeium.com/windsurf/download"},
    "8": {"key":"trae",        "name":"TRAE",             "type":"desktop", "download":"https://www.trae.ai/download"},
    "9": {"key":"cline",       "name":"Cline (VS Code)",  "type":"plugin",  "install":"code --install-extension saoudrizwan.claude-dev"},
    "10":{"key":"kilo-code",   "name":"Kilo Code",        "type":"plugin",  "install":"code --install-extension kilocode.kilocode"},
}

# ── 配置写入 ──────────────────────────────────────────
def write_json(path, data, merge=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if merge and path.exists():
        d = json.loads(path.read_text())
        if isinstance(d, dict): d.update(data); data = d
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

def write_env(path, **kv):
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text().split("\n") if path.exists() else []
    lines = [l for l in old if not any(l.startswith(f"{k}=") for k in kv)]
    for k, v in kv.items(): lines.append(f"{k}={v}")
    path.write_text("\n".join(l for l in lines if l) + "\n")

def cfg_path(*parts):
    p = HOME.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p

def configure(tool, base_url, api_key):
    """根据工具类型写入配置"""
    k = tool["key"]
    if k == "codebuddy":
        write_json(cfg_path(".codebuddy", "models.json"), {"models": [{"id":"auto","name":"Auto","vendor":"Tencent Cloud","apiKey":api_key,"url":base_url}]})
    elif k == "claude-code":
        write_json(cfg_path(".claude", "settings.json"), {"env":{"ANTHROPIC_AUTH_TOKEN":api_key,"ANTHROPIC_BASE_URL":base_url,"ANTHROPIC_MODEL":"auto"}}, merge=True)
    elif k == "codex":
        cfg_path(".codex", "config.toml").write_text(f'model_provider = "TencentCloud"\nmodel = "auto"\n\n[model_providers.TencentCloud]\nname = "TencentCloud"\nbase_url = "{base_url}"\nenv_key = "Token_Plan_API_KEY"\nwire_api = "chat"\n')
    elif k == "hermes":
        write_env(cfg_path(".hermes", ".env"), OPENAI_API_KEY=api_key, OPENAI_BASE_URL=base_url)
    elif k == "dsh":
        p = cfg_path(".dsh", "cordis.patch.yml")
        if not p.exists():
            p.write_text(f"- insert:\n    - id: tokenplan\n      name: '@deepseek-ai/dsh-llm-pi-ai'\n      config:\n        providers:\n          - id: tokenplan\n            name: Tencent Cloud\n            apiKey: \"{api_key}\"\n            baseURL: \"{base_url}\"\n")
    elif k == "cursor":
        write_json(cfg_path("Library", "Application Support", "Cursor", "User", "settings.json"), {"openai.customURL":base_url,"openai.customAPIKey":api_key}, merge=True)
    elif k == "windsurf":
        write_json(cfg_path("Library", "Application Support", "Windsurf", "User", "settings.json"), {"codeium.apiEndpoint":base_url,"codeium.apiKey":api_key}, merge=True)
    elif k == "trae":
        pass  # GUI 配置
    elif k in ("cline", "kilo-code"):
        pass  # 插件设置
    ok(f"{tool['name']} — 已配置")

def run(cmd):
    try:
        subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        return True
    except subprocess.CalledProcessError:
        return False

# ── 主流程 ──────────────────────────────────────────
def main():
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 小白一键接入          ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  只需 API Key，其余全自动。")
    print()

    # 1. 选版本
    print("  📋 你的 Token Plan 版本？")
    print("     [1] 个人版 (通用/Hy)")
    print("     [2] 企业版 (专业/轻享)")
    edition = "personal" if ask("  > ") == "1" else "enterprise"
    base_url = "https://api.lkeap.cloud.tencent.com/plan/v3" if edition == "personal" else "https://tokenhub.tencentmaas.com/plan/v3"
    print()

    # 2. 输 Key
    print("  🔑 请输入 API Key")
    print("     (获取: https://console.cloud.tencent.com/tokenhub/api-key)")
    api_key = ask("  > ")
    if len(api_key) < 10:
        print("  ❌ Key 无效"); return
    print()

    # 3. 选工具
    print("  🛠️  你想配置哪些工具？（输入编号，空格分隔，直接回车=全部）")
    for num, t in TOOLS.items():
        tag = {"cli":"自动安装","desktop":"需先下载","plugin":"VS Code"}[t["type"]]
        print(f"     [{num}] {t['name']:20s} ({tag})")
    print()
    choices = ask("  > ").split()
    selected = [TOOLS[c] for c in choices if c in TOOLS] if choices else list(TOOLS.values())
    print()

    # 4. 逐个处理
    installed = 0
    for tool in selected:
        title(f"📦 {tool['name']}")

        # 检查是否已安装
        exe = tool.get("check")
        already = exe and shutil.which(exe)

        if not already:
            if tool["type"] == "cli" and tool.get("install"):
                info(f"正在安装 {tool['name']}...")
                if run(tool["install"]):
                    ok("安装成功")
                else:
                    warn(f"安装失败，请手动执行: {tool['install']}")
                    continue
            elif tool["type"] == "desktop":
                info(f"请先下载: {tool.get('download', '')}")
                info("下载安装后重新运行本工具即可自动配置")
                continue
            elif tool["type"] == "plugin" and tool.get("install"):
                if run(tool["install"]):
                    ok("插件已安装")
                else:
                    warn("安装失败，请在 VS Code 扩展商店搜索安装")
                    continue
        else:
            info("已安装")

        # 写配置
        try:
            configure(tool, base_url, api_key)
            installed += 1
        except Exception as e:
            warn(f"配置失败: {e}")

        # 桌面工具额外提示
        if tool["type"] == "desktop":
            info(f"打开 {tool['name']} → 设置 → 模型，确认 Base URL 和 API Key 已填入")
            info(f"  Base URL: {base_url}")
            info(f"  API Key:  {api_key[:8]}...")

    print()
    print("  ══════════════════════════════════════════")
    print(f"  ✅ 完成！{installed} 个工具已配置。")
    print("  ══════════════════════════════════════════")
    print()

if __name__ == "__main__":
    main()