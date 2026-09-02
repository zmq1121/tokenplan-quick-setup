# 腾讯云 Token Plan 一键接入

> 就一个文件，双击就能用。

---

> 📖 **完全不懂命令行？先看 [小白使用说明](docs/USER-GUIDE.md)**——每一步在哪里、点什么、输什么都有图可循。

## Mac 用户

把 `setup.command` 下载到本地后，在终端运行：

```bash
bash setup.command
```

如果想要更短的命令，可以把脚本复制为 `tokenplan-setup` 后运行：

```bash
chmod +x tokenplan-setup
./tokenplan-setup
```

---

## Windows 用户

双击 `setup.bat`（推荐），或在 cmd / PowerShell 中运行：

```bat
setup.bat
setup.bat doctor
```

`setup.bat` 会自动完成：检测 Python（优先 py 启动器）→ 从多个镜像源下载主脚本（国内网络优先 jsDelivr CDN）→ 校验脚本内容 → 运行并透传参数。

也可以直接用 Python 运行主脚本：

```bat
py -3 setup.command doctor
```

---

## 发给用户

| 系统 | 发哪个文件 | 怎么用 |
|------|-----------|--------|
| Mac | `setup.command` | `bash setup.command` |
| Windows | `setup.bat` | 双击运行 |

微信/QQ/邮件直接发一个文件就行。

## 功能

- ✅ 自动检测已安装的 AI 工具（17 个）
- ✅ 自动下载安装 CLI 工具
- ✅ 自动写入配置文件
- ✅ 配置前自动备份原有配置（含备份清单，支持后续还原）
- ✅ API Key 实时验证 + 配置完成后的端到端模型验证
- ✅ 进度条 + 旋转动画
- ✅ 前置检查（Node.js、npm、curl、Mac 架构、Windows 版本）
- ✅ OpenClaw 和 OpenCode 自定义 Provider 配置
- ✅ 完成后汇总报告
- ✅ Windows 支持：npm 类工具自动安装、CodeBuddy 环境变量写入（setx）、claude-tokenplan.cmd 模型选择器
- ✅ 桌面应用分步接入引导（Base URL + API Key 逐步说明）
- ✅ 国际站（新加坡）套餐支持：个人版 / 企业版专业 / 企业版轻享，与中国站按产品线严格区分
- ✅ `doctor` 配置三态诊断：已安装+配置有效 / 已安装+配置缺失（提示 repair）/ 未安装
- ✅ 安装命令 10 分钟超时保护（网络受限时明确报错而非无限转圈）
- ✅ 旧安装文件自动感知新版本（通过远程目录提示升级）

## 支持的工具（17 个）

| # | 工具 | 接入方式 |
|---|------|---------|
| 1 | Hermes Agent | 自动安装 + 自动配置 |
| 2 | CodeBuddy Code | 自动安装 + 自动配置 |
| 3 | Claude Code | 自动安装 + 自动配置 + 模型选择器 |
| 4 | OpenCode | 自动安装 + 自动配置 |
| 5 | OpenClaw | 自动安装 + 自动配置 |
| 6 | DeepSeek Harness | 自动安装 + 自动配置 |
| 7 | Codex CLI | 自动安装 + 自动配置（config.toml，Responses 协议） |
| 8 | Kilo CLI | 自动安装 + /connect 引导配置 |
| 9 | Kilo Code | VS Code 插件自动安装 + Provider 引导 |
| 10 | Cline | VS Code 插件自动安装 + Provider 引导 |
| 11 | Cursor | 手动下载 + Settings→Models 分步引导 |
| 12 | TRAE | 手动下载 + 自定义模型分步引导 |
| 13 | WorkBuddy | 手动下载 + **套餐模型全量自动写入** |
| 14 | Lighthouse OpenClaw | 云端部署场景引导（轻量应用服务器） |
| 15 | AutoClaw | 手动下载 + 自定义接入引导 |
| 16 | QClaw | 手动下载 + 自定义接入引导 |
| 17 | CoPaw | 手动获取 + 自定义接入引导 |

编号 1-6 为已验证工具，配置行为与旧版本完全一致。

## macOS 使用前提

本安装器支持 Intel Mac（x86_64）和 Apple 芯片 Mac（arm64，包括 M1、M2、M3、M4）。短期版本不是完整的系统安装包，运行前请准备：

- macOS 12 Monterey 或更高版本；
- Python 3；
- 网络连接和当前用户的文件写入权限；
- 选择 CodeBuddy Code、Claude Code、OpenCode、OpenClaw 或 DeepSeek Harness 时，需要 Node.js LTS（包含 npm）；这些 CLI 工具若未安装，安装器会先尝试自动安装；
- 选择 Hermes Agent 或 OpenClaw 时，需要 curl；

