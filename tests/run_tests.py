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
import os
import re
import subprocess
import sys
import tempfile
import time
import types
from pathlib import Path

# Windows 默认 stdout 编码(cp1252/GBK)无法打印中文与制表符(CI 红的原因),
# 本地与 CI 统一强制 UTF-8;stdout 可能被替换(重定向/pytest)时静默跳过。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass

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
    check("12 个工具注册", len(mod.TOOLS) == 12)
    check("编号 1-6 为已验证工具(顺序稳定)",
          [t.key for t in mod.TOOLS[:6]] ==
          ["hermes", "codebuddy", "claude-code", "opencode", "openclaw", "dsh"])
    check("索引 1-12 连续", sorted(mod.TOOL_BY_INDEX, key=int) == [str(i) for i in range(1, 13)])
    check("TOOL_BY_KEY 与 TOOLS 一致",
          set(mod.TOOL_BY_KEY) == {t.key for t in mod.TOOLS})
    check("每个配置器都有对应工具 key",
          set(mod.CONFIGURATOR_REGISTRY) <= set(mod.TOOL_BY_KEY))
    check("plugin 工具都有扩展 ID",
          all(t.key in mod.PLUGIN_EXTENSION_IDS for t in mod.TOOLS if t.backend == "plugin"))
    check("backend 全部已注册", all(t.backend in mod.BACKEND_REGISTRY for t in mod.TOOLS))
    check("9 个套餐(4 中国站 + 3 国际站套餐 + 2 后付费)",
          len(mod.PLAN_CATALOG) == 9)
    check("后付费套餐走 tokenhub /v1 端点",
          mod.PLAN_CATALOG["8"].base_url == "https://tokenhub.tencentmaas.com/v1")
    check("国际站后付费走 intl /v1 端点(与套餐版同域)",
          mod.PLAN_CATALOG["9"].base_url
          == "https://tokenhub-intl.tencentcloudmaas.com/v1")
    check("两站后付费 Key 控制台不同",
          mod.PLAN_CATALOG["8"].key_url != mod.PLAN_CATALOG["9"].key_url)
    check("国际站套餐走 intl 端点",
          all(p.base_url.startswith("https://tokenhub-intl.")
              for p in mod.PLAN_CATALOG.values() if p.key.startswith("intl-")))
    check("每个套餐都有模型目录",
          set(p.key for p in mod.PLAN_CATALOG.values()) <= set(mod.MODEL_CATALOG))
    check("配置签名与配置器一一对应",
          set(mod.CONFIG_SIGNATURES) == set(mod.CONFIGURATOR_REGISTRY))
    check("每个签名文件路径存在且特征串非空",
          all(rel and marker for rel, marker, _legacy in mod.CONFIG_SIGNATURES.values()))


def test_registry_windows():
    mod = load_module(windows=True)
    cmd = mod.get_install_command(mod.TOOL_BY_KEY["codex"])
    check("Win: codex 安装命令以 npm 开头", cmd is not None and cmd[0] == "npm")
    check("Win: hermes 不自动安装", mod.get_install_command(mod.TOOL_BY_KEY["hermes"]) is None)
    check("Win: WorkBuddy 走手动下载",
          mod.should_manual_download(mod.TOOL_BY_KEY["workbuddy"]))


# ---------------------------------------------------------------------------
# 测试组: TOML 手术 + Codex 配置器

def test_toml_surgery():
    mod = load_module()
    U, S = mod._toml_upsert_root_key, mod._toml_upsert_section
    entries = {"name": "T", "base_url": "https://x", "wire_api": "chat",
               "env_key": "TOKENPLAN_API_KEY"}

    lines = S(U(U([], "model_provider", "tokenhub"), "model", "glm-5.2"),
              "[model_providers.tokenhub]", entries)
    text = "\n".join(lines)
    check("TOML: 全新生成含根键与表", "model_provider" in text and "[model_providers.tokenhub]" in text)
    check("TOML: 根键位于表头之前", text.index("model_provider") < text.index("["))

    existing = ['model = "gpt-5"', 'approval_mode = "on-request"', "",
                "[model_providers.openai]", 'name = "OpenAI"', "",
                '[projects."work"]', 'trust_level = "trusted"']
    lines = U(list(existing), "model_provider", "tokenhub")
    lines = U(lines, "model", "glm-5.2")
    lines = S(lines, "[model_providers.tokenhub]", entries)
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
    # 按域分治(真 Key 实测):tokenhub 域用 responses(Codex 0.152+ 唯一支持的模式,
    # 端点 200;lkeap 个人版无 /responses(404),按官方文档用 chat)
    check("Codex: tokenhub 域 wire_api=responses", 'wire_api = "responses"' in text)
    # lkeap 个人版:按官方文档走 chat + 警告
    (tmp / ".codex" / "config.toml").unlink()
    with contextlib.redirect_stdout(io.StringIO()):
        mod.configure_codex("https://api.lkeap.cloud.tencent.com/plan/v3", key,
                            mod.PLAN_CATALOG["1"])
    ltext = (tmp / ".codex" / "config.toml").read_text()
    check("Codex: lkeap 域 wire_api=chat(官方文档)", 'wire_api = "chat"' in ltext)
    if sys.platform == "win32":
        # Windows 设计:走 setx 用户环境变量,不写 env 文件
        check("Codex: Windows 注入 TOKENPLAN_API_KEY",
              os.environ.get("TOKENPLAN_API_KEY") == key)
    else:
        check("Codex: env 文件权限 600",
              (tmp / ".codex" / "tokenplan.env").stat().st_mode & 0o777 == 0o600)

    # 保留用户已有配置
    cfg.write_text('model = "gpt-5"\n\n[model_providers.openai]\nname = "OpenAI"\nbase_url = "https://api.openai.com/v1"\n')
    with contextlib.redirect_stdout(io.StringIO()):
        mod.configure_codex(base, key, plan)
    text = cfg.read_text()
    check("Codex: 用户 provider 保留", "model_providers.openai" in text)
    check("Codex: 我们的节共存(新品牌口径)",
          f"model_providers.{mod.BRAND_SLUG}" in text)

    before = text
    with contextlib.redirect_stdout(io.StringIO()):
        mod.configure_codex(base, key, plan)
    check("Codex: 幂等", cfg.read_text() == before)

    # 旧品牌段(2.5.x)在重跑时被摘除,不再残留失效入口
    cfg.write_text(
        'model = "glm-5.2"\n\n[model_providers.tokenplan]\nname = "Tencent Cloud Token Plan"\n'
        'base_url = "https://old"\nwire_api = "chat"\n\n[model_providers.openai]\nname = "OpenAI"\n'
    )
    with contextlib.redirect_stdout(io.StringIO()):
        mod.configure_codex(base, key, plan)
    text = cfg.read_text()
    check("Codex: 旧品牌段摘除", "model_providers.tokenplan" not in text)
    check("Codex: 旧段摘除后新段在", f"model_providers.{mod.BRAND_SLUG}" in text)


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
    e = tmp / "x" / ".env"
    mod.write_env(e, TOKEN="sk-xxx")
    if sys.platform == "win32":
        # NTFS 无 POSIX 权限位;Windows 契约 = 文件生成且 _harden 不抛错
        check("write_json: 文件生成(Windows 无 POSIX 位)", p.exists())
        check("write_env: 文件生成(Windows 无 POSIX 位)", e.exists())
    else:
        check("write_json: 0o600", p.stat().st_mode & 0o777 == 0o600)
        check("write_env: 0o600", e.stat().st_mode & 0o777 == 0o600)


# ---------------------------------------------------------------------------
# 测试组: 后付费(按量计费)

