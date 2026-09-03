"""Domain registries and immutable specifications."""
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple, Union

from tokenplan_setup._model_catalog import MODEL_CATALOG as MODEL_CATALOG
from tokenplan_setup.infrastructure import BRAND_NAME, BRAND_SLUG, BRAND_VENDOR


@dataclass(frozen=True)
class PlanSpec:
    """A TokenHub product tier: display info plus its API base URL and key console URL."""

    choice: str
    key: str
    display_name: str
    base_url: str
    key_url: str
    only_note: str = ""


@dataclass(frozen=True)
class ToolSpec:
    """Declarative registry entry: install command, config location, usage guidance."""

    key: str
    name: str
    backend: str
    check_exe: Optional[str] = None
    install_cmd: Optional[Union[tuple[str, ...], str]] = None
    install_cmd_win: Optional[Union[tuple[str, ...], str]] = None
    # 远程安装脚本(macOS/Linux):走 run_remote_script(下载+SHA256+确认),
    # 不再使用 curl|bash 盲管道;上游未发布固定哈希,故只做展示与确认
    install_script: Optional[str] = None
    install_script_args: Tuple[str, ...] = field(default_factory=tuple)
    win_manual: bool = False
    download_url: Optional[str] = None
    start_hint: str = ""
    cfg_hint: str = ""
    usage_lines: Tuple[str, ...] = field(default_factory=tuple)

# npm registry verification snapshot (queried 2026-09-03).
# Policy: pin `latest` when it is a normal release. DeepSeek Harness has never
# published a non-prerelease version, so its exact `latest` RC is retained and
# marked honestly instead of inventing a stable version.
VERIFIED_TOOL_VERSIONS: Dict[str, Dict[str, str]] = {
    "@tencent-ai/codebuddy-code": {
        "version": "2.143.1",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-E1gWW9osWj4u3d2Fo0cCgT+GqGEXMdaZMIfbH0YI0sQRnuG8WGhxQq1P9oXCTFFJX79FQ6R6jX94nK1Nj2bL3w==",
    },
    "@anthropic-ai/claude-code": {
        "version": "2.1.259",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-kzhz+R36GgL5aouAkeMO9nI1BEIVaRx1NGu0wTTn/H315l61uiLRo13yvva7H10Pfv0PGgzqJ4m+EKv9BzIRXQ==",
    },
    "opencode-ai": {
        "version": "1.18.27",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-5xrG2gQEwV2sLus30SZX9GyLbPX3z57BCxddedDM0wx1bgnwlHVLOS/FD2uve7fEZlmkr7KYFbvs65ySz1rwzA==",
    },
    "openclaw": {
        "version": "2026.8.2",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-I9aqK1attaONePpWs2gPqh23s1s1EDcN/6icF2AAfONdtowu4156QD7g6oD7KlA2vQ9yiqnvlAVH6yduvGH9Ig==",
    },
    "@deepseek-ai/dsh": {
        "version": "0.1.1-rc.2",
        "dist_tag": "latest",
        "stability": "prerelease-only",
        "integrity": "sha512-UP1UIh6q3Gme/yXRn/QL2P8IsVlv8Shpg22TRJIZPsCRWLm4CBiA1MUvXmJAfsOEETBMLAl+xWPtFw6ICsN3wg==",
    },
    "@openai/codex": {
        "version": "0.153.0",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-k55kUZaclNi5ceUStSVuyW834ruA6AEdzTK7Xi3M1mOyXokUmq1sJLXm1RJ3XD2S7bRPeF1EXNsYB5Qxwus0mw==",
    },
    "@moonshot-ai/kimi-code": {
        "version": "0.40.1",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-aiglDy/yFpgVGyT3tiItBJnCx1Cgp9EpuK1N5D609OB9KvABQ67qKv7m56hSr0vnyxU8USJFy1WwWQSgVFo4aA==",
    },
    "@xai-official/grok": {
        "version": "1.0.13",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-rBMEx/7ND5DaBRGwzi6fEyf4ZWy4yStPnZ38UaIM2smZzg4E0fieDfLKPK8eRF4l2Xe4+5kSdCAVop99+whG4A==",
    },
    "@earendil-works/pi-coding-agent": {
        "version": "0.84.4",
        "dist_tag": "latest",
        "stability": "stable",
        "integrity": "sha512-jmOlrqUmvhh/siNWFRXjYLJzhKFIHNsAQaysRwzQPQFnPAaV/vhqHsLH/MBsIISA1Rjj7WTUFR3nJrpXoLx39w==",
    },
}


