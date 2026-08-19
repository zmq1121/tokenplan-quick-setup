#!/bin/bash
"exec" "python3" "$0" "$@"
# -*- coding: utf-8 -*-
# 腾讯云 Token Plan — 小白一键接入
# Mac: 双击此文件 | Windows: 右键→Python 打开
import os, sys, json, shutil, subprocess, time, threading
from pathlib import Path
HOME = Path.home()
G,Y,B,R,C,M,W = "\033[32m","\033[33m","\033[36m","\033[0m","\033[35m","\033[35m","\033[37m"
def clear(): print("\033[2J\033[H", end="")
def ok(msg):    print(f"  {G}✓{R} {msg}")
def warn(msg):  print(f"  {Y}⚠{R}  {msg}")
def info(msg):  print(f"  {B}→{R} {msg}")
def title(msg): print(f"\n  {C}{msg}{R}")
def dim(msg):   print(f"  {W}{msg}{R}")
def ask(msg):   return input(f"  {msg}").strip()

# ── 进度条 ──────────────────────────────────────────
class Spinner:
    def __init__(self, msg):
        self.msg = msg
        self.running = False
        self.thread = None
    def _spin(self):
        frames = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        i = 0
        while self.running:
            sys.stdout.write(f"\r  {C}{frames[i%len(frames)]}{R} {self.msg}")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1
    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
    def stop(self, success=True):
        self.running = False
        if self.thread: self.thread.join(timeout=0.3)
        sys.stdout.write("\r" + " " * (len(self.msg) + 10) + "\r")
        sys.stdout.flush()
        if success: ok(self.msg)
        else: warn(self.msg + " (失败)")

def run_with_spinner(cmd, msg):
    spinner = Spinner(msg)
    spinner.start()
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
        spinner.stop(success=result.returncode == 0)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        spinner.stop(success=False)
        return False
    except Exception:
        spinner.stop(success=False)
        return False