def test_postpaid():
    mod = load_module()
    tmp = sandbox(mod)
    mod._REMOTE_CATALOG = None
    mod._POSTPAID_DISCOVERED = None
    plan = mod.PLAN_CATALOG["8"]
    base = "https://tokenhub.tencentmaas.com/v1"

    check("后付费: 选项 8 存在且端点正确",
          plan.key == "postpaid" and plan.base_url == base)
    check("后付费: Key 控制台指向 tokenhub",
          "tokenhub/apikey" in plan.key_url)

    # 未发现时:目录为空,default 为空串
    empty_catalog = mod.get_model_catalog("postpaid")
    check("后付费: 未发现时目录为空", empty_catalog["default"] == "" and not empty_catalog["display"])

    # 模拟发现成功(贴近 tokenhub /v1/models 实测列表)
    mod._POSTPAID_DISCOVERED = ["hy4-preview", "glm-5.3", "glm-5.3-flash", "deepseek-v3"]
    catalog = mod.get_model_catalog("postpaid")
    ids = mod.get_model_ids("postpaid")
    check("后付费: 发现后目录为发现列表", set(ids) == set(mod._POSTPAID_DISCOVERED))
    check("后付费: 默认模型优先 glm-5.3", catalog["default"] == "glm-5.3")

    # 模拟无首选时的次优选择
    mod._POSTPAID_DISCOVERED = ["hy3", "deepseek-chat"]
    check("后付费: 无首选时回退第一个", mod.get_model_catalog("postpaid")["default"] == "hy3")

    # 聊天能力过滤:非聊天模型不进目录
    mod._POSTPAID_DISCOVERED = [
        "glm-5.3", "kling-video-v3", "kinfra-text-embedding-4b",
        "minimax-music-v3.0", "deepseek-v4-pro",
    ]
    ids = mod.get_model_ids("postpaid")
    check("后付费: 非聊天模型被过滤",
          set(ids) == {"glm-5.3", "deepseek-v4-pro"})
    check("后付费: 过滤后默认模型仍正确",
          mod.get_model_catalog("postpaid")["default"] == "glm-5.3")

    # 全部被过滤时兜底原始列表(不至于空配置)
    mod._POSTPAID_DISCOVERED = ["kling-video-v3", "seedream-image-v5.0-pro"]
    check("后付费: 全被过滤时兜底原始列表",
          mod.get_model_ids("postpaid") == ["kling-video-v3", "seedream-image-v5.0-pro"])

    # ── 模型自选 ──
    mod._POSTPAID_DISCOVERED = ["glm-5.3-flash", "glm-5.3", "deepseek-v4-pro",
                                "kling-video-v3", "kimi-k3"]
    mod._POSTPAID_SELECTED = None
    chosen = mod.set_postpaid_selection(["kimi-k3", "glm-5.3", "no-such-model"])
    check("自选: 未知模型被忽略,有效项按发现顺序",
          chosen == ["glm-5.3", "kimi-k3"])
    check("自选: 目录只含所选", mod.get_model_ids("postpaid") == ["glm-5.3", "kimi-k3"])
    check("自选: 默认模型在所选中回退",
          mod.get_model_catalog("postpaid")["default"] == "glm-5.3")
    # 清空选择恢复全部
    mod._POSTPAID_SELECTED = None
    check("自选: 清空后恢复全部",
          mod.get_model_ids("postpaid") == ["glm-5.3-flash", "glm-5.3", "deepseek-v4-pro", "kimi-k3"])
    # 全部无效 → 保持全部
    chosen2 = mod.set_postpaid_selection(["nope-1", "nope-2"])
    check("自选: 所选全无效时保持全部", len(chosen2) == 4 and mod._POSTPAID_SELECTED is None)

    # 5xx 瞬时错误重试:一次 502 后 200 → 成功;连续 502 → 如实失败
    import urllib.error as _ue, io as _io2
    calls = {"n": 0}
    def _flaky(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _ue.HTTPError(req.full_url, 502, "Bad Gateway", {},
                                _io2.BytesIO(b'{"error":{"message":"upstream"}}'))
        return _io2.BytesIO(b'{"id":"x"}')
    mod.urllib.request.urlopen = _flaky
    mod.time.sleep = lambda s: None
    passed, reason = mod.test_model("https://x", "sk-k", "m1")
    check("验证重试: 502 后 200 → 成功", passed and calls["n"] == 2)
    calls["n"] = 0
    def _always502(req, timeout=None):
        calls["n"] += 1
        raise _ue.HTTPError(req.full_url, 502, "Bad Gateway", {},
                            _io2.BytesIO(b'{"error":{"message":"upstream"}}'))
    mod.urllib.request.urlopen = _always502
    passed2, reason2 = mod.test_model("https://x", "sk-k", "m1")
    check("验证重试: 连续 502 → 失败且注明疑似瞬时",
          not passed2 and "瞬时" in reason2 and calls["n"] == 2)
    # 4xx 不重试
    calls["n"] = 0
    def _always401(req, timeout=None):
        calls["n"] += 1
        raise _ue.HTTPError(req.full_url, 401, "Unauthorized", {},
                            _io2.BytesIO(b'{"error":{"message":"no"}}'))
    mod.urllib.request.urlopen = _always401
    passed3, _ = mod.test_model("https://x", "sk-k", "m1")
    check("验证重试: 401 不重试", not passed3 and calls["n"] == 1)

    # 交互选择:编号挑选
    mod._POSTPAID_SELECTED = None
    answers = iter(["1 3"])
    mod.ask = lambda p="": next(answers, "")
    import contextlib, io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        mod.choose_postpaid_models()
    check("自选: 交互编号'1 3'生效",
          mod.get_model_ids("postpaid") == ["glm-5.3-flash", "deepseek-v4-pro"])
    # 交互:回车=全部
    mod._POSTPAID_SELECTED = None
    answers = iter([""])
    mod.ask = lambda p="": next(answers, "")
    with contextlib.redirect_stdout(_io.StringIO()):
        mod.choose_postpaid_models()
    check("自选: 回车=全部", len(mod.get_model_ids("postpaid")) == 4)
    # 交互:模型名直接输入
    mod._POSTPAID_SELECTED = None
    answers = iter(["kimi-k3"])
    mod.ask = lambda p="": next(answers, "")
    with contextlib.redirect_stdout(_io.StringIO()):
        mod.choose_postpaid_models()
    check("自选: 直接输入模型名生效",
          mod.get_model_ids("postpaid") == ["kimi-k3"])

    # Claude 槽位:精确匹配优先(flash 在前也不抢 glm-5.3)
    mod._POSTPAID_SELECTED = None
    with contextlib.redirect_stdout(_io.StringIO()):
        mod.configure_claude_code(base, "sk-pp-9", plan)
    env9 = json.loads((tmp / ".claude" / "settings.json").read_text())["env"]
    check("自选: Claude opus 精确匹配 glm-5.3",
          env9.get("ANTHROPIC_DEFAULT_OPUS_MODEL") == "glm-5.3")

    # Claude 动态槽
    mod._POSTPAID_DISCOVERED = ["glm-5.3", "glm-5.3-flash", "hy4-preview"]
    import contextlib, io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        mod.configure_claude_code(base, "sk-pp-test-1234567890", plan)
    settings = json.loads((tmp / ".claude" / "settings.json").read_text())
    env = settings.get("env", {})
    # Anthropic SDK 硬拼 /v1/messages:base 必须为裸域(不带 /v1),
    # 否则请求 /v1/v1/messages → 404(2.1.1 修复)
    check("后付费: Claude anthropic base 为裸域(SDK 拼 /v1/messages)",
          env.get("ANTHROPIC_BASE_URL") == base.rstrip("/")[:-len("/v1")])
    check("后付费: Claude opus 槽选 glm-5.3", env.get("ANTHROPIC_DEFAULT_OPUS_MODEL") == "glm-5.3")
    check("后付费: Claude haiku 槽选 flash", env.get("ANTHROPIC_DEFAULT_HAIKU_MODEL") == "glm-5.3-flash")

    # verify:发现失败返回 False
    def _fail(url, key):
        return None
    orig = mod.discover_postpaid_models
    mod.discover_postpaid_models = lambda u, k: None
    with contextlib.redirect_stdout(_io.StringIO()):
        passed = mod.verify_api_key(base, "sk-bad", plan)
    check("后付费: 发现失败 → verify False", passed is False)
    mod.discover_postpaid_models = orig

    # WorkBuddy 用发现列表(进程检测必须 mock:测试不依赖宿主机是否开着 WorkBuddy)
    mod._POSTPAID_DISCOVERED = ["deepseek-v3.2", "deepseek-chat"]
    real_run = mod.subprocess.run
    mod.subprocess.run = lambda *a, **k: type("R", (), {"returncode": 1})()
    try:
        with contextlib.redirect_stdout(_io.StringIO()):
            mod.configure_workbuddy(base, "sk-pp-2", plan)
    finally:
        mod.subprocess.run = real_run
    wb = json.loads((tmp / ".workbuddy" / "models.json").read_text())
    check("后付费: WorkBuddy 写入发现模型", {e["id"] for e in wb} == {"deepseek-v3.2", "deepseek-chat"})

    mod._POSTPAID_DISCOVERED = None


# ---------------------------------------------------------------------------
# 测试组: WorkBuddy 全量模型写入

def test_workbuddy_config():
    mod = load_module()
    tmp = sandbox(mod)
    # 钉死目录来源:测试必须与网络状态无关(内置目录,企业专业=18 模型)
    mod._REMOTE_CATALOG = None
    plan = mod.PLAN_CATALOG["3"]  # 企业专业,18 模型
    base, key = "https://tokenhub.tencentmaas.com/plan/v3", "sk-wb-test-1234567890"

    # 预置用户手填条目(模拟真实场景:已有 1 条自建 + 1 条旧 TokenPlan)
    models = tmp / ".workbuddy" / "models.json"
    models.parent.mkdir(parents=True, exist_ok=True)
    models.write_text(json.dumps([
        {"id": "my-own-model", "name": "自建模型", "apiKey": "sk-user-own"},
        {"id": "glm-5.2", "name": "旧的手填 TokenPlan", "apiKey": "sk-old"},
    ], ensure_ascii=False))

    import contextlib, io as _io
    buf = _io.StringIO()
    real_run = mod.subprocess.run
    mod.subprocess.run = lambda *a, **k: type("R", (), {"returncode": 1})()
    try:
        with contextlib.redirect_stdout(buf):
            mod.configure_workbuddy(base, key, plan)
    finally:
        mod.subprocess.run = real_run

    data = json.loads(models.read_text())
    ids = [e["id"] for e in data]
    # 预置了 1 条用户自建 + 1 条旧 TokenPlan(被更新) → 总数 = 目录数 + 1
    check("WorkBuddy: 写入全部套餐模型", len(ids) == len(mod.get_model_ids("enterprise-pro")) + 1)
    check("WorkBuddy: 套餐模型全部在列",
          set(mod.get_model_ids("enterprise-pro")) <= set(ids))
    check("WorkBuddy: 用户自建模型保留", "my-own-model" in ids and json.dumps(data).find("sk-user-own") != -1)
    check("WorkBuddy: 旧 TokenPlan 条目被更新(非重复)",
          ids.count("glm-5.2") == 1 and [e for e in data if e["id"] == "glm-5.2"][0]["apiKey"] == key)
    check("WorkBuddy: 条目使用 chat/completions URL",
          all(e["url"].endswith("/chat/completions") for e in data if e["id"] != "my-own-model"))
    check("WorkBuddy: vision 模型标记图片能力",
          [e for e in data if e["id"] == "deepseek/deepseek-v4-flash-vision-exp"][0]["supportsImages"] is True)
    check("WorkBuddy: 文本模型不标图片",
          [e for e in data if e["id"] == "glm-5.3"][0]["supportsImages"] is False)
    if sys.platform == "win32":
        # NTFS 无 POSIX 权限位;Windows 契约 = 文件生成即可
        check("WorkBuddy: 文件生成(Windows 无 POSIX 位)", models.exists())
    else:
        check("WorkBuddy: 文件权限 600", models.stat().st_mode & 0o777 == 0o600)
    # 幂等验证
    mod.subprocess.run = lambda *a, **k: type("R", (), {"returncode": 1})()
    try:
        with contextlib.redirect_stdout(_io.StringIO()):
            mod.configure_workbuddy(base, key, plan)
    finally:
        mod.subprocess.run = real_run
    ids2 = [e["id"] for e in json.loads(models.read_text())]
    check("WorkBuddy: 重跑后条目数不变(幂等)", len(ids2) == len(ids))
    check("WorkBuddy: doctor 签名存在", mod.probe_config(mod.TOOL_BY_KEY["workbuddy"]) is True)


def test_write_json_list_merge():
    mod = load_module()
    tmp = sandbox(mod)
    p = tmp / "list.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps([{"id": "a", "v": 1}, {"id": "user", "v": 9}]))
    mod.write_json(p, [{"id": "a", "v": 2}, {"id": "b", "v": 3}], merge=True, merge_key="id")
    data = {e["id"]: e["v"] for e in json.loads(p.read_text())}
    check("list合并: 同 id 更新", data["a"] == 2)
    check("list合并: 新 id 追加", data["b"] == 3)
    check("list合并: 用户条目保留", data["user"] == 9)
    check("list合并: 总数正确", len(data) == 3)


# ---------------------------------------------------------------------------
# 测试组: Kimi/Grok/Pi/ZCode 配置器(arkcli 对标新增)

def test_new_tool_configs():
    mod = load_module()
    tmp = sandbox(mod)
    mod._REMOTE_CATALOG = None
    plan = mod.PLAN_CATALOG["1"]  # 个人通用,10 模型
    base = "https://tokenhub.tencentmaas.com/plan/v3"
    key = "sk-new-tools-1234567890"

    import contextlib, io as _io
    buf = _io.StringIO()
    real_run = mod.subprocess.run
    mod.subprocess.run = lambda *a, **k: type("R", (), {"returncode": 1})()
    try:
        with contextlib.redirect_stdout(buf):
            mod.configure_kimi(base, key, plan)
            mod.configure_grok(base, key, plan)
            mod.configure_pi(base, key, plan)
            mod.configure_zcode(base, key, plan)
    finally:
        mod.subprocess.run = real_run

    models = mod.get_model_ids(plan.key)

    # Kimi Code: config.toml
    toml = (tmp / ".kimi-code" / "config.toml").read_text()
    check("kimi: provider 段", f"[providers.{mod.BRAND_SLUG}]" in toml)
    check("kimi: 默认模型", 'default_model = "%s"' % models[0] in toml)
    check("kimi: 默认 provider", 'default_provider = "%s"' % mod.BRAND_SLUG in toml)
    check("kimi: 默认键在首个表头之前(顶层)",
          toml.index("default_provider") < toml.index(f"[providers.{mod.BRAND_SLUG}]"))
    check("kimi: 模型段数", toml.count("[models.") == len(models))
    check("kimi: max_context_size 必填字段", "max_context_size" in toml)
    # 含点号的模型 id(minimax-m2.7 等)必须引号包裹:
    # TOML 表头中点是分隔符,[models.glm-5.3] 会解析成嵌套表,
    # 且与平级 [models.glm-5] 冲突 → 整个文件解析失败(2.2.0 修复)
    import re as _re
    secs = _re.findall(r'^\[models\.[^\]]+\]', toml, _re.M)
    check("kimi: 模型段全部引号包裹(点号安全)",
          len(secs) == len(models) and all('"' in s for s in secs))
    check("kimi: 无遗留无引号段", _re.search(r'^\[models\.[^"\]]+\]$', toml, _re.M) is None)
    with contextlib.redirect_stdout(buf):
        mod.configure_kimi(base, key, plan)
    toml2 = (tmp / ".kimi-code" / "config.toml").read_text()
    check("kimi: 幂等重跑不重复", toml2.count(f"[providers.{mod.BRAND_SLUG}]") == 1
          and toml2.count("[models.") == len(models))

    # Grok: config.toml
    gtoml = (tmp / ".grok" / "config.toml").read_text()
    check("grok: 模型段数", gtoml.count("[model.") == len(models))
    gsecs = _re.findall(r'^\[model\.[^\]]+\]', gtoml, _re.M)
    check("grok: 模型段全部引号包裹(点号安全)",
          len(gsecs) == len(models) and all('"' in s for s in gsecs))
    check("grok: base_url 写入", base in gtoml)
    check("grok: 托管标记", f"# {mod.BRAND_NAME} models begin" in gtoml)
    with contextlib.redirect_stdout(buf):
        mod.configure_grok(base, key, plan)
    gtoml2 = (tmp / ".grok" / "config.toml").read_text()
    check("grok: 幂等重跑不重复", gtoml2.count("[model.") == len(models))

    # Pi: models.json
    pdata = json.loads((tmp / ".pi" / "agent" / "models.json").read_text())
    check("pi: provider 注册", mod.BRAND_SLUG in pdata["providers"])
    prov = pdata["providers"][mod.BRAND_SLUG]
    check("pi: openai-completions 协议", prov["api"] == "openai-completions")
    check("pi: 模型数", len(prov["models"]) == len(models))
    check("pi: 模型 id 结构", prov["models"][0]["id"] == models[0])

    # ZCode: config.json
    zdata = json.loads((tmp / ".zcode" / "v2" / "config.json").read_text())
    zprov = list(zdata["provider"].values())[0]
    check("zcode: kind", zprov["kind"] == "openai-compatible")
    check("zcode: baseURL", zprov["options"]["baseURL"] == base)
    check("zcode: 模型数", len(zprov["models"]) == len(models))
    check("zcode: limit 结构", "context" in list(zprov["models"].values())[0]["limit"])
    with contextlib.redirect_stdout(buf):
        mod.configure_zcode(base, key, plan)
    zdata2 = json.loads((tmp / ".zcode" / "v2" / "config.json").read_text())
    check("zcode: 幂等(provider 不翻倍)", len(zdata2["provider"]) == 1)

    # 权限:含 Key 的文件全部 0600(POSIX)
    if hasattr(os, "stat") and not sys.platform.startswith("win"):
        for rel in (".kimi-code/config.toml", ".grok/config.toml",
                    ".pi/agent/models.json", ".zcode/v2/config.json"):
            p = tmp / rel
            check(f"权限 0600: {rel}", (p.stat().st_mode & 0o777) == 0o600)

    # doctor 签名可用
    for k in ("kimi", "grok", "pi", "zcode"):
        check(f"doctor 签名生效: {k}",
              mod.probe_config(mod.TOOL_BY_KEY[k]) is True)


# 测试组: doctor 配置三态 / 超时 / 版本感知

def test_doctor_config_probe():
    mod = load_module()
    tmp = sandbox(mod)
    tool = mod.TOOL_BY_KEY["codex"]
    # 全部 8 个工具均有配置器,probe 只会返回 True/False;防御路径(None)已无实例
    check("probe: 有签名工具返回布尔值",
          isinstance(mod.probe_config(mod.TOOL_BY_KEY["codex"]), bool))

    # 未配置:文件不存在 → False
    check("probe: 配置文件缺失 → False", mod.probe_config(tool) is False)

    # 已配置:写入含签名的文件 → True
    cfg = tmp / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('model = "glm-5.2"\n\n[model_providers.tokenplan]\nname = "Token Plan"\n')
    check("probe: 旧版签名(2.5.x 品牌) → True", mod.probe_config(tool) is True)
    cfg.write_text(f'[model_providers.{mod.BRAND_SLUG}]\n')
    check("probe: 当前签名 → True", mod.probe_config(tool) is True)

    # 配置被外部覆盖(签名丢失)→ False
    cfg.write_text('model = "gpt-5"\n')
    check("probe: 签名被覆盖 → False", mod.probe_config(tool) is False)

    # doctor 三态文案(安装状态与环境无关:CI 机器没有 codex,必须 mock)
    import contextlib, io as _io
    mod.is_tool_installed = lambda t: True
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod.run_doctor([tool])
    out = buf.getvalue()
    check("doctor: 配置缺失提示 repair", "配置缺失" in out and "repair" in out)
    cfg.write_text(f'[model_providers.{mod.BRAND_SLUG}]\n')
    buf2 = _io.StringIO()
    with contextlib.redirect_stdout(buf2):
        mod.run_doctor([tool])
    check("doctor: 配置有效文案", "配置有效" in buf2.getvalue())
    mod.is_tool_installed = lambda t: False
    buf3 = _io.StringIO()
    with contextlib.redirect_stdout(buf3):
        mod.run_doctor([tool])
    check("doctor: 未安装文案", "未安装" in buf3.getvalue() and "配置有效" not in buf3.getvalue())


def test_install_timeout():
    mod = load_module()
    check("INSTALL_TIMEOUT 为 600 秒", mod.INSTALL_TIMEOUT == 600)
    # 超时路径:假命令 sleep 超过被临时调小的 deadline
    mod.INSTALL_TIMEOUT = 1
    import contextlib, io as _io, time as _t
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        t0 = _t.monotonic()
        passed = mod.run_command(("python3", "-c", "import time; time.sleep(30)"), "超时测试")
        elapsed = _t.monotonic() - t0
    check("超时: 返回失败", passed is False)
    check("超时: 快速返回而非等待 30s", elapsed < 10)
    check("超时: 提示网络受限", "网络" in buf.getvalue())


def test_version_awareness():
    mod = load_module()
    check("版本比较: 1.1.0 > 1.0.0",
          mod._version_tuple("1.1.0") > mod._version_tuple("1.0.0"))
    check("版本比较: 1.0.10 > 1.0.9",
          mod._version_tuple("1.0.10") > mod._version_tuple("1.0.9"))
    check("版本比较: 相等", mod._version_tuple("1.1.0") == mod._version_tuple("1.1.0"))
    # 提示逻辑:同版本不提示,旧版本提示
    mod._REMOTE_LATEST_VERSION = mod.VERSION
    import contextlib, io as _io
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        mod.notify_upgrade_available()
    check("版本提示: 当前即最新则不提示", "新版本" not in buf.getvalue())
    mod._REMOTE_LATEST_VERSION = "99.0.0"
    buf2 = _io.StringIO()
    with contextlib.redirect_stdout(buf2):
        mod.notify_upgrade_available()
    check("版本提示: 落后时提示升级", "99.0.0" in buf2.getvalue())


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
        # 远程脚本安装走本地桩:交互测试不触网(真实路径由 remote-script 组覆盖)。
        # 远程脚本在非交互下本来就 fail-closed,桩只是省掉真实下载。
        mod.run_remote_script = lambda url, sargs, name: False
        # 宿主机可能残留 TOKENPLAN_API_KEY(真实运行写入),不清理会改变交互顺序
        os.environ.pop("TOKENPLAN_API_KEY", None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = mod.main()
        return buf.getvalue(), code

    out, _ = run(["x", "--plan", "enterprise-pro"],
                 ["sk-fake-key-1234567890", "1", "none"])
    check("交互: 第三步运行模式", "第三步：选择运行模式" in out)
    check("交互: 第四步工具菜单", "第四步：选择工具" in out)
    check("交互: none 取消", "未选择任何工具" in out)

    out, _ = run(["x", "--plan", "enterprise-pro", "--api-key", "sk-fake-key-1234567890"])
    check("EOF: run mode 默认", "无输入，默认" in out)
    check("EOF: 工具默认全部", "默认选择全部工具" in out)
    check("EOF: 配置 12 个", "正在配置 12 个工具" in out)

    out, _ = run(["x", "--plan", "enterprise-pro", "--api-key", "sk-fake-key-1234567890",
                  "--tools", "codex"], ["1"])
    check("--tools: 只配指定工具", "正在配置 1 个工具" in out and "Codex 已配置" in out)

    # 手动下载类但有配置器的工具(WorkBuddy):配置必须照写,不能只提示下载
    # 注意:前面的 EOF 子测试已在旧沙箱写过全量配置,这里必须换全新沙箱,
    # 否则 merge 语义会把两个套餐的条目合并,数量断言就依赖执行顺序了
    import subprocess as _sp
    _real = _sp.run
    def _fake(cmd, *a, **k):
        if cmd and "pgrep" in str(cmd[0]):
            return type("R", (), {"returncode": 1})()
        return _real(cmd, *a, **k)
    _sp.run = _fake
    try:
        wb_home = sandbox(mod)
        # 数量断言用内置目录:必须连 refresh 一起 mock,否则 main() 真拉 CDN,
        # 陈旧边缘缓存(v1.1.0 目录)会覆盖内置 catalog,数量随缓存漂移
        mod._REMOTE_CATALOG = None
        _real_refresh = mod.refresh_remote_catalog
        mod.refresh_remote_catalog = lambda: None
        out, _ = run(["x", "--plan", "personal-general", "--api-key", "sk-fake-key-1234567890",
                      "--tools", "workbuddy"], ["1"])
        mod.refresh_remote_catalog = _real_refresh
        check("WorkBuddy: 手动下载类仍写配置", "配置已写入" in out)
        wb_models = json.loads((wb_home / ".workbuddy" / "models.json").read_text())
        check("WorkBuddy: 模型真实落盘", len(wb_models) == 13)  # personal-general 目录=13 模型(真 Key 实测)
    finally:
        _sp.run = _real

    # 短 key flag 明确报错
    out, _ = run(["x", "--plan", "enterprise-pro", "--api-key", "abc"])
    check("短key: flag 明确报错", "--api-key 传入的 Key 无效" in out)

    # 短 key 交互重试
    out, _ = run(["x", "--plan", "enterprise-pro"], ["short", ""])
    check("短key: 交互提示重输", "长度过短" in out)


# ---------------------------------------------------------------------------
# 测试组: 结构一致性(仓库卫生)

def test_repo_consistency():
    mod = load_module()
    check("npm/lib 与主脚本字节一致", NPM_LIB.read_bytes() == SCRIPT.read_bytes())

    # setup.bat:内嵌版本与 SHA256 必须与主脚本一致(改 setup.command 忘跑 sync 会被 CI 拦下)
    import hashlib as _hl
    bat_text = (REPO / "setup.bat").read_text(encoding="utf-8")
    import re as _re
    v_m = _re.search(r'set "SETUP_VERSION=([^"]+)"', bat_text)
    h_m = _re.search(r'set "SETUP_SHA256=([0-9a-fA-F]{64})"', bat_text)
    check("setup.bat: 内嵌版本与主脚本一致", v_m and v_m.group(1) == mod.VERSION)
    check("setup.bat: 内嵌 SHA256 与主脚本一致",
          h_m and h_m.group(1).lower() == _hl.sha256(SCRIPT.read_bytes()).hexdigest())
    check("setup.bat: 下载 URL 固定版本(非 @main)",
          "@main" not in bat_text and "releases/download" in bat_text)

    # models.json.sha256 与 models.json 严格对应(远程目录完整性校验依赖;
    # 改 models.json 忘刷哈希会被这里拦下,正常流程由 sync_npm_lib.py 自动再生)
    sha_path = REPO / "models.json.sha256"
    sha_text = sha_path.read_text(encoding="utf-8") if sha_path.exists() else ""
    sha_m = re.search(r"[0-9a-fA-F]{64}", sha_text)
    check("models.json.sha256 存在且与 models.json 一致",
          bool(sha_m)
          and sha_m.group(0).lower()
          == _hl.sha256((REPO / "models.json").read_bytes()).hexdigest())

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
    check("目录: 每个套餐都有 default+display(后付费除外:运行时发现)",
          all(
              (plans[k].get("display") or k in ("postpaid", "postpaid-intl"))
              for k in plans
          ) and all("default" in plans[k] for k in plans))
    check("目录: display 行都有 ':' 分隔",
          all(":" in line for p in plans.values() for line in p["display"]))

    # refresh 网络失败不崩溃
    mod2 = load_module()
    mod2.REMOTE_CATALOG_URL = "https://invalid.invalid/models.json"
    mod2.refresh_remote_catalog()
    check("目录: 网络失败安全回退", mod2._REMOTE_CATALOG is None)


# ---------------------------------------------------------------------------
# 测试组: write_json 深合并(2.5.0:修复顶层浅合并顶掉用户同级配置)

def test_deep_merge():
    mod = load_module()
    tmp = sandbox(mod)

    # dict 深合并:用户同级 provider 保留,我方 provider 嵌套更新
    p = tmp / "opencode.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "model": "openai/gpt-5",
        "provider": {
            "openai": {"name": "OpenAI", "options": {"apiKey": "sk-user"}},
            "tokenplan": {"name": "旧名", "options": {"apiKey": "sk-old"}},
        },
    }, ensure_ascii=False))
    mod.write_json(p, {
        "model": "tokenplan/glm-5.2",
        "provider": {
            "tokenplan": {"name": "Tencent Cloud Token Plan",
                          "options": {"apiKey": "sk-new"}},
        },
    }, merge=True)
    data = json.loads(p.read_text())
    check("深合并: 用户同级 provider 保留",
          data["provider"]["openai"]["options"]["apiKey"] == "sk-user")
    check("深合并: 我方 provider 嵌套更新",
          data["provider"]["tokenplan"]["options"]["apiKey"] == "sk-new")
    check("深合并: 我方顶层键生效", data["model"] == "tokenplan/glm-5.2")

    # env 字典深合并:用户自定义环境变量不丢
    p2 = tmp / "settings.json"
    p2.write_text(json.dumps(
        {"env": {"USER_CUSTOM": "keep-me"}, "other": 1}, ensure_ascii=False))
    mod.write_json(p2, {"env": {"TOKENPLAN_API_KEY": "sk-x"}}, merge=True)
    d2 = json.loads(p2.read_text())
    check("深合并: 用户 env 键保留", d2["env"]["USER_CUSTOM"] == "keep-me")
    check("深合并: 我方 env 键写入", d2["env"]["TOKENPLAN_API_KEY"] == "sk-x")
    check("深合并: 无关顶层键保留", d2["other"] == 1)

    # 嵌套 list + merge_key:codebuddy models.json 的结构({"models": [...]})
    p3 = tmp / "codebuddy-models.json"
    p3.write_text(json.dumps({"models": [
        {"id": "user-own", "apiKey": "sk-user"},
        {"id": "glm-5.2", "apiKey": "sk-old"},
    ]}, ensure_ascii=False))
    mod.write_json(p3, {"models": [
        {"id": "glm-5.2", "apiKey": "sk-new"},
        {"id": "glm-5.3", "apiKey": "sk-new"},
    ]}, merge=True, merge_key="id")
    d3 = {e["id"]: e["apiKey"] for e in json.loads(p3.read_text())["models"]}
    check("深合并: 嵌套 list 按 id 更新", d3["glm-5.2"] == "sk-new")
    check("深合并: 嵌套 list 追加新项", d3.get("glm-5.3") == "sk-new")
    check("深合并: 嵌套 list 用户条目保留", d3["user-own"] == "sk-user")