def verified_npm_spec(package: str) -> str:
    """Return the exact npm package spec from the verified version registry."""
    return f"{package}@{VERIFIED_TOOL_VERSIONS[package]['version']}"


# Claude Code exposes three fixed custom slots. Keep these mappings separate from
# the OpenAI-compatible model catalog so other adapters remain unchanged.
CLAUDE_MODEL_SLOTS = {
    "personal-general": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
    },
    "enterprise-pro": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
    },
    "intl-personal": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
    },
    "intl-enterprise-pro": {
        "opus": "deepseek-v4-pro-202606",
        "sonnet": "glm-5.2",
        "haiku": "deepseek-v4-flash-202605",
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
        only_note="该套餐仅支持混元 Hy 系列模型: Hy3、Hy4-preview",
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
    "5": PlanSpec(
        choice="5",
        key="intl-personal",
        display_name="国际站 - 个人版（新加坡）",
        base_url="https://tokenhub-intl.tencentcloudmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="新加坡地域,不支持跨地域调用;模型列表参照中国站个人版通用套餐",
    ),
    "6": PlanSpec(
        choice="6",
        key="intl-enterprise-pro",
        display_name="国际站 - 企业版专业套餐（新加坡）",
        base_url="https://tokenhub-intl.tencentcloudmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="新加坡地域,不支持跨地域调用",
    ),
    "7": PlanSpec(
        choice="7",
        key="intl-enterprise-light",
        display_name="国际站 - 企业版轻享套餐（新加坡）",
        base_url="https://tokenhub-intl.tencentcloudmaas.com/plan/v3",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="新加坡地域;该套餐仅支持 Auto 模型",
    ),
    "8": PlanSpec(
        choice="8",
        key="postpaid",
        display_name="后付费 - 按量计费（中国站）",
        base_url="https://tokenhub.tencentmaas.com/v1",
        key_url="https://console.cloud.tencent.com/tokenhub/apikey",
        only_note="按 token 计费(非套餐订阅);模型列表由 API 实时发现,需联网",
    ),
    "9": PlanSpec(
        choice="9",
        key="postpaid-intl",
        display_name="后付费 - 按量计费（国际站）",
        base_url="https://tokenhub-intl.tencentcloudmaas.com/v1",
        key_url="https://console.tencentcloud.com/tokenhub/apikey",
        only_note="新加坡地域,按 token 计费(非套餐订阅);模型列表由 API 实时发现,需联网",
    ),
}

# 套餐分组(菜单展示用):组标题 -> 组内套餐 key 顺序,必须覆盖全部套餐
PLAN_GROUPS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("套餐版（包月）", ("personal-general", "personal-hy", "enterprise-pro", "enterprise-light")),
    ("国际站（新加坡）", ("intl-personal", "intl-enterprise-pro", "intl-enterprise-light")),
    ("后付费（按量计费）", ("postpaid", "postpaid-intl")),
)
PLAN_BY_KEY = {item.key: item for item in PLAN_CATALOG.values()}


