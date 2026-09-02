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
    check("14 个工具注册", len(mod.TOOLS) == 14)
    check("编号 1-6 为已验证工具(顺序稳定)",
          [t.key for t in mod.TOOLS[:6]] ==
          ["hermes", "codebuddy", "claude-code", "opencode", "openclaw", "dsh"])
    check("索引 1-14 连续", sorted(mod.TOOL_BY_INDEX, key=int) == [str(i) for i in range(1, 15)])
    check("TOOL_BY_KEY 与 TOOLS 一致",
          set(mod.TOOL_BY_KEY) == {t.key for t in mod.TOOLS})
    check("每个配置器都有对应工具 key",
          set(mod.CONFIGURATOR_REGISTRY) <= set(mod.TOOL_BY_KEY))
    check("plugin 工具都有扩展 ID",
          all(t.key in mod.PLUGIN_EXTENSION_IDS for t in mod.TOOLS if t.backend == "plugin"))
    check("backend 全部已注册", all(t.backend in mod.BACKEND_REGISTRY for t in mod.TOOLS))
    check("8 个套餐(4 中国站 + 3 国际站 + 1 后付费)", len(mod.PLAN_CATALOG) == 8)
    check("后付费套餐走 tokenhub /v1 端点",
          mod.PLAN_CATALOG["8"].base_url == "https://tokenhub.tencentmaas.com/v1")
    check("国际站套餐走 intl 端点",
          all(p.base_url.startswith("https://tokenhub-intl.")
              for p in mod.PLAN_CATALOG.values() if p.key.startswith("intl-")))
    check("每个套餐都有模型目录",
          set(p.key for p in mod.PLAN_CATALOG.values()) <= set(mod.MODEL_CATALOG))
    check("配置签名与配置器一一对应",
          set(mod.CONFIG_SIGNATURES) == set(mod.CONFIGURATOR_REGISTRY))
    check("每个签名文件路径存在且特征串非空",
          all(rel and marker for rel, marker in mod.CONFIG_SIGNATURES.values()))


def test_registry_windows():
    mod = load_module(windows=True)
    for key, first in [("codex", "npm"), ("kilo-cli", "npm"),
                       ("kilo-code", "code"), ("cline", "code")]:
        cmd = mod.get_install_command(mod.TOOL_BY_KEY[key])
        check(f"Win: {key} 安装命令以 {first} 开头", cmd is not None and cmd[0] == first)
    check("Win: hermes 不自动安装", mod.get_install_command(mod.TOOL_BY_KEY["hermes"]) is None)
    check("Win: 桌面工具走手动下载",
          all(mod.should_manual_download(mod.TOOL_BY_KEY[k])
              for k in ("workbuddy", "qclaw", "copaw", "autoclaw")))


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
    check("后付费: Claude anthropic 端点(即 /v1,Claude 自动拼 /messages)", env.get("ANTHROPIC_BASE_URL") == base)
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
# 测试组: doctor 配置三态 / 超时 / 版本感知

def test_doctor_config_probe():
    mod = load_module()
    tmp = sandbox(mod)
    tool = mod.TOOL_BY_KEY["codex"]
    check("probe: 引导型工具返回 None", mod.probe_config(mod.TOOL_BY_KEY["qclaw"]) is None)

    # 未配置:文件不存在 → False
    check("probe: 配置文件缺失 → False", mod.probe_config(tool) is False)

    # 已配置:写入含签名的文件 → True
    cfg = tmp / ".codex" / "config.toml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text('model = "glm-5.2"\n\n[model_providers.tokenplan]\nname = "Token Plan"\n')
    check("probe: 签名存在 → True", mod.probe_config(tool) is True)

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
    cfg.write_text('[model_providers.tokenplan]\n')
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
    check("EOF: 配置 14 个", "正在配置 14 个工具" in out)

    out = run(["x", "--plan", "enterprise-pro", "--api-key", "sk-fake-key-1234567890",
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
        out = run(["x", "--plan", "personal-general", "--api-key", "sk-fake-key-1234567890",
                   "--tools", "workbuddy"], ["1"])
        mod.refresh_remote_catalog = _real_refresh
        check("WorkBuddy: 手动下载类仍写配置", "配置已写入" in out)
        wb_models = json.loads((wb_home / ".workbuddy" / "models.json").read_text())
        check("WorkBuddy: 模型真实落盘", len(wb_models) == 10)  # personal-general 目录现为 10 模型
    finally:
        _sp.run = _real

    # 短 key flag 明确报错
    out = run(["x", "--plan", "enterprise-pro", "--api-key", "abc"])
    check("短key: flag 明确报错", "--api-key 传入的 Key 无效" in out)

    # 短 key 交互重试
    out = run(["x", "--plan", "enterprise-pro"], ["short", ""])
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
              (plans[k].get("display") or k == "postpaid")
              for k in plans
          ) and all("default" in plans[k] for k in plans))
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
    ("postpaid", test_postpaid),
    ("workbuddy", test_workbuddy_config),
    ("list-merge", test_write_json_list_merge),
    ("doctor-probe", test_doctor_config_probe),
    ("timeout", test_install_timeout),
    ("version", test_version_awareness),
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