def test_codebuddy_user_models_preserved():
    """codebuddy models.json 此前全量重写,用户自建模型会丢(与 WorkBuddy 双标)。"""
    mod = load_module()
    tmp = sandbox(mod)
    mod._REMOTE_CATALOG = None
    plan = mod.PLAN_CATALOG["3"]

    models = tmp / ".codebuddy" / "models.json"
    models.parent.mkdir(parents=True, exist_ok=True)
    models.write_text(json.dumps({"models": [
        {"id": "user-own", "name": "自建", "apiKey": "sk-user", "url": "https://x"},
    ]}, ensure_ascii=False))

    import contextlib, io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        mod.configure_codebuddy(plan.base_url, "sk-cb-1234567890", plan)

    data = json.loads(models.read_text())
    ids = [e["id"] for e in data["models"]]
    check("codebuddy: 套餐模型全部写入",
          set(mod.get_model_ids("enterprise-pro")) <= set(ids))
    check("codebuddy: 用户自建模型保留",
          "user-own" in ids and
          [e for e in data["models"] if e["id"] == "user-own"][0]["apiKey"] == "sk-user")


# ---------------------------------------------------------------------------
# 测试组: 安装策略(供应链加固)

def test_install_policy():
    mod = load_module()
    npm_cmds = []
    for t in mod.TOOLS:
        for cmd in (t.install_cmd, t.install_cmd_win):
            if isinstance(cmd, tuple) and cmd and cmd[0] == "npm":
                npm_cmds.append((t.key, cmd))
    check("安装策略: npm 工具全覆盖(>=8)", len(npm_cmds) >= 8)
    check("安装策略: npm 安装一律 --ignore-scripts(拦截 lifecycle 脚本)",
          all("--ignore-scripts" in cmd for _, cmd in npm_cmds))
    check("安装策略: 无 curl|bash 盲管道",
          all(
              "curl" not in " ".join(str(part) for part in (cmd or ()))
              for t in mod.TOOLS
              for cmd in (t.install_cmd, t.install_cmd_win)
          ))
    hermes = mod.TOOL_BY_KEY["hermes"]
    openclaw = mod.TOOL_BY_KEY["openclaw"]
    check("安装策略: hermes 走受控远程脚本",
          hermes.install_script is not None and hermes.install_cmd is None)
    check("安装策略: openclaw 走受控远程脚本", openclaw.install_script is not None)
    check("安装策略: 远程脚本工具支持自动安装(macOS/Linux)",
          mod.supports_auto_install(hermes) or mod.IS_WINDOWS)
    check("安装策略: 不再依赖系统 curl",
          "curl" not in mod.TOOL_DEPENDENCY_REGISTRY.get("hermes", ()))


