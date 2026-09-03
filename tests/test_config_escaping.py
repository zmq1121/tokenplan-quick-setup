"""Ensure API-key credentials round-trip through every text-based config format.

Real Tencent API keys are alphanumeric so injection is not a live threat, but
config writers must not assume that: a bad key ever leaking into a TOML file
should corrupt the credential, not the whole config (or, worse, inject new
sections). These tests exercise the escape path directly.
"""
from pathlib import Path

import pytest

from tokenplan_setup import adapters, domain, flows

# 一次覆盖 TOML 语义所有 corner case: 双引号触发字符串终结、反斜杠触发转义、
# 换行/回车/制表符会被 TOML basic string 拒绝、井号可能被误解成注释、方括号
# 会被误解成新表头(section injection)。
NASTY_KEY = 'quote-"-back\\-newline\n-cr\r-tab\t-hash#-[section]-END'


def test_toml_escape_helper_produces_valid_toml_string() -> None:
    escaped = adapters._toml_escape_basic_string(NASTY_KEY)
    # 关键控制字符不能残留,否则解析器会把它当作换行/终结符。
    for forbidden in ('\n', '\r', '\t'):
        assert forbidden not in escaped
    # 未转义的双引号会截断字符串,反斜杠必须成对出现,才能保证下一个字符
    # 被解释为字面量而不是转义序列。
    unescaped_quotes = escaped.count('"') - escaped.count('\\"')
    assert unescaped_quotes == 0
    assert escaped.count("\\") % 2 == 0


def test_grok_config_survives_a_hostile_api_key(
    isolated_home: Path,
) -> None:
    plan = domain.PLAN_BY_KEY["personal-hy"]
    adapters.configure_grok(plan.base_url, NASTY_KEY, plan)

    config_path = isolated_home / ".grok" / "config.toml"
    text = config_path.read_text(encoding="utf-8")

    # 表头注入检测:任何一行都不能是 `[section]` 这种独立表头。
    # (转义后应形如 `api_key = "…\"[section]\"…"`,只能作为字符串内容出现。)
    for line in text.splitlines():
        assert line.strip() != "[section]"

    try:
        tomllib = __import__("tomllib")
    except ImportError:
        tomllib = None
    if tomllib is not None:
        parsed = tomllib.loads(text)
        # 断言跟随套餐首个模型:目录随官方上/下线变化,写死 ID 会像
        # 'glm-5'(personal-hy 从未有过的模型)一样在 CI 的 tomllib
        # 分支上炸出 KeyError,而本地 <=3.10 无 tomllib 时永远测不到。
        first_model = flows.get_model_ids(plan.key)[0]
        recovered = parsed["model"][first_model]["api_key"]  # first plan model
    else:
        # 3.9/3.10 无 tomllib:退回严格的字符串包含检查,验证 raw 换行/制表符
        # 都以转义序列出现,没有以字面字符出现。
        raw_lines = [line for line in text.splitlines() if line.startswith('api_key = ')]
        assert raw_lines, "grok 配置里没有 api_key 行"
        for line in raw_lines:
            assert "\\n" in line and "\\t" in line and "\\r" in line
        return

    assert recovered == NASTY_KEY


def test_kimi_config_survives_a_hostile_api_key(
    isolated_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adapters, "install_codex_shell_env", lambda *_a, **_k: None)
    plan = domain.PLAN_BY_KEY["personal-hy"]
    adapters.configure_kimi(plan.base_url, NASTY_KEY, plan)

    config_path = isolated_home / ".kimi-code" / "config.toml"
    text = config_path.read_text(encoding="utf-8")

    try:
        tomllib = __import__("tomllib")
    except ImportError:
        # 老 CI 上退回字符级检查:换行/回车/制表符必须以转义序列出现。
        api_lines = [line for line in text.splitlines() if line.startswith('api_key = ')]
        assert api_lines
        for line in api_lines:
            assert "\\n" in line and "\\t" in line and "\\r" in line
        return

    parsed = tomllib.loads(text)
    assert parsed["providers"]["tokenhub"]["api_key"] == NASTY_KEY
