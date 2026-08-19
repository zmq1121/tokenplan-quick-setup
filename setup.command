#!/bin/bash
"exec" "python3" "$0" "$@"
# -*- coding: utf-8 -*-
# 腾讯云 Token Plan — 小白一键接入
# Mac: 双击此文件 | Windows: 右键→Python 打开
import os, sys, json, shutil, subprocess, time, threading, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime

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

def run_cmd(cmd, msg):
    """运行命令，实时输出，不阻塞 UI"""
    print(f"  {C}→{R} {msg}")
    print()
    try:
        # 使用 Popen 实时输出
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, universal_newlines=True)
        lines = []
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                print(f"     {W}{line}{R}")
                lines.append(line)
        proc.wait()
        success = proc.returncode == 0
        print()
        if success:
            ok(f"{msg} — 完成")
        else:
            warn(f"{msg} — 失败")
        return success, "\n".join(lines), ""
    except Exception as e:
        warn(f"{msg} — 失败: {e}")
        return False, "", str(e)

# ── 前置检查 ──────────────────────────────────────────
def check_prerequisites(tools_needed):
    print("  ── 前置检查 ──")
    print()
    results = {}

    # Python
    results["python"] = True
    ok("Python 3")

    # Node.js + npm
    needs_node = any(t["type"] == "cli" and t.get("install","").startswith("npm") for t in tools_needed)
    if needs_node:
        if shutil.which("node"):
            ok("Node.js")
            results["node"] = True
        else:
            warn("未安装 Node.js，CLI 工具安装会失败")
            info("安装: https://nodejs.org")
            results["node"] = False
        if shutil.which("npm"):
            ok("npm")
            results["npm"] = True
        else:
            results["npm"] = False

    # curl
    needs_curl = any("curl" in (t.get("install") or "") for t in tools_needed)
    if needs_curl:
        if shutil.which("curl"):
            ok("curl")
            results["curl"] = True
        else:
            warn("未安装 curl")
            results["curl"] = False

    # Git (for some tools)
    if shutil.which("git"):
        ok("git")

    print()
    return results

# ── 备份 ────────────────────────────────────────────
BACKUP_DIR = HOME / ".tokenplan-backups"
def backup_file(path):
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"{path.name}.{ts}.bak"
    shutil.copy2(path, backup)
    return backup

# ── 工具定义 ──────────────────────────────────────────
TOOLS = {
    "1": {"key":"codebuddy",   "name":"CodeBuddy",          "type":"cli",     "install":"npm install -g @tencent-ai/codebuddy-code",       "check":"codebuddy", "start":"codebuddy", "cfg":"~/.codebuddy/models.json"},
    "2": {"key":"claude-code", "name":"Claude Code",         "type":"cli",     "install":"npm install -g @anthropic-ai/claude-code",        "check":"claude", "start":"claude", "cfg":"~/.claude/settings.json"},
    "3": {"key":"codex",       "name":"Codex",               "type":"cli",     "install":"npm install -g @openai/codex@0.80.0",             "check":"codex", "start":"codex", "cfg":"~/.codex/config.toml"},
    "4": {"key":"hermes",      "name":"Hermes Agent",        "type":"cli",     "install":"curl -fsSL https://hermes-agent.nousresearch.com/install.sh | HERMES_NO_WIZARD=1 bash", "check":"hermes", "start":"hermes", "cfg":"~/.hermes/.env"},
    "5": {"key":"dsh",         "name":"DeepSeek Harness",    "type":"cli",     "install":None,                                              "check":"npx", "start":"npx @deepseek-ai/dsh web", "cfg":"~/.dsh/cordis.patch.yml"},
    "6": {"key":"cursor",      "name":"Cursor",              "type":"desktop", "download":"https://cursor.com/downloads", "start":"cursor", "cfg":"Cursor 设置文件"},
    "7": {"key":"windsurf",    "name":"Windsurf",            "type":"desktop", "download":"https://codeium.com/windsurf/download", "start":"windsurf", "cfg":"Windsurf 设置文件"},
    "8": {"key":"trae",        "name":"TRAE",                "type":"desktop", "download":"https://www.trae.ai/download", "start":"TRAE.app", "cfg":"TRAE 设置"},
    "9": {"key":"cline",       "name":"Cline (VS Code 插件)", "type":"plugin",  "install":"code --install-extension saoudrizwan.claude-dev", "start":"VS Code → Cline", "cfg":"Cline 插件设置"},
    "10":{"key":"kilo-code",   "name":"Kilo Code",           "type":"plugin",  "install":"code --install-extension kilocode.kilocode", "start":"VS Code → Kilo Code", "cfg":"Kilo Code 插件设置"},
}

