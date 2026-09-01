#!/usr/bin/env python3
"""tokenplan-quick-setup 回归测试套件(零依赖,单命令运行)。

用法:
    python3 tests/run_tests.py            # 全部测试
    python3 tests/run_tests.py codex      # 只跑名称含 codex 的组

加载方式说明:setup.command 是 bash/python polyglot 单文件,这里用
exec 加载它(禁用 main 入口),与真实运行路径一致,不复制代码。
"""
import contextlib
import io
import json
import re
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "setup.command"
NPM_LIB = REPO / "npm" / "lib" / "setup.command"
NPM_PKG = REPO / "npm" / "package.json"

# ---------------------------------------------------------------------------
# 加载被测模块

FAILS: list = []
PASSES: list = []


def load_module(windows: bool = False):
    src = SCRIPT.read_text(encoding="utf-8")
    src = src.replace("if __name__ == \"__main__\":", "if False:")
    if windows:
        src = src.replace('IS_WINDOWS = sys.platform == "win32"', "IS_WINDOWS = True", 1)
    mod = types.ModuleType("setup_under_test")
    exec(compile(src, str(SCRIPT), "exec"), mod.__dict__)
    return mod


def check(name: str, cond: bool) -> None:
    mark = "✓" if cond else "✗"
    print(f"  {mark} {name}")
    (PASSES if cond else FAILS).append(name)


def sandbox(mod):
    """Redirect module state into a temp home; returns the temp dir."""
    tmp = Path(tempfile.mkdtemp())
    mod.HOME = tmp
    mod.BACKUP_DIR = tmp / ".tokenplan-backups"
    mod.STATE_PATH = mod.BACKUP_DIR / "state.json"
    return tmp


# ---------------------------------------------------------------------------
# 测试组: 注册表完整性

def test_registry():
    mod = load_module()
    check("17 个工具注册", len(mod.TOOLS) == 17)
    check("编号 1-6 为已验证工具(顺序稳定)",
          [t.key for t in mod.TOOLS[:6]] ==
          ["hermes", "codebuddy", "claude-code", "opencode", "openclaw", "dsh"])
    check("索引 1-17 连续", sorted(mod.TOOL_BY_INDEX, key=int) == [str(i) for i in range(1, 18)])
    check("TOOL_BY_KEY 与 TOOLS 一致",
          set(mod.TOOL_BY_KEY) == {t.key for t in mod.TOOLS})
    check("每个配置器都有对应工具 key",
          set(mod.CONFIGURATOR_REGISTRY) <= set(mod.TOOL_BY_KEY))
    check("plugin 工具都有扩展 ID",
          all(t.key in mod.PLUGIN_EXTENSION_IDS for t in mod.TOOLS if t.backend == "plugin"))
    check("backend 全部已注册", all(t.backend in mod.BACKEND_REGISTRY for t in mod.TOOLS))


def test_registry_windows():
    mod = load_module(windows=True)
    for key, first in [("codex", "npm"), ("kilo-cli", "npm"),
                       ("kilo-code", "code"), ("cline", "code")]:
        cmd = mod.get_install_command(mod.TOOL_BY_KEY[key])
        check(f"Win: {key} 安装命令以 {first} 开头", cmd is not None and cmd[0] == first)
    check("Win: hermes 不自动安装", mod.get_install_command(mod.TOOL_BY_KEY["hermes"]) is None)
    check("Win: 桌面工具走手动下载",
          all(mod.should_manual_download(mod.TOOL_BY_KEY[k])
              for k in ("cursor", "trae", "workbuddy", "qclaw", "copaw")))


# ---------------------------------------------------------------------------
# 测试组: TOML 手术 + Codex 配置器