TOOLS: Tuple[ToolSpec, ...] = (
    ToolSpec(
        key="hermes",
        name="Hermes Agent",
        backend="cli",
        check_exe="hermes",
        start_hint="hermes",
        cfg_hint="~/.hermes/.env",
        install_script="https://hermes-agent.nousresearch.com/install.sh",
        install_script_args=(
            "--skip-browser", "--skip-computer-use", "--skip-setup",
        ),
        win_manual=True,
        download_url="https://hermes-agent.nousresearch.com",
        usage_lines=(
            "终端输入: hermes",
            "切换模型: 输入 /model",
            "模型列表: 由 Hermes 从当前 custom 端点自动发现",
            "Windows: 暂不支持自动安装，请参考官网手动安装后重跑修复模式",
        ),
    ),
    ToolSpec(
        key="codebuddy",
        name="CodeBuddy Code",
        backend="cli",
        check_exe="codebuddy",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("@tencent-ai/codebuddy-code")),
        start_hint="codebuddy",
        cfg_hint="~/.codebuddy/models.json",
        usage_lines=(
            "终端输入: codebuddy",
            f"{BRAND_NAME} 使用 API Key，无需腾讯账号网页登录",
            "如果新窗口提示 command not found，请先执行: source ~/.zshrc",
            "输入 /model 切换模型",
        ),
    ),
    ToolSpec(
        key="claude-code",
        name="Claude Code",
        backend="cli",
        check_exe="claude",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("@anthropic-ai/claude-code")),
        start_hint="claude",
        cfg_hint="~/.claude/settings.json",
        usage_lines=(
            "终端输入: claude",
            "切换模型: claude --model <模型ID>",
            f"完整模型选择器: claude-{BRAND_SLUG}",
            f"重要: Claude 内置 /model 只显示固定槽位，不能显示全部 {BRAND_NAME} 模型",
            f"其它模型请用 claude --model <模型ID>，或运行 claude-{BRAND_SLUG} 选择",
            "glm-5.3 始终思考：已启用 Thinking mode，并默认使用 high effort",
            "模型与强度需分别执行：先提交 /model <模型ID>，成功后再单独提交 /effort low|high|max",
            "不要一次粘贴两行，也不要使用 /model <模型ID> low；它们都会被当成模型 ID",
        ),
    ),
    ToolSpec(
        key="opencode",
        name="OpenCode",
        backend="cli",
        check_exe="opencode",
        start_hint="opencode",
        cfg_hint="~/.config/opencode/opencode.json",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("opencode-ai")),
        usage_lines=(
            "终端输入: opencode",
            "项目初始化: 在 OpenCode 中输入 /init",
            "切换模型: 输入 /models",
            f"{BRAND_NAME} 使用 OpenAI-compatible Chat Completions 端点",
        ),
    ),
    ToolSpec(
        key="openclaw",
        name="OpenClaw",
        backend="cli",
        check_exe="openclaw",
        start_hint="openclaw",
        cfg_hint="~/.openclaw/openclaw.json",
        install_script="https://openclaw.ai/install.sh",
        install_script_args=("--no-onboard",),
        install_cmd_win=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("openclaw")),
        download_url="https://openclaw.ai",
        usage_lines=(
            "终端输入: openclaw",
            "检查配置: openclaw config validate",
            f"仅看套餐模型: openclaw models list --provider {BRAND_SLUG}",
            f"切换模型: openclaw models set {BRAND_SLUG}/<模型ID>",
            "不要运行 /auth tencent-token-plan（openclaw 内置条目，非本安装器配置的 Provider）",
            f"{BRAND_NAME} 使用 API Key，无需 ChatGPT 或其他网页登录",
        ),
    ),
    ToolSpec(
        key="dsh",
        name="DeepSeek Harness",
        backend="cli",
        check_exe="dsh",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("@deepseek-ai/dsh")),
        start_hint="dsh web",
        cfg_hint="~/.dsh/settings.yaml",
        usage_lines=(
            "终端输入: dsh web",
            "浏览器打开: http://127.0.0.1:3080",
            "如果提示 ~/.dsh/cordis.patch.yml 格式错误，未使用自定义 patch 时可删除它",
            "修复: rm ~/.dsh/cordis.patch.yml",
            "或保留文件: printf '%s\\n' '[]' > ~/.dsh/cordis.patch.yml",
        ),
    ),
    ToolSpec(
        key="codex",
        name="Codex CLI",
        backend="cli",
        check_exe="codex",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("@openai/codex")),
        start_hint="codex",
        cfg_hint="~/.codex/config.toml",
        usage_lines=(
            "终端输入: codex",
            "切换模型: 会话中输入 /model，或编辑 ~/.codex/config.toml 的 model 字段",
            "企业/国际/后付费走 responses 协议;个人版走 chat(官方文档规定),已自动配置",
            "个人版注意: Codex 0.152+ 移除了 chat 模式,如遇配置报错需降级 Codex",
            "API Key 环境变量: TOKENPLAN_API_KEY",
        ),
    ),
    ToolSpec(
        key="workbuddy",
        name="WorkBuddy",
        backend="desktop",
        check_exe=None,
        download_url="https://workbuddy.qq.com",
        cfg_hint="~/.workbuddy/models.json",
        usage_lines=(
            "下载安装: https://workbuddy.qq.com（腾讯云 AI 桌面智能体）",
            "模型配置: 安装器已自动写入当前套餐全部模型到 ~/.workbuddy/models.json",
            f"打开 WorkBuddy → 模型选择,即可看到 {BRAND_NAME} 开头的模型",
            "如需手动添加: 设置 → 模型/服务商,Base URL: {base_url}",
        ),
    ),
    ToolSpec(
        key="kimi",
        name="Kimi Code",
        backend="cli",
        check_exe="kimi",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("@moonshot-ai/kimi-code")),
        start_hint="kimi",
        cfg_hint="~/.kimi-code/config.toml",
        usage_lines=(
            "终端输入: kimi",
            f"安装器已写入 {BRAND_SLUG} provider 与套餐模型(config.toml),默认模型已设为套餐默认",
            "切换模型: 会话内 /model,或 kimi -m <模型别名>",
            "配置文件: ~/.kimi-code/config.toml",
        ),
    ),
    ToolSpec(
        key="grok",
        name="Grok CLI",
        backend="cli",
        check_exe="grok",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("@xai-official/grok")),
        start_hint="grok",
        cfg_hint="~/.grok/config.toml",
        usage_lines=(
            "终端输入: grok",
            "安装器已写入套餐模型到 ~/.grok/config.toml 的 [model.*] 段",
            "切换模型: 会话内 /model,或 grok -m <模型名>",
        ),
    ),
    ToolSpec(
        key="pi",
        name="Pi",
        backend="cli",
        check_exe="pi",
        install_cmd=("npm", "install", "-g", "--ignore-scripts", verified_npm_spec("@earendil-works/pi-coding-agent")),
        start_hint="pi",
        cfg_hint="~/.pi/agent/models.json",
        usage_lines=(
            "终端输入: pi",
            f"安装器已写入 {BRAND_SLUG} provider 与套餐模型(models.json)",
            f"切换模型: 会话内 /model,或 pi --model {BRAND_SLUG}/<模型>",
        ),
    ),
    ToolSpec(
        key="zcode",
        name="ZCode",
        backend="desktop",
        check_exe=None,
        download_url="https://zcode.ai",
        cfg_hint="~/.zcode/v2/config.json",
        usage_lines=(
            "下载安装: https://zcode.ai(智谱 ZCode 客户端)",
            "安装器已写入自定义 provider 与套餐模型到 ~/.zcode/v2/config.json",
            f"启动 ZCode 后在模型选择中使用 {BRAND_VENDOR} 条目",
            "该客户端为闭源应用,配置写入未经官方端到端验证,如异常请在应用内手动添加",
        ),
    ),
)