# ---------------------------------------------------------------------------
# 测试组: 远程脚本执行(fail-closed + 指纹展示)

def test_remote_script():
    mod = load_module()
    sandbox(mod)
    import contextlib, hashlib as _hl, io as _io
    script_body = "#!/bin/sh\necho installed\n"
    digest = _hl.sha256(script_body.encode()).hexdigest()

    executed = {"cmd": None}
    real_http, real_run = mod._http_request, mod.run_command
    mod._http_request = lambda url, **kw: (0, script_body.encode())
    mod.run_command = lambda command, message: (executed.__setitem__("cmd", command), True)[1]

    try:
        # 非交互(EOF):拒绝执行 —— fail-closed,对齐 thcli 非 TTY 拒绝口径
        mod._ASSUME_YES = False
        mod.ask = lambda p="": (_ for _ in ()).throw(EOFError)
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            passed = mod.run_remote_script(
                "https://example.com/install.sh", ("--flag",), "TestTool")
        out = buf.getvalue()
        check("远程脚本: 非交互拒绝执行(fail-closed)",
              passed is False and executed["cmd"] is None)
        check("远程脚本: 展示来源与 SHA256",
              "https://example.com/install.sh" in out and digest in out)

        # 明确拒绝
        mod.ask = lambda p="": "n"
        with contextlib.redirect_stdout(_io.StringIO()):
            passed = mod.run_remote_script(
                "https://example.com/install.sh", ("--flag",), "TestTool")
        check("远程脚本: 用户拒绝 → 不执行", passed is False and executed["cmd"] is None)

        # --yes 跳过确认仍执行
        mod._ASSUME_YES = True
        with contextlib.redirect_stdout(_io.StringIO()):
            passed = mod.run_remote_script(
                "https://example.com/install.sh", ("--flag",), "TestTool")
        cmd = executed["cmd"]
        check("远程脚本: --yes 直接执行", passed is True and cmd is not None)
        check("远程脚本: 以本地文件执行(非管道),参数透传",
              cmd[0] == "bash" and cmd[1].endswith(".sh") and cmd[2] == "--flag")

        # 下载失败(HTTP 错误)
        mod._http_request = lambda url, **kw: (404, b"not found")
        with contextlib.redirect_stdout(_io.StringIO()):
            passed = mod.run_remote_script(
                "https://example.com/install.sh", (), "TestTool")
        check("远程脚本: 下载 404 → 失败", passed is False)

        # 网络层失败
        def _raise(url, **kw):
            raise RuntimeError("conn refused")
        mod._http_request = _raise
        with contextlib.redirect_stdout(_io.StringIO()):
            passed = mod.run_remote_script(
                "https://example.com/install.sh", (), "TestTool")
        check("远程脚本: 网络失败 → 失败且不抛异常", passed is False)
    finally:
        mod._ASSUME_YES = False
        mod._http_request = real_http
        mod.run_command = real_run