def test_toml_surgery():
    mod = load_module()
    U, S = mod._toml_upsert_root_key, mod._toml_upsert_section
    entries = {"name": "T", "base_url": "https://x", "wire_api": "responses",
               "env_key": "TOKENPLAN_API_KEY"}

    lines = S(U(U([], "model_provider", "tokenplan"), "model", "glm-5.2"),
              "[model_providers.tokenplan]", entries)
    text = "\n".join(lines)
    check("TOML: 全新生成含根键与表", "model_provider" in text and "[model_providers.tokenplan]" in text)
    check("TOML: 根键位于表头之前", text.index("model_provider") < text.index("["))

    existing = ['model = "gpt-5"', 'approval_mode = "on-request"', "",
                "[model_providers.openai]", 'name = "OpenAI"', "",
                '[projects."work"]', 'trust_level = "trusted"']
    lines = U(list(existing), "model_provider", "tokenplan")
    lines = U(lines, "model", "glm-5.2")
    lines = S(lines, "[model_providers.tokenplan]", entries)
    text = "\n".join(lines)
    check("TOML: 未知根键保留", "approval_mode" in text)
    check("TOML: 用户 provider 保留", "model_providers.openai" in text)
    check("TOML: 其它表保留", "trust_level" in text)
    check("TOML: model 值唯一替换", text.count("model = ") == 1 and 'model = "glm-5.2"' in text)

    again = S(list(lines), "[model_providers.tokenplan]", entries)
    check("TOML: 幂等无重复表头", "\n".join(again).count("[model_providers.tokenplan]") == 1)


def test_codex_config():
    mod = load_module()
    tmp = sandbox(mod)
    plan = mod.PLAN_CATALOG["3"]
    base, key = "https://tokenhub.tencentmaas.com/plan/v3", "sk-test-1234567890"

    with contextlib.redirect_stdout(io.StringIO()):
        mod.configure_codex(base, key, plan)
    cfg = tmp / ".codex" / "config.toml"
    text = cfg.read_text()
    check("Codex: config.toml 生成", cfg.exists())
    check("Codex: wire_api=responses", 'wire_api = "responses"' in text)
    check("Codex: env 文件权限 600", (tmp / ".codex" / "tokenplan.env").stat().st_mode & 0o777 == 0o600)

    # 保留用户已有配置
    cfg.write_text('model = "gpt-5"\n\n[model_providers.openai]\nname = "OpenAI"\nbase_url = "https://api.openai.com/v1"\n')
    with contextlib.redirect_stdout(io.StringIO()):
        mod.configure_codex(base, key, plan)
    text = cfg.read_text()
    check("Codex: 用户 provider 保留", "model_providers.openai" in text)
    check("Codex: 我们的节共存", "model_providers.tokenplan" in text)

    before = text
    with contextlib.redirect_stdout(io.StringIO()):
        mod.configure_codex(base, key, plan)
    check("Codex: 幂等", cfg.read_text() == before)


# ---------------------------------------------------------------------------
# 测试组: 备份与卸载生命周期

def test_uninstall():
    mod = load_module()
    tmp = sandbox(mod)

    cfg = tmp / ".claude" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{"user": "original"}')
    mod.backup_file(cfg)
    cfg.write_text('{"env": {"TOKEN": "new"}}')

    rc = tmp / ".bashrc"
    rc.write_text("export EDITOR=vim\n")
    marker = "# Token Plan Claude model selector"
    rc.write_text(rc.read_text() + f"\n{marker}\nexport PATH=\"{tmp}/bin:$PATH\"\n")
    mod.record_state("rc_blocks", {"file": str(rc), "marker": marker})

    launcher = tmp / "bin" / "claude-tokenplan"
    launcher.parent.mkdir(parents=True)
    launcher.write_text("#!/bin/sh\n")
    mod.record_state("files_written", str(launcher))

    with contextlib.redirect_stdout(io.StringIO()):
        code = mod.run_uninstall(yes=True)
    check("卸载: 退出码 0", code == 0)
    check("卸载: 配置还原到备份", '"original"' in cfg.read_text())
    check("卸载: rc 块被剥除", marker not in rc.read_text())
    check("卸载: rc 其它内容保留", "export EDITOR=vim" in rc.read_text())
    check("卸载: 生成文件删除", not launcher.exists())
    check("卸载: 备份目录保留", mod.BACKUP_DIR.exists())

    # 空环境安全
    sandbox(mod)
    with contextlib.redirect_stdout(io.StringIO()):
        code = mod.run_uninstall(yes=True)
    check("卸载: 空环境正常退出", code == 0)


# ---------------------------------------------------------------------------
# 测试组: 权限收紧

def test_permissions():
    mod = load_module()
    tmp = sandbox(mod)
    p = tmp / "x" / "models.json"
    mod.write_json(p, {"apiKey": "sk-xxx"})
    check("write_json: 0o600", p.stat().st_mode & 0o777 == 0o600)
    e = tmp / "x" / ".env"
    mod.write_env(e, TOKEN="sk-xxx")
    check("write_env: 0o600", e.stat().st_mode & 0o777 == 0o600)