TOOL_BY_INDEX = {str(i + 1): tool for i, tool in enumerate(TOOLS)}
TOOL_BY_KEY = {tool.key: tool for tool in TOOLS}

# 系统/平台依赖单一注册表。doctor、文档和测试均以此为口径；optional
# 表示缺失时只降级相应能力，不应阻断整个安装流程。
SYSTEM_DEPENDENCY_REGISTRY: Dict[str, Dict[str, object]] = {
    "python": {
        "commands": ("python3", "python", "py"),
        "platforms": ("all",),
        "required_by": ("setup.command", "setup.bat", "npx wrapper"),
        "optional": False,
    },
    "node": {
        "commands": ("node",),
        "platforms": ("all",),
        "required_by": ("npm-installed tools",),
        "optional": False,
    },
    "npm": {
        "commands": ("npm",),
        "platforms": ("all",),
        "required_by": ("npm-installed tools", "Windows launchers"),
        "optional": False,
    },
    "npx": {
        "commands": ("npx",),
        "platforms": ("all",),
        "required_by": ("DeepSeek Harness runtime", "npm entrypoint"),
        "optional": False,
    },
    "bash": {
        "commands": ("bash",),
        "platforms": ("posix",),
        "required_by": ("setup.command", "Hermes/OpenClaw remote installers"),
        "optional": False,
    },
    "curl": {
        "commands": ("curl",),
        "platforms": ("windows",),
        "required_by": ("setup.bat download",),
        "optional": False,
    },
    "certutil": {
        "commands": ("certutil",),
        "platforms": ("windows",),
        "required_by": ("setup.bat SHA256 verification",),
        "optional": False,
    },
    "pgrep": {
        "commands": ("pgrep",),
        "platforms": ("posix",),
        "required_by": ("WorkBuddy running-process guard",),
        "optional": True,
    },
    "setx": {
        "commands": ("setx",),
        "platforms": ("windows",),
        "required_by": ("persistent API-key environment variables",),
        "optional": False,
    },
    "reg": {
        "commands": ("reg",),
        "platforms": ("windows",),
        "required_by": ("user env inspection", "uninstall env cleanup"),
        "optional": False,
    },
}

# Per-tool runtime additions. npm/remote-script installation dependencies are
# inferred from ToolSpec; this registry only carries requirements not implied by
# the installer shape.
TOOL_DEPENDENCY_REGISTRY = {
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
}


__all__ = [name for name in globals() if not name.startswith("__")]