## Windows 平台说明

- 支持 Windows 10/11（老版本 cmd 已启用 VT100 颜色支持）；
- 需要 Python 3（推荐通过 `winget install Python.Python.3.12` 安装并勾选 Add to PATH）；
- npm 类工具（CodeBuddy Code、Claude Code、OpenCode、OpenClaw、DeepSeek Harness）在 Windows 上自动走 npm 安装；
- Hermes Agent 在 Windows 上暂不支持自动安装（官方仅提供 curl | bash 安装脚本），安装器会提示官网地址，手动安装后重跑 `repair` 模式即可完成配置；
- CodeBuddy 的 API Key 环境变量通过 `setx` 写入用户环境变量，需重新打开终端生效；
- `claude-tokenplan` 模型选择器以 `.cmd` 形式写入 npm 全局目录（该目录默认已在 PATH 中）。
- 选择 CodeBuddy Code、Claude Code、OpenCode、OpenClaw 或 DeepSeek Harness 时，需要 Node.js LTS（包含 npm）；这些 CLI 工具若未安装，安装器会先尝试自动安装；
- 选择 Hermes Agent 或 OpenClaw 时，需要 curl；

如果是全新 Mac，建议先安装 [Node.js LTS](https://nodejs.org/en/download)。首次安装 CLI 后请关闭并重新打开终端；如果提示 `command not found`，执行：

```bash
source ~/.zshrc
```

如果双击 `.command` 被 macOS 拦截，请右键文件，选择“打开”，再确认一次。当前版本会在安装前检查 Mac 架构和关键依赖；缺少 Node.js 或 curl 时会停止并显示修复地址，不会让用户在后续步骤中遇到难以理解的 npm 错误。

## setup.command 使用限制

- 仅支持 macOS 12+，需要 Python 3、网络连接以及当前用户的配置目录写入权限。
- 运行时需要手动输入 API Key；Key 会写入当前用户本机的工具配置，用于工具认证，不会写入 `setup.command` 模板。
- 安装器只修改用户选择的工具配置；未选择的工具不会被安装或重写。
- 如果选择 DeepSeek Harness，需要 Node.js LTS、npm/npx；首次启动由 `npx` 下载或使用本地 DSH 包。
- `setup.command` 是一个 CLI 安装入口；修改套餐或 Key 后需要重新运行。
- macOS 首次拦截 `.command` 时，需要右键选择“打开”。

## DeepSeek Harness 启动故障提示

如果运行 `dsh web` 时提示：

```text
patches ~/.dsh/cordis.patch.yml must be a top-level YAML array
```

说明该文件为空或格式错误。未使用自定义 patch 时可以删除：

```bash
rm ~/.dsh/cordis.patch.yml
dsh web
```

也可以保留文件并重置为空数组：

```bash
printf '%s\\n' '[]' > ~/.dsh/cordis.patch.yml
dsh web
```

如果企业版可以正常运行，通常说明 Node.js、`npx` 和 DSH 主程序本身没有问题，优先检查当前用户目录下的本地 patch 配置。

## OpenClaw 和 OpenCode

安装器会自动安装并配置这两个工具：

- OpenClaw：写入 `~/.openclaw/openclaw.json` 和 `~/.openclaw/.env`，使用 `tencent-tokenplan` Provider；安装器会同时写入 `agents.defaults.models` allowlist，避免内置的一百多个模型遮住 Token Plan 模型。启动后运行 `openclaw models list --provider tencent-tokenplan` 应只看到当前套餐模型。
- OpenCode：写入 `~/.config/opencode/opencode.json`，使用 `tokenplan` 自定义 Provider；其当前配置按 OpenAI-compatible Chat Completions 端点生成，单独使用 OpenAI-compatible Chat Completions 配置。
- DeepSeek Harness：通过本机 `dsh` CLI 接入，启动后运行 `dsh web`；若系统未安装 `dsh`，安装器会先尝试自动安装。

OpenClaw 和 OpenCode 都需要 Node.js/npm；OpenClaw 的安装脚本还需要 curl。首次启动时如果工具提示需要初始化，请按工具提示完成一次初始化即可。

## 套餐与站点

| 选项 | 套餐 | 站点/地域 | Base URL |
|------|------|----------|----------|
| 1 | 个人版 - 通用 | 中国站 | `https://api.lkeap.cloud.tencent.com/plan/v3` |
| 2 | 个人版 - Hy（混元） | 中国站 | 同上 |
| 3 | 企业版 - 专业套餐 | 中国站 | `https://tokenhub.tencentmaas.com/plan/v3` |
| 4 | 企业版 - 轻享套餐 | 中国站 | 同上 |
| 5 | 个人版 | 国际站（新加坡） | `https://tokenhub-intl.tencentmaas.com/plan/v3` |
| 6 | 企业版 - 专业套餐 | 国际站（新加坡） | 同上 |
| 7 | 企业版 - 轻享套餐 | 国际站（新加坡） | 同上 |

> 国际站仅新加坡地域，不支持跨地域调用。国际站企业版模型表与中国站一致（官方文档"新加坡"章节核实）；国际站个人版模型列表参照中国站通用套餐，建议首次配置后用 `--verify-models default` 端到端验证。API Key 统一在 [TokenHub 控制台](https://console.cloud.tencent.com/tokenhub/apikey) 管理。

## CLI 使用说明

本安装器现在是一个终端 CLI 入口，默认命令为：

```bash
bash setup.command
```

也可以把它复制成 `tokenplan-setup` 后运行：

```bash
chmod +x tokenplan-setup
./tokenplan-setup
```

支持的子命令：

- `setup`：安装并补全配置，默认模式；
- `repair`：仅修复已安装工具的配置；
- `doctor`：只检查环境和安装状态（含 Token Plan 配置块是否完好），不修改任何文件；
- `uninstall`：从备份还原配置，并清理安装器写入的文件/环境变量/PATH 修改。

例如：

```bash
bash setup.command doctor
bash setup.command repair --plan enterprise-pro --tools dsh,opencode
bash setup.command --version
```

## 模型列表更新机制

模型目录有两级来源：

1. **远程目录（优先）**：仓库根目录的 [models.json](models.json)，安装器启动时通过 jsDelivr CDN 拉取。**新模型上线只需修改这个 JSON 并提交**，所有已分发出去的安装器（包括旧的微信文件）下次运行时自动拿到新列表，无需重新发文件；
2. **内置目录（回退）**：`setup.command` 内的 `MODEL_CATALOG`，远程不可用（离线/CDN 被墙）时使用。

个人版套餐还会额外调用 API `/models` 端点做交叉核对；企业版端点不提供该 API，以策展目录为准。国际站企业套餐模型与中国站一致；国际站个人版参照中国站通用套餐（官方国际站文档暂无法程序化抓取，可通过远程目录随时修正）。

远程目录同时携带 `latest_version` 字段：旧版本安装文件运行时会自动提示"发现新版本"，微信分发的旧文件由此获得升级通知渠道。

## 开发与测试

```bash
python3 tests/run_tests.py          # 全部回归测试（118 项，零依赖）
python3 tests/run_tests.py codex    # 只跑某一组
python3 scripts/sync_npm_lib.py     # 修改 setup.command 后同步 npm 构建产物
```

`tests/run_tests.py` 通过 exec 直接加载 `setup.command`（与真实运行路径一致），覆盖：注册表完整性（17 工具、编号稳定）、docstring 覆盖率、Windows 平台行为模拟、TOML 手术安全性、Codex 配置器端到端、卸载生命周期、文件权限、交互流 EOF 安全、远程目录回退、npm/lib 字节一致性与版本号一致性。

发布 npm 前务必先跑测试再执行 `scripts/sync_npm_lib.py`——一致性校验失败会直接报错。

## Claude Code 模型选择说明

Claude Code 的内置 `/model` 菜单只能显示 Claude Code 支持的固定槽位，不能把 Token Plan 的全部模型都加入菜单。

- `/model`：只能显示 Claude Code 的固定模型槽位；
- `claude --model <模型ID>`：直接使用指定的其它 Token Plan 模型；
- `claude-tokenplan`：列出当前产品线的完整模型列表，选择后自动启动 Claude Code。

例如：

```bash
claude --model glm-5.2
claude-tokenplan
```

Claude Code 中，模型和思考强度是两个独立设置，不能把思考级别拼到 `/model` 命令后面。请先单独输入 `/model glm-5.3` 并按回车，等待切换成功后，再另行输入 `/effort low` 并按回车；不要一次粘贴两行：

```text
/model glm-5.3
```

切换成功后再单独执行：

```text
/effort low
```

也可以使用 `high` 或 `max`：

```text
/effort high
/effort max
```

下面两种写法都会把后续内容当成模型 ID，因而收到“模型不支持”的 403：

```text
/model glm-5.3 low
```

```text
/model glm-5.3
/effort low
```

脚本还会写入 `alwaysThinkingEnabled: true`。如果旧会话仍提示“该模型始终思考，不支持关闭思考”，请退出 Claude Code、重新运行配置脚本并新建会话；也可以在 `/config` 中确认 `Thinking mode` 为开启状态。底部的 `high · /effort` 只表示思考强度，并不等于 Thinking mode 已开启。

如果新终端提示找不到 `claude-tokenplan`，先执行：

```bash
source ~/.zshrc
```

完整模型目录会写入：

```text
~/.claude/tokenplan-models.json
```