# ---------------------------------------------------------------------------
# 测试组: Spinner / 错误格式化

def test_ux_helpers():
    mod = load_module()
    real = sys.stdout
    try:
        buf = io.StringIO()
        sys.stdout = buf
        sp = mod.Spinner("验证 API Key...")
        sp.start(); sp.stop(success=False)
        out = buf.getvalue()
        check("Spinner: 非tty无帧", "⠋" not in out)
        check("Spinner: 非tty无清行码", "\x1b[K" not in out)

        class Tty(io.StringIO):
            def isatty(self):
                return True
        buf2 = Tty()
        sys.stdout = buf2
        sp2 = mod.Spinner("验证")
        sp2.start(); time.sleep(0.2); sp2.stop(success=True)
        check("Spinner: tty 有帧", any(f in buf2.getvalue() for f in "⠋⠙⠹⠸"))
        check("Spinner: tty 用 \\x1b[K 清行", "\r\x1b[K" in buf2.getvalue())
    finally:
        sys.stdout = real

    raw = json.dumps({"error": {"code": "401002", "message": "bad key " + "x" * 200}})
    f = mod._format_api_error(raw)
    check("错误: 截断带省略号", f.endswith("…") and len(f) <= 161)
    check("错误: code 前缀", f.startswith("[401002]"))
    check("错误: 非JSON原样", mod._format_api_error("plain") == "plain")
    check("错误: 空串安全", mod._format_api_error("") == "")


# ---------------------------------------------------------------------------
# 测试组: main() 交互流(EOF 安全)

def test_main_interactions():
    mod = load_module()
    sandbox(mod)
    mod.verify_api_key = lambda *a: True
    mod.fetch_remote_models = lambda *a: None
    mod.check_prerequisites = lambda tools: True

    def run(argv, answers=None):
        sys.argv = argv
        if answers is None:
            mod.ask = lambda p="": (_ for _ in ()).throw(EOFError)
        else:
            it = iter(answers)
            mod.ask = lambda p="": next(it)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main()
        return buf.getvalue()

    out = run(["x", "--plan", "enterprise-pro"],
              ["sk-fake-key-1234567890", "1", "none"])
    check("交互: 第三步运行模式", "第三步：选择运行模式" in out)
    check("交互: 第四步工具菜单", "第四步：选择工具" in out)
    check("交互: none 取消", "未选择任何工具" in out)

    out = run(["x", "--plan", "enterprise-pro", "--api-key", "sk-fake-key-1234567890"])
    check("EOF: run mode 默认", "无输入，默认" in out)
    check("EOF: 工具默认全部", "默认选择全部工具" in out)
    check("EOF: 配置 17 个", "正在配置 17 个工具" in out)

    out = run(["x", "--plan", "enterprise-pro", "--api-key", "sk-fake-key-1234567890",
               "--tools", "codex"], ["1"])
    check("--tools: 只配指定工具", "正在配置 1 个工具" in out and "Codex 已配置" in out)

    # 短 key flag 明确报错
    out = run(["x", "--plan", "enterprise-pro", "--api-key", "abc"])
    check("短key: flag 明确报错", "--api-key 传入的 Key 无效" in out)

    # 短 key 交互重试
    out = run(["x", "--plan", "enterprise-pro"], ["short", ""])
    check("短key: 交互提示重输", "长度过短" in out)


# ---------------------------------------------------------------------------
# 测试组: 结构一致性(仓库卫生)