# ---------------------------------------------------------------------------
# 测试组: 远程目录完整性(SHA256 fail-closed)

def test_catalog_integrity():
    mod = load_module()
    import contextlib, hashlib as _hl, io as _io
    catalog_bytes = (REPO / "models.json").read_bytes()
    digest = _hl.sha256(catalog_bytes).hexdigest()

    def _fetch_map(body_map):
        def _fetch(url, **kw):
            if url not in body_map:
                raise RuntimeError(f"unexpected url {url}")
            return 0, body_map[url]
        return _fetch

    real_http = mod._http_request
    try:
        # 1) 哈希匹配 → 远程目录生效
        mod._REMOTE_CATALOG = None
        mod._http_request = _fetch_map({
            mod.REMOTE_CATALOG_URL: catalog_bytes,
            mod.REMOTE_CATALOG_SHA256_URL: f"{digest}  models.json\n".encode(),
        })
        with contextlib.redirect_stdout(_io.StringIO()):
            mod.refresh_remote_catalog()
        check("目录校验: 哈希匹配 → 采用远程", mod._REMOTE_CATALOG is not None)

        # 2) 哈希不匹配 → 回退内置
        mod._REMOTE_CATALOG = None
        mod._http_request = _fetch_map({
            mod.REMOTE_CATALOG_URL: catalog_bytes,
            mod.REMOTE_CATALOG_SHA256_URL: ("0" * 64).encode(),
        })
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.refresh_remote_catalog()
        check("目录校验: 哈希不匹配 → 回退内置", mod._REMOTE_CATALOG is None)
        check("目录校验: 不匹配时给出警告", "SHA256" in buf.getvalue())

        # 3) .sha256 获取失败 → 回退内置(fail-closed)
        def _fetch_404(url, **kw):
            if url == mod.REMOTE_CATALOG_SHA256_URL:
                return 404, b"not found"
            return 0, catalog_bytes
        mod._REMOTE_CATALOG = None
        mod._http_request = _fetch_404
        with contextlib.redirect_stdout(_io.StringIO()):
            mod.refresh_remote_catalog()
        check("目录校验: 哈希文件缺失 → 回退内置(fail-closed)",
              mod._REMOTE_CATALOG is None)
    finally:
        mod._http_request = real_http

    # _parse_sha256 宽松解析(sha256sum 常见两种形态)
    check("sha256 解析: sha256sum 双空格格式",
          mod._parse_sha256(f"{digest}  models.json\n") == digest)
    check("sha256 解析: 裸哈希", mod._parse_sha256(digest) == digest)
    check("sha256 解析: 无效内容 → None", mod._parse_sha256("no digest here") is None)