# ── 配置写入 ──────────────────────────────────────────
def write_json(path, data, merge=False):
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if merge and path.exists():
        d = json.loads(path.read_text())
        if isinstance(d, dict): d.update(data); data = d
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
def write_env(path, **kv):
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text().split("\n") if path.exists() else []
    lines = [l for l in old if not any(l.startswith(f"{k}=") for k in kv)]
    for k, v in kv.items(): lines.append(f"{k}={v}")
    path.write_text("\n".join(l for l in lines if l) + "\n")
def cfg_path(*parts):
    p = HOME.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
def configure(tool, base_url, api_key, plan):
    k = tool["key"]
    if k == "codebuddy":
        write_json(cfg_path(".codebuddy", "models.json"), {"models": [{"id":"auto","name":"Auto","vendor":"Tencent Cloud","apiKey":api_key,"url":base_url}]})
    elif k == "claude-code":
        write_json(cfg_path(".claude", "settings.json"), {"env":{"ANTHROPIC_AUTH_TOKEN":api_key,"ANTHROPIC_BASE_URL":base_url,"ANTHROPIC_MODEL":"auto"}}, merge=True)
    elif k == "codex":
        p = cfg_path(".codex", "config.toml")
        backup_file(p)
        p.write_text(f'model_provider = "TencentCloud"\nmodel = "auto"\n\n[model_providers.TencentCloud]\nname = "TencentCloud"\nbase_url = "{base_url}"\nenv_key = "Token_Plan_API_KEY"\nwire_api = "chat"\n')
    elif k == "hermes":
        write_env(cfg_path(".hermes", ".env"), OPENAI_API_KEY=api_key, OPENAI_BASE_URL=base_url)
        # 设置默认模型（用 hermes config set 命令）
        default_model = {"personal-general":"tc-code-latest","personal-hy":"hy3","enterprise-pro":"auto","enterprise-light":"auto"}.get(plan, "auto")
        subprocess.run(f"hermes config set model.default openai/{default_model}", shell=True)
        subprocess.run(f"hermes config set model.provider openai", shell=True)
        info("提示: 选 openai 是因为 Token Plan 兼容 OpenAI 协议，实际请求发到腾讯云")
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

# ── 验证 API Key ────────────────────────────────────
def verify_api_key(base_url, api_key, plan):
    """验证 API Key — 使用正确的默认模型"""
    default_model = {"personal-general":"tc-code-latest","personal-hy":"hy3","enterprise-pro":"auto","enterprise-light":"auto"}.get(plan, "auto")
    spinner = Spinner("验证 API Key...")
    spinner.start()
    try:
        req = urllib.request.Request(
            f"{base_url}/chat/completions",
            data=json.dumps({"model":default_model,"max_tokens":1,"messages":[{"role":"user","content":"hi"}]}).encode(),
            headers={"Authorization":f"Bearer {api_key}","Content-Type":"application/json"},
            method="POST"
        )
        resp = urllib.request.urlopen(req, timeout=10)
        spinner.stop(success=True)
        return True
    except urllib.error.HTTPError as e:
        spinner.stop(success=False)
        body = e.read().decode()[:200] if e.fp else ""
        warn(f"API 返回错误 [{e.code}]: {body}")
        return False
    except Exception as e:
        spinner.stop(success=False)
        warn(f"连接失败: {e}")
        return False