def test_repo_consistency():
    check("npm/lib 与主脚本字节一致", NPM_LIB.read_bytes() == SCRIPT.read_bytes())

    src = SCRIPT.read_text(encoding="utf-8")
    ver = re.search(r'^VERSION = "([^"]+)"', src, re.M)
    pkg = json.loads(NPM_PKG.read_text(encoding="utf-8"))
    check("版本号: 主脚本与 npm 包一致", bool(ver) and ver.group(1) == pkg["version"])

    names = re.findall(r"^def ([a-zA-Z_]\w*)", src, re.M)
    dead = [n for n in names if len(re.findall(rf"\b{n}\b", src)) <= 1]
    check("无死代码(零引用函数)", dead == [] or print(f"  (死代码: {dead})") is None and not dead)

    for path in (SCRIPT, REPO / "setup.bat", NPM_PKG):
        text = path.read_text(encoding="utf-8", errors="ignore")
        leaked = re.findall(r"/Users/[\w/]+|/home/[\w/]+", text)
        check(f"{path.name}: 无硬编码用户路径", not leaked)

    # --version 冒烟
    r = subprocess.run([sys.executable, str(SCRIPT), "--version"],
                       capture_output=True, text=True)
    check("--version 可用", r.returncode == 0 and "tokenplan-setup" in (r.stdout + r.stderr))

    # setup.bat 规范:CRLF 行尾 + UTF-8 + chcp 65001(cmd 解析稳定性要求)
    bat = (REPO / "setup.bat").read_bytes()
    lf_only = bat.replace(b"\r\n", b"").count(b"\n")
    crlf = bat.count(b"\r\n")
    check("setup.bat: CRLF 行尾", crlf > 0 and lf_only == 0)
    check("setup.bat: UTF-8 可解码", bat.decode("utf-8") is not None)
    check("setup.bat: chcp 65001 存在", b"chcp 65001" in bat)

    # LICENSE 必须存在(公开发布前提)
    check("LICENSE 存在", (REPO / "LICENSE").exists())


# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 测试组: 远程模型目录

def test_remote_catalog():
    mod = load_module()

    # 回退:未刷新时用内置
    cat = mod.get_model_catalog("enterprise-pro")
    check("目录: 默认用内置", cat["default"] == "auto" and len(cat["display"]) > 0)

    # 远程覆盖:注入一份不同的远程目录
    mod._REMOTE_CATALOG = {
        "enterprise-pro": {
            "default": "glm-5.9",
            "display": ["新模型: glm-5.9", "另一款: kimi-k3"],
        }
    }
    cat = mod.get_model_catalog("enterprise-pro")
    check("目录: 远程优先", cat["default"] == "glm-5.9")
    check("目录: get_model_ids 走远程", mod.get_model_ids("enterprise-pro") == ["glm-5.9", "kimi-k3"])

    # 未知套餐 key 回退
    mod._REMOTE_CATALOG = {"other-plan": {"default": "x", "display": ["a: b"]}}
    cat = mod.get_model_catalog("enterprise-pro")
    check("目录: 远程缺该套餐时回退内置", cat["default"] == "auto")

    # 仓库 models.json 结构合法且套餐 key 对齐
    data = json.loads((REPO / "models.json").read_text(encoding="utf-8"))
    plans = data.get("plans", {})
    check("目录: models.json 套餐 key 与 PLAN_CATALOG 对齐",
          set(plans) == {p.key for p in mod.PLAN_CATALOG.values()})
    check("目录: 每个套餐都有 default+display",
          all(plans[k].get("default") and plans[k].get("display") for k in plans))
    check("目录: display 行都有 ':' 分隔",
          all(":" in line for p in plans.values() for line in p["display"]))

    # refresh 网络失败不崩溃
    mod2 = load_module()
    mod2.REMOTE_CATALOG_URL = "https://invalid.invalid/models.json"
    mod2.refresh_remote_catalog()
    check("目录: 网络失败安全回退", mod2._REMOTE_CATALOG is None)


TEST_GROUPS = [
    ("registry", test_registry),
    ("registry-windows", test_registry_windows),
    ("toml", test_toml_surgery),
    ("codex", test_codex_config),
    ("uninstall", test_uninstall),
    ("permissions", test_permissions),
    ("ux", test_ux_helpers),
    ("interactions", test_main_interactions),
    ("catalog", test_remote_catalog),
    ("consistency", test_repo_consistency),
]


def main():
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    groups = [(n, f) for n, f in TEST_GROUPS if pattern in n]
    for name, fn in groups:
        print(f"\n── {name} ──")
        fn()
    print(f"\n{'='*50}")
    print(f"通过 {len(PASSES)} / {len(PASSES) + len(FAILS)}")
    if FAILS:
        print("失败项:")
        for f in FAILS:
            print(f"  ✗ {f}")
        sys.exit(1)
    print("✅ 全部通过")


if __name__ == "__main__":
    main()