# ---------------------------------------------------------------------------
# 测试组: 退出码契约(0/1/2/3)

def test_exit_codes():
    mod = load_module()
    sandbox(mod)
    mod.verify_api_key = lambda *a: True
    mod.fetch_remote_models = lambda *a: None
    mod.check_prerequisites = lambda tools: True
    mod.refresh_remote_catalog = lambda: None
    mod.run_remote_script = lambda url, sargs, name: False

    def run(argv, answers=None):
        sys.argv = argv
        if answers is None:
            mod.ask = lambda p="": (_ for _ in ()).throw(EOFError)
        else:
            it = iter(answers)
            mod.ask = lambda p="": next(it)
        os.environ.pop("TOKENPLAN_API_KEY", None)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            return mod.main(), buf.getvalue()

    # 未选择工具 → 用户取消(1)
    code, _ = run(["x", "--plan", "enterprise-pro"],
                  ["sk-fake-key-1234567890", "1", "none"])
    check("退出码: 未选工具 → 1", code == 1)

    # 配置器抛错 → 配置失败(3)
    real_cfg = dict(mod.CONFIGURATOR_REGISTRY)
    def _boom(base, key, plan):
        raise RuntimeError("boom")
    for k in real_cfg:
        mod.CONFIGURATOR_REGISTRY[k] = _boom
    code, _ = run(["x", "--plan", "enterprise-pro",
                   "--api-key", "sk-fake-key-1234567890",
                   "--tools", "codex", "--verify-models", "off"], ["1"])
    check("退出码: 配置失败 → 3", code == 3)
    mod.CONFIGURATOR_REGISTRY.clear()
    mod.CONFIGURATOR_REGISTRY.update(real_cfg)

    # 全部成功 → 0
    code, _ = run(["x", "--plan", "enterprise-pro",
                   "--api-key", "sk-fake-key-1234567890",
                   "--tools", "codex", "--verify-models", "off"], ["1"])
    check("退出码: 配置成功 → 0", code == 0)

    # doctor:已安装但配置缺失 → 3(全新沙箱,probe 面对不存在的配置文件)
    sandbox(mod)
    mod.is_tool_installed = lambda t: True
    code, _ = run(["x", "doctor", "--tools", "codex"])
    check("退出码: doctor 配置缺失 → 3", code == 3)

    # doctor --deep 缺 --plan / 缺 Key → 2
    code, _ = run(["x", "doctor", "--deep", "--tools", "codex"])
    check("退出码: doctor --deep 缺 --plan → 2", code == 2)
    code, _ = run(["x", "doctor", "--deep", "--plan", "enterprise-pro",
                   "--tools", "codex"])
    check("退出码: doctor --deep 缺 Key → 2", code == 2)


# ---------------------------------------------------------------------------
# 测试组: --json 结构化输出(密钥打码,stdout 干净)

def test_json_mode():
    mod = load_module()
    sandbox(mod)
    mod.verify_api_key = lambda *a: True
    mod.fetch_remote_models = lambda *a: None
    mod.check_prerequisites = lambda tools: True
    mod.refresh_remote_catalog = lambda: None

    # setup --json
    sys.argv = ["x", "--plan", "enterprise-pro",
                "--api-key", "sk-fake-key-1234567890",
                "--tools", "codex", "--json", "--verify-models", "off"]
    mod.ask = lambda p="": (_ for _ in ()).throw(EOFError)
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = mod.main()
    payload = json.loads(out_buf.getvalue())
    check("JSON: stdout 只有合法 JSON", isinstance(payload, dict))
    check("JSON: 退出码字段一致", payload.get("exit_code") == code == 0)
    check("JSON: 密钥打码(不落明文)",
          payload.get("api_key") != "sk-fake-key-1234567890"
          and payload.get("api_key", "").startswith("sk-f"))
    check("JSON: 工具结果数组",
          payload["tools"][0]["key"] == "codex"
          and payload["tools"][0]["status"] == "configured")
    check("JSON: 过程日志转 stderr", "Codex" in err_buf.getvalue())
    check("JSON: stdout 无过程日志", "已配置" not in out_buf.getvalue())

    # doctor --json
    sandbox(mod)
    mod.is_tool_installed = lambda t: True
    sys.argv = ["x", "doctor", "--tools", "codex", "--json"]
    out_buf, err_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
        code = mod.main()
    payload = json.loads(out_buf.getvalue())
    check("JSON: doctor 结构化结果",
          payload.get("command") == "doctor"
          and payload["tools"][0]["key"] == "codex")
    check("JSON: doctor 退出码 = 3(配置缺失)", code == 3 and payload["exit_code"] == 3)


# ---------------------------------------------------------------------------
# 测试组: TOKENPLAN_API_KEY 环境变量