# ── 工具定义 ──────────────────────────────────────────
TOOLS = {
    "1": {"key":"codebuddy",   "name":"CodeBuddy",          "type":"cli",     "install":"npm install -g @tencent-ai/codebuddy-code",       "check":"codebuddy"},
    "2": {"key":"claude-code", "name":"Claude Code",         "type":"cli",     "install":"npm install -g @anthropic-ai/claude-code",        "check":"claude"},
    "3": {"key":"codex",       "name":"Codex",               "type":"cli",     "install":"npm install -g @openai/codex@0.80.0",             "check":"codex"},
    "4": {"key":"hermes",      "name":"Hermes Agent",        "type":"cli",     "install":"curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash", "check":"hermes"},
    "5": {"key":"dsh",         "name":"DeepSeek Harness",    "type":"cli",     "install":None,                                              "check":"npx"},
    "6": {"key":"cursor",      "name":"Cursor",              "type":"desktop", "download":"https://cursor.com/downloads"},
    "7": {"key":"windsurf",    "name":"Windsurf",            "type":"desktop", "download":"https://codeium.com/windsurf/download"},
    "8": {"key":"trae",        "name":"TRAE",                "type":"desktop", "download":"https://www.trae.ai/download"},
    "9": {"key":"cline",       "name":"Cline (VS Code 插件)", "type":"plugin",  "install":"code --install-extension saoudrizwan.claude-dev"},
    "10":{"key":"kilo-code",   "name":"Kilo Code",           "type":"plugin",  "install":"code --install-extension kilocode.kilocode"},
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
    elif k == "trae": pass
    elif k in ("cline", "kilo-code"): pass

# ── 主流程 ──────────────────────────────────────────
def main():
    clear()
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 小白一键接入          ║")
    print("  ║   只需 API Key，其余全自动                  ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  ── 第一步：选择套餐 ──")
    print("     [1] 个人版 - 通用")
    print("     [2] 个人版 - Hy（混元）")
    print("     [3] 企业版 - 专业套餐")
    print("     [4] 企业版 - 轻享套餐")
    print()
    choice = ask("  请输入数字 (1-4): ")
    plans = {"1":"personal-general","2":"personal-hy","3":"enterprise-pro","4":"enterprise-light"}
    plan = plans.get(choice, "personal-general")
    if plan.startswith("personal"):
        base_url = "https://api.lkeap.cloud.tencent.com/plan/v3"
    else:
        base_url = "https://tokenhub.tencentmaas.com/plan/v3"
    if plan == "personal-general":
        key_url = "https://console.cloud.tencent.com/tokenhub/tokenplan/common/api-key"
    elif plan == "personal-hy":
        key_url = "https://console.cloud.tencent.com/tokenhub/tokenplan/hy/api-key"
    else:
        key_url = "https://console.cloud.tencent.com/tokenhub/tokenplan-e/api-key"
    print()
    info(f"套餐: {['个人版-通用','个人版-Hy','企业版-专业','企业版-轻享'][int(choice)-1]}")
    if plan in ("enterprise-light", "personal-hy"):
        warn(f"该套餐仅支持 {'Auto' if plan == 'enterprise-light' else 'Hy3'} 模型")
    print()

    print("  ── 第二步：输入 API Key ──")
    info(f"获取地址: {key_url}")
    print()
    api_key = ask("  请粘贴 API Key: ")
    if len(api_key) < 10:
        print(f"\n  {Y}❌ API Key 无效，请重新运行。{R}")
        return
    print()
    ok(f"API Key 已确认 ({api_key[:8]}...)")
    print()

    print("  ── 第三步：选择工具 ──")
    print("  输入编号选择，空格分隔，直接回车 = 全部")
    print()
    for num, t in TOOLS.items():
        tag = {"cli":f"{G}自动安装{R}", "desktop":f"{Y}需先下载{R}", "plugin":f"{C}VS Code{R}"}[t["type"]]
        print(f"     [{num}] {t['name']:22s} {tag}")
    print()
    choices = ask("  > ").split()
    selected = [TOOLS[c] for c in choices if c in TOOLS] if choices else list(TOOLS.values())
    print()

    # 进度摘要
    total = len(selected)
    print(f"  ── 开始配置 {total} 个工具 ──")
    print()

    installed = 0
    for i, tool in enumerate(selected):
        # 进度条
        bar_len = 20
        filled = int((i / total) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  [{bar}] {i}/{total}")
        print(f"  📦 {tool['name']}")
        print()

        exe = tool.get("check")
        already = exe and shutil.which(exe)

        if not already and tool["type"] == "cli" and tool.get("install"):
            run_with_spinner(tool["install"], f"正在安装 {tool['name']}...")
        elif not already and tool["type"] == "desktop":
            warn(f"请先下载 {tool['name']}")
            info(f"下载地址: {tool.get('download', '')}")
            info("下载安装后重新运行本工具即可自动配置")
            print()
            continue
        elif not already and tool["type"] == "plugin" and tool.get("install"):
            run_with_spinner(tool["install"], f"正在安装 {tool['name']}...")
        else:
            ok("已安装")

        try:
            configure(tool, base_url, api_key)
            installed += 1
            ok(f"配置完成")
        except Exception as e:
            warn(f"配置失败: {e}")

        if tool["type"] == "desktop":
            info(f"打开 {tool['name']} → 设置 → 模型，确认已填入:")
            info(f"  Base URL: {base_url}")
            info(f"  API Key:  {api_key[:8]}...")
        print()

    # 完成
    bar = "█" * bar_len
    print(f"  [{bar}] {total}/{total}")
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print(f"  ║  ✅ 完成！{installed}/{total} 个工具已配置       ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  打开你的工具，选择 Token Plan 模型即可开始使用。")
    print()

if __name__ == "__main__":
    try:
        main()
        input("  按回车退出...")
    except KeyboardInterrupt:
        print(f"\n  {Y}已取消{R}")
    except EOFError:
        pass