# ── 主流程 ──────────────────────────────────────────
def main():
    clear()
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   腾讯云 Token Plan — 小白一键接入          ║")
    print("  ║   只需 API Key，其余全自动                  ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print("  三步完成：选套餐 → 输 Key → 选工具")
    print()

    # 1. 选套餐
    print("  ── 第一步：选择套餐 ──")
    print()
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
    plan_names = ["个人版-通用","个人版-Hy","企业版-专业","企业版-轻享"]
    ok(f"已选择: {plan_names[int(choice)-1]}")
    if plan in ("enterprise-light", "personal-hy"):
        warn(f"该套餐仅支持 {'Auto' if plan == 'enterprise-light' else 'Hy3'} 模型")
    print()

    # 2. 输 Key
    print("  ── 第二步：输入 API Key ──")
    print()
    info(f"获取地址: {key_url}")
    print()
    api_key = ask("  请粘贴 API Key: ")
    if len(api_key) < 10:
        print(f"\n  {Y}❌ API Key 无效，请重新运行。{R}")
        return
    print()

    # 验证 Key
    if not verify_api_key(base_url, api_key, plan):
        warn("API Key 验证失败，请检查 Key 是否正确")
        print()
        if ask("  是否继续？(y/n): ").lower() != "y":
            return
    else:
        ok("API Key 验证通过 ✓")
    print()

    # 3. 选工具
    print("  ── 第三步：选择工具 ──")
    print()
    print("  输入编号选择，空格分隔，直接回车 = 全部")
    print()
    for num, t in TOOLS.items():
        tag = {"cli":f"{G}自动安装{R}", "desktop":f"{Y}需先下载{R}", "plugin":f"{C}VS Code{R}"}[t["type"]]
        print(f"     [{num}] {t['name']:22s} {tag}")
    print()
    choices = ask("  > ").split()
    selected = [TOOLS[c] for c in choices if c in TOOLS] if choices else list(TOOLS.values())
    print()

    # 前置检查
    check_prerequisites(selected)

    # 进度条
    total = len(selected)
    print(f"  ── 正在配置 {total} 个工具 ──")
    print()

    installed = []
    failed = []
    skipped = []

    for i, tool in enumerate(selected):
        bar_len = 20
        filled = int(((i+1) / total) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  [{bar}] {i+1}/{total}")
        print(f"  📦 {tool['name']}")
        print()

        exe = tool.get("check")
        already = exe and shutil.which(exe)

        if not already and tool["type"] == "cli" and tool.get("install"):
            success, out, err = run_cmd(tool["install"], f"正在安装 {tool['name']}...")
            if not success:
                failed.append((tool, "安装失败"))
                warn(f"安装失败，请手动执行: {tool['install']}")
                print()
                continue
        elif not already and tool["type"] == "desktop":
            skipped.append((tool, "需先下载"))
            warn(f"请先下载 {tool['name']}")
            info(f"下载: {tool.get('download', '')}")
            info("下载安装后重新运行即可自动配置")
            print()
            continue
        elif not already and tool["type"] == "plugin" and tool.get("install"):
            success, out, err = run_cmd(tool["install"], f"正在安装 {tool['name']}...")
            if not success:
                failed.append((tool, "安装失败"))
                print()
                continue
        else:
            dim("已安装")

        try:
            configure(tool, base_url, api_key, plan)
            installed.append(tool)
            ok(f"配置完成")
        except Exception as e:
            failed.append((tool, str(e)))
            warn(f"配置失败: {e}")

        if tool["type"] == "desktop":
            info(f"打开 {tool['name']} → 设置 → 模型")
            info(f"  Base URL: {base_url}")
            info(f"  API Key:  {api_key[:8]}...")
        print()

    # 最终汇总
    bar = "█" * bar_len
    print(f"  [{bar}] {total}/{total}")
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print(f"  ║           配 置 完 成                       ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    if installed:
        print(f"  {G}✅ 已配置 {len(installed)} 个工具:{R}")
        for t in installed:
            start = t.get('start', '')
            cfg = t.get('cfg', '')
            print(f"       {t['name']}")
            if start: print(f"         启动: {start}")
            if cfg: print(f"         配置: {cfg}")
    if skipped:
        print(f"  {Y}📝 需手动下载 {len(skipped)} 个工具:{R}")
        for t, reason in skipped:
            print(f"       {t['name']} — {t.get('download','')}")
    if failed:
        print(f"  {Y}❌ 失败 {len(failed)} 个工具:{R}")
        for t, reason in failed:
            print(f"       {t['name']} — {reason}")
    if BACKUP_DIR.exists():
        backups = list(BACKUP_DIR.glob("*.bak"))
        if backups:
            print(f"  {W}💾 原有配置已备份到: {BACKUP_DIR}{R}")
    print()
    print("  ── 如何使用 ──")
    print()
    for t in installed:
        name = t['name']
        start = t.get('start', '')
        if name == 'Hermes Agent':
            print(f"  {name}:")
            print(f"    终端输入: hermes"  )
            print(f"    切换模型: 输入 /model → 选择 openai（Token Plan 兼容 OpenAI 协议，非 OpenAI 账号）")
            print(f"    模型列表: {base_url.replace('/plan/v3','')}"  )
            print()
        elif name == 'Claude Code':
            print(f"  {name}:")
            print(f"    终端输入: claude"  )
            print(f"    模型已配置，直接使用")
            print()
        elif name == 'CodeBuddy':
            print(f"  {name}:")
            print(f"    终端输入: codebuddy"  )
            print(f"    输入 /model 切换模型")
            print()
        elif name == 'Codex':
            print(f"  {name}:")
            print(f"    终端输入: codex"  )
            print(f"    模型已配置，直接使用")
            print()
        elif name == 'DeepSeek Harness':
            print(f"  {name}:")
            print(f"    终端输入: npx @deepseek-ai/dsh web"  )
            print(f"    浏览器打开 http://127.0.0.1:3080")
            print(f"    设置 → 模型 → 添加自定义提供方")
            print()
        elif start:
            print(f"  {name}: 启动命令: {start}")
            print()
    print(f"  API 端点: {base_url}")
    print()

if __name__ == "__main__":
    try:
        main()
        input("  按回车退出...")
    except KeyboardInterrupt:
        print(f"\n  {Y}已取消{R}")
    except EOFError:
        pass