def test_env_key():
    mod = load_module()
    sandbox(mod)
    mod.verify_api_key = lambda *a: True
    mod.fetch_remote_models = lambda *a: None
    mod.check_prerequisites = lambda tools: True
    mod.refresh_remote_catalog = lambda: None

    sys.argv = ["x", "--plan", "enterprise-pro", "--tools", "none"]
    mod.ask = lambda p="": (_ for _ in ()).throw(EOFError)
    os.environ["TOKENPLAN_API_KEY"] = "sk-from-env-1234567890"
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main()
        out = buf.getvalue()
        check("环境变量 Key: 从 TOKENPLAN_API_KEY 读取", "TOKENPLAN_API_KEY 读取" in out)
        check("环境变量 Key: 不再提示粘贴", "请粘贴" not in out)
    finally:
        os.environ.pop("TOKENPLAN_API_KEY", None)

    # 环境变量 Key 过短 → 警告并回退交互输入(第一个答案被当作 Key 消费)
    os.environ["TOKENPLAN_API_KEY"] = "short"
    try:
        answers = iter(["sk-fake-key-1234567890", "1", "none"])
        prompts = []
        def _ask(prompt=""):
            prompts.append(prompt)
            return next(answers)
        mod.ask = _ask
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main()
        check("环境变量 Key: 过短则警告并回退交互",
              "长度过短" in buf.getvalue() and "已忽略" in buf.getvalue()
              and "请粘贴 API Key" in prompts[0])
    finally:
        os.environ.pop("TOKENPLAN_API_KEY", None)


# ---------------------------------------------------------------------------
# 测试组: 共享 HTTP 入口 _http_request

def test_http_helper():
    mod = load_module()
    real = mod.urllib.request.urlopen
    import urllib.error as _ue

    try:
        # 成功:status 0 + 原始字节
        mod.urllib.request.urlopen = lambda req, timeout=None: io.BytesIO(b'{"data":[]}')
        status, body = mod._http_request("https://x/models")
        check("HTTP: 成功返回 0+原始字节", status == 0 and body == b'{"data":[]}')

        # HTTPError → (code, body),不抛异常
        def _err(req, timeout=None):
            raise _ue.HTTPError(req.full_url, 401, "Unauthorized", {},
                                io.BytesIO(b'{"error":{"message":"bad"}}'))
        mod.urllib.request.urlopen = _err
        status, body = mod._http_request("https://x/models", api_key="k")
        check("HTTP: HTTPError → (code, body)", status == 401 and b"bad" in body)

        # 传输层错误 → RuntimeError(调用方决定提示口径)
        def _netfail(req, timeout=None):
            raise OSError("connection refused")
        mod.urllib.request.urlopen = _netfail
        try:
            mod._http_request("https://x/models")
            check("HTTP: 传输错误 → RuntimeError", False)
        except RuntimeError as exc:
            check("HTTP: 传输错误 → RuntimeError", "connection refused" in str(exc))

        # POST:payload 自动 JSON 编码 + 认证/类型头注入
        captured = {}
        def _capture(req, timeout=None):
            captured["data"] = req.data
            captured["headers"] = dict(req.headers)
            return io.BytesIO(b"{}")
        mod.urllib.request.urlopen = _capture
        status, _ = mod._http_request(
            "https://x/chat/completions", api_key="sk-k",
            payload={"model": "m", "max_tokens": 1})
        auth = next((v for k, v in captured["headers"].items()
                     if k.lower() == "authorization"), "")
        ctype = next((v for k, v in captured["headers"].items()
                      if k.lower() == "content-type"), "")
        check("HTTP: payload JSON 编码",
              json.loads(captured["data"].decode())["model"] == "m")
        check("HTTP: Authorization 头注入", auth == "Bearer sk-k")
        check("HTTP: Content-Type 头注入", "application/json" in ctype)
    finally:
        mod.urllib.request.urlopen = real


# ---------------------------------------------------------------------------
# 测试组: doctor --deep 端到端验证

def test_doctor_deep():
    mod = load_module()
    tmp = sandbox(mod)
    mod.check_prerequisites = lambda tools: True
    mod.is_tool_installed = lambda t: True
    cfg = tmp / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(f'[model_providers.{mod.BRAND_SLUG}]\nname = "{mod.BRAND_VENDOR}"\n')

    plan = mod.PLAN_CATALOG["3"]
    import contextlib, io as _io
    mod.test_model = lambda base, key, model: (True, "")
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.run_doctor([mod.TOOL_BY_KEY["codex"]], deep=True,
                              plan=plan, api_key="sk-k")
    check("doctor --deep: 端到端通过 → 0", code == 0 and "端到端可用" in buf.getvalue())

    mod.test_model = lambda base, key, model: (False, "HTTP 401: bad key")
    buf = _io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = mod.run_doctor([mod.TOOL_BY_KEY["codex"]], deep=True,
                              plan=plan, api_key="sk-bad")
    check("doctor --deep: 端到端失败 → 3", code == 3 and "端到端失败" in buf.getvalue())

    with contextlib.redirect_stdout(_io.StringIO()):
        code = mod.run_doctor([mod.TOOL_BY_KEY["codex"]], deep=True,
                              plan=None, api_key="sk-k")
    check("doctor --deep: 缺 --plan → 2", code == 2)
    with contextlib.redirect_stdout(_io.StringIO()):
        code = mod.run_doctor([mod.TOOL_BY_KEY["codex"]], deep=True,
                              plan=plan, api_key="")
    check("doctor --deep: 缺 Key → 2", code == 2)


# ---------------------------------------------------------------------------
# 测试组: 品牌口径迁移(2.6.0)——TokenHub 统一 + 旧键清理 + 展示优化

def test_brand_migration():
    mod = load_module()
    tmp = sandbox(mod)
    base = "https://tokenhub.tencentmaas.com/plan/v3"
    key = "sk-brand-test-123456"
    plan = mod.PLAN_CATALOG["3"]
    buf = io.StringIO()

    # 常量口径自洽
    check("品牌: slug 不在旧键集合里", mod.BRAND_SLUG not in mod.BRAND_LEGACY_KEYS)
    check("品牌: 常量非空", all([mod.BRAND_NAME, mod.BRAND_SLUG, mod.BRAND_VENDOR]))

    # 套餐分组表覆盖全部套餐且不重复
    grouped = [k for _, keys in mod.PLAN_GROUPS for k in keys]
    check("品牌: 套餐分组全覆盖不重复",
          sorted(grouped) == sorted(p.key for p in mod.PLAN_CATALOG.values()))

    # subprocess 桩:挡掉 pgrep/reg query 等真实调用
    # (stdout/stderr 必须有:Windows 上 get_npm_prefix_dir 经
    #  check_output 取 .stdout,npm 在 CI 上存在会真走到这里)
    real_run = mod.subprocess.run
    mod.subprocess.run = lambda *a, **k: type(
        "R", (), {"returncode": 1, "stdout": b"", "stderr": b""}
    )()

    # Hermes: provider 键与展示名走 TokenHub(用户报告的问题点)
    with contextlib.redirect_stdout(buf):
        mod.configure_hermes(base, key, plan)
    hcfg = (tmp / ".hermes" / "config.yaml").read_text()
    check("hermes: provider 键为 tokenhub", f"provider: {mod.BRAND_SLUG}" in hcfg)
    check("hermes: 展示名为 TokenHub", f"name: {mod.BRAND_NAME}" in hcfg)
    check("hermes: 无旧品牌残留", "token-plan" not in hcfg)

    # OpenCode: 旧 provider 摘除,用户自建 provider 保留
    oc = tmp / ".config" / "opencode" / "opencode.json"
    oc.parent.mkdir(parents=True, exist_ok=True)
    oc.write_text(json.dumps({
        "provider": {
            "openai": {"name": "OpenAI", "options": {"apiKey": "sk-user"}},
            "tokenplan": {"name": "旧名", "options": {"apiKey": "sk-old"}},
        },
    }, ensure_ascii=False))
    with contextlib.redirect_stdout(buf):
        mod.configure_opencode(base, key, plan)
    data = json.loads(oc.read_text())
    check("opencode: 新 provider 键", mod.BRAND_SLUG in data["provider"])
    check("opencode: 旧 provider 键已摘除", "tokenplan" not in data["provider"])
    check("opencode: 用户 provider 保留", "openai" in data["provider"])

    # Pi: 旧键清理
    pi = tmp / ".pi" / "agent" / "models.json"
    pi.parent.mkdir(parents=True, exist_ok=True)
    pi.write_text(json.dumps({"providers": {"tokenplan": {"baseUrl": "x"}}}))
    with contextlib.redirect_stdout(buf):
        mod.configure_pi(base, key, plan)
    pdata = json.loads(pi.read_text())
    check("pi: 旧键摘除", "tokenplan" not in pdata["providers"])
    check("pi: 新键写入", mod.BRAND_SLUG in pdata["providers"])

    # OpenClaw: 旧 provider 及 agents 引用一并清理
    ow = tmp / ".openclaw" / "openclaw.json"
    ow.parent.mkdir(parents=True, exist_ok=True)
    ow.write_text(json.dumps({
        "models": {"mode": "merge", "providers": {
            "tencent-tokenplan": {"baseUrl": "x"},
        }},
        "agents": {"defaults": {"models": {
            "tencent-tokenplan/glm-5.2": {"alias": "glm-5.2"},
        }}},
    }, ensure_ascii=False))
    with contextlib.redirect_stdout(buf):
        mod.configure_openclaw(base, key, plan)
    odata = json.loads(ow.read_text())
    check("openclaw: 旧 provider 摘除",
          "tencent-tokenplan" not in odata["models"]["providers"])
    check("openclaw: 旧 agents 引用摘除",
          not [k for k in odata["agents"]["defaults"]["models"]
               if k.startswith("tencent-")])
    check("openclaw: 新 provider 写入",
          mod.BRAND_SLUG in odata["models"]["providers"])

    # Kimi: 旧 providers 段摘除
    km = tmp / ".kimi-code" / "config.toml"
    km.parent.mkdir(parents=True, exist_ok=True)
    km.write_text('[providers.tokenplan]\ntype = "openai"\nbase_url = "https://old"\n')
    with contextlib.redirect_stdout(buf):
        mod.configure_kimi(base, key, plan)
    ktoml = km.read_text()
    check("kimi: 旧 providers 段摘除", "[providers.tokenplan]" not in ktoml)
    check("kimi: 新 providers 段写入", f"[providers.{mod.BRAND_SLUG}]" in ktoml)

    # Codex: 旧 model_providers 段摘除
    cx = tmp / ".codex" / "config.toml"
    cx.parent.mkdir(parents=True, exist_ok=True)
    cx.write_text(
        '[model_providers.tokenplan]\nname = "Tencent Cloud Token Plan"\n'
        'base_url = "https://old"\nwire_api = "chat"\n'
    )
    real_env = mod.install_codex_shell_env
    mod.install_codex_shell_env = lambda k: None
    try:
        with contextlib.redirect_stdout(buf):
            mod.configure_codex(base, key, plan)
    finally:
        mod.install_codex_shell_env = real_env
    ctoml = cx.read_text()
    check("codex: 旧 model_providers 段摘除",
          "[model_providers.tokenplan]" not in ctoml)
    check("codex: 新段写入", f"[model_providers.{mod.BRAND_SLUG}]" in ctoml)

    # Claude: 旧记账键/旧模型文件/旧启动器清理,新命名生效
    cs = tmp / ".claude" / "settings.json"
    cs.parent.mkdir(parents=True, exist_ok=True)
    cs.write_text(json.dumps(
        {"tokenplan": {"provider": "anthropic"}}, ensure_ascii=False))
    ext = ".cmd" if mod.IS_WINDOWS else ""
    old_launcher = tmp / ".local" / "bin" / f"claude-tokenplan{ext}"
    old_launcher.parent.mkdir(parents=True, exist_ok=True)
    old_launcher.write_text("#!/bin/sh\n")
    with contextlib.redirect_stdout(buf):
        mod.configure_claude_code(base, key, plan)
    cdata = json.loads(cs.read_text())
    check("claude: 旧记账键摘除", "tokenplan" not in cdata)
    check("claude: 新记账键写入", mod.BRAND_SLUG in cdata)
    check("claude: 旧启动器清理", not old_launcher.exists())
    check("claude: 新启动器就位",
          (tmp / ".local" / "bin" / f"claude-{mod.BRAND_SLUG}{ext}").exists())
    check("claude: 新模型文件",
          (tmp / ".claude" / f"{mod.BRAND_SLUG}-models.json").exists())
    check("claude: 旧模型文件清理",
          not (tmp / ".claude" / "tokenplan-models.json").exists())

    # WorkBuddy: 展示名 TokenHub 前缀 + vendor 新口径(顶层是列表)
    with contextlib.redirect_stdout(buf):
        mod.configure_workbuddy(base, key, plan)
    wdata = json.loads((tmp / ".workbuddy" / "models.json").read_text())
    check("workbuddy: 模型名 TokenHub 前缀",
          all(e["name"].startswith(mod.BRAND_NAME) for e in wdata))
    check("workbuddy: vendor 新口径",
          all(e["vendor"] == mod.BRAND_VENDOR for e in wdata))

    # DSH: provider 键与 displayName
    with contextlib.redirect_stdout(buf):
        mod.configure_dsh(base, key, plan)
    dcfg = (tmp / ".dsh" / "settings.yaml").read_text()
    check("dsh: provider 键为 tokenhub", f"    {mod.BRAND_SLUG}:" in dcfg)
    check("dsh: displayName 为 TokenHub", f"displayName: {mod.BRAND_NAME}" in dcfg)

    mod.subprocess.run = real_run

    # probe: 旧品牌配置不误报(2.5.x 用户 doctor 仍绿,repair 即升级)
    hm = tmp / ".hermes" / "config.yaml"
    hm.write_text("model:\n  provider: token-plan\n")
    check("probe: hermes 旧品牌配置 → True",
          mod.probe_config(mod.TOOL_BY_KEY["hermes"]) is True)

    # 动态提示范围: 套餐总数进入提示文案(修复写死的 1-4)
    prompts = []
    def _ask(prompt=""):
        prompts.append(prompt)
        return "1"
    mod.ask = _ask
    with contextlib.redirect_stdout(buf):
        mod.choose_plan()
    total = len(mod.PLAN_CATALOG)
    check("提示: 套餐范围动态生成", f"(1-{total})" in prompts[0] and total > 4)

    # 套餐菜单: 分组标题与受限套餐内联提示
    pbuf = io.StringIO()
    with contextlib.redirect_stdout(pbuf):
        mod.choose_plan()
    menu = pbuf.getvalue()
    check("菜单: 套餐分组标题", all(g in menu for g, _ in mod.PLAN_GROUPS))
    check("菜单: 受限套餐内联提示", "仅支持" in menu)

    # 工具菜单: 状态列(桩掉 is_tool_installed 保证两种状态都出现)
    real_installed = mod.is_tool_installed
    mod.is_tool_installed = lambda t: t.key == "dsh"
    tbuf = io.StringIO()
    with contextlib.redirect_stdout(tbuf):
        mod.choose_tools()
    mod.is_tool_installed = real_installed
    tmenu = tbuf.getvalue()
    check("菜单: 已安装状态列", "✓ 已安装" in tmenu)
    check("菜单: 未安装状态列", "· 未安装" in tmenu)
    check("菜单: 桌面工具手动下载提示", "需手动下载" in tmenu)
    check("菜单: CLI 可自动安装提示", "可自动安装" in tmenu)

    # 横幅: 按显示宽度对齐(中文标题下右边框不漂移)
    bbuf = io.StringIO()
    with contextlib.redirect_stdout(bbuf):
        mod.print_banner(f"{mod.BRAND_NAME} 环境诊断")
    blines = [l for l in bbuf.getvalue().splitlines() if l.strip()]
    widths = {mod.display_width(l) for l in blines}
    check("横幅: 全行显示宽度一致(CJK 对齐)", len(widths) == 1)
    check("横幅: 边框闭合", blines[0].lstrip().startswith("╔")
          and blines[-1].lstrip().startswith("╚"))


TEST_GROUPS = [
    ("registry", test_registry),
    ("registry-windows", test_registry_windows),
    ("toml", test_toml_surgery),
    ("codex", test_codex_config),
    ("uninstall", test_uninstall),
    ("permissions", test_permissions),
    ("postpaid", test_postpaid),
    ("workbuddy", test_workbuddy_config),
    ("new-tools", test_new_tool_configs),
    ("list-merge", test_write_json_list_merge),
    ("doctor-probe", test_doctor_config_probe),
    ("timeout", test_install_timeout),
    ("version", test_version_awareness),
    ("ux", test_ux_helpers),
    ("interactions", test_main_interactions),
    ("catalog", test_remote_catalog),
    ("deep-merge", test_deep_merge),
    ("codebuddy-merge", test_codebuddy_user_models_preserved),
    ("install-policy", test_install_policy),
    ("remote-script", test_remote_script),
    ("catalog-integrity", test_catalog_integrity),
    ("exit-codes", test_exit_codes),
    ("json-mode", test_json_mode),
    ("env-key", test_env_key),
    ("http", test_http_helper),
    ("doctor-deep", test_doctor_deep),
    ("brand-migration", test_brand_migration),
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
