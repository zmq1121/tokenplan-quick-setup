# 腾讯云 Token Plan 一键接入

将腾讯云大模型 API 的接入配置(服务端点、API Key、模型列表)自动写入 12 个 AI 编程工具,运行一次即可完成安装与配置。

面向新用户的完整操作指引见 [使用说明](docs/USER-GUIDE.md)。

## 安装与运行

三种方式均可。

**npx**(需已安装 Node.js):

```bash
npx tokenplan-setup
```

国内网络:

```bash
npx --registry=https://registry.npmmirror.com tokenplan-setup
```

**下载单文件**(无需 Node.js):从 [Releases](https://github.com/zmq1121/tokenplan-quick-setup/releases/latest) 下载对应系统的文件。

- Mac:`setup.command`,在终端中运行 `bash setup.command`
- Windows:`setup.bat`,双击运行

**转发文件**:上述文件可直接通过微信、QQ、邮件发送,接收方无需其它依赖。

`setup.bat` 运行后从固定版本的 Release 附件下载主脚本(多镜像回退)并做 SHA256 校验,通过后执行。Mac 上首次运行若提示无法验证开发者,右键文件选择"打开"并确认。

## 运行环境

- macOS 12+ 或 Windows 10/11,已安装 Python 3(Windows 推荐 `winget install Python.Python.3.12`,安装时勾选 Add to PATH)
- 安装 CLI 类工具(Claude Code、Codex 等)需要 Node.js LTS;未安装时安装器会尝试自动安装
- Hermes Agent 与 OpenClaw 的安装脚本需要 curl

首次安装 CLI 后如提示 `command not found`,重新打开终端或执行 `source ~/.zshrc`。

## 套餐与端点

| 选项 | 套餐 | 站点 | Base URL | API Key 获取 |
|------|------|------|----------|--------------|
| 1 | 个人版 - 通用 | 中国站 | `https://api.lkeap.cloud.tencent.com/plan/v3` | [通用套餐控制台](https://console.cloud.tencent.com/tokenhub/tokenplan/common/api-key) |
| 2 | 个人版 - Hy(混元) | 中国站 | 同选项 1 | [Hy 套餐控制台](https://console.cloud.tencent.com/tokenhub/tokenplan/hy/api-key) |
| 3 | 企业版 - 专业套餐 | 中国站 | `https://tokenhub.tencentmaas.com/plan/v3` | [企业版控制台](https://console.cloud.tencent.com/tokenhub/tokenplan-e/api-key) |
| 4 | 企业版 - 轻享套餐 | 中国站 | 同选项 3 | 同选项 3 |
| 5 | 个人版 | 国际站(新加坡) | `https://tokenhub-intl.tencentmaas.com/plan/v3` | [TokenHub 控制台](https://console.cloud.tencent.com/tokenhub/apikey) |
| 6 | 企业版 - 专业套餐 | 国际站(新加坡) | 同选项 5 | 同选项 5 |
| 7 | 企业版 - 轻享套餐 | 国际站(新加坡) | 同选项 5 | 同选项 5 |
| 8 | 后付费 - 按量计费 | — | `https://tokenhub.tencentmaas.com/v1` | [TokenHub 控制台](https://console.cloud.tencent.com/tokenhub/apikey) |

- 选项 1-7 为包月订阅,不同产品线的 API Key 不通用,请在对应控制台创建
- 选项 8 按 token 计费,模型列表由 `/v1/models` 实时发现并自动过滤非聊天模型,可交互选择或通过 `--models` 参数指定;支持全部 12 个工具
- 国际站仅新加坡地域,不支持跨地域调用

## 支持的工具(12 个)

| # | 工具 | 接入方式 |
|---|------|---------|
| 1 | Hermes Agent | 自动安装 + 自动配置 |
| 2 | CodeBuddy Code | 自动安装 + 自动配置 |
| 3 | Claude Code | 自动安装 + 自动配置 + 模型选择器 |
| 4 | OpenCode | 自动安装 + 自动配置 |
| 5 | OpenClaw | 自动安装 + 自动配置 |
| 6 | DeepSeek Harness | 自动安装 + 自动配置 |
| 7 | Codex CLI | 自动安装 + 自动配置(wire_api 按产品线自动选择,见下方说明) |
| 8 | WorkBuddy | 应用手动下载,套餐模型全量自动写入 `~/.workbuddy/models.json` |
| 9 | Kimi Code | 自动安装 + 自动配置(config.toml,chat completions) |
| 10 | Grok CLI | 自动安装 + 自动配置(config.toml,[model.*] 段) |
| 11 | Pi | 自动安装 + 自动配置(models.json,openai-completions) |
| 12 | ZCode | 应用手动下载,provider 写入 `~/.zcode/v2/config.json`(闭源客户端,配置层验证) |

编号 1-6 为已验证工具,顺序固定。未列出的工具(如 Cursor、TRAE、Kilo、Cline 等)不提供自动配置,也不在本工具的支持范围内。

### 真 Key 验证口径(v2.2.0,2026-09 实测)

| 产品线 | 协议端点 | 工具端到端(真实对话) |
|--------|:---:|:---:|
| 个人通用/混元(lkeap) | chat ✓ / anthropic ✓(responses 无此端点) | Kimi Code ✓ |
| 企业专业/轻享(tokenhub) | chat ✓ / responses ✓ / anthropic ✓ | Codex、Kimi Code、Grok、Pi、Claude Code 全 ✓ |
| 后付费(tokenhub /v1) | chat ✓ / responses ✓ / anthropic ✓ | Kimi Code ✓(130 模型自动发现) |
| 国际版(tokenhub-intl) | 域名路由正常 | 暂未验证(尚无有效 Key) |

ZCode 为配置层写入(格式经两个第三方工具交叉确认,闭源客户端未实测)。

**Codex 在个人版的已知限制**:个人版(lkeap)不提供 Responses 端点,官方文档要求 `wire_api = "chat"`,但 Codex 0.152+ 已移除 chat 模式(上游 [openai/codex#7782](https://github.com/openai/codex/discussions/7782))。安装器对个人版按官方文档写入 `chat` 并在配置时警告;企业/国际/后付费产品线写入 `responses`(真 Key 实测通过)。个人版用户如遇 Codex 报错,需降级 Codex 版本——这是官方文档与新版 Codex 之间的上游冲突,非安装器问题。

Windows 平台差异:Hermes Agent 无官方安装器,安装器会提示手动安装后重跑 `repair`;CodeBuddy 的 API Key 通过 `setx` 写入用户环境变量,需重新打开终端生效;`claude-tokenplan` 选择器以 `.cmd` 文件写入 npm 全局目录。

## 子命令

```bash
bash setup.command setup      # 安装并补全配置(默认)
bash setup.command repair     # 仅修复已安装工具的配置,不重新安装
bash setup.command doctor     # 只读诊断:环境与各工具配置状态
bash setup.command uninstall  # 从备份还原全部修改
```

常用参数:`--plan`、`--api-key`、`--tools`、`--models`(后付费)、`--yes`、`--verify-models`。

## 模型目录更新机制

模型目录有两级来源:优先读取仓库根目录的 [models.json](models.json)(经 jsDelivr CDN 分发),获取失败时使用脚本内置目录。模型发生增减时修改 models.json 并提交即可,已分发的旧安装文件下次运行时自动获取新列表;`latest_version` 字段用于向旧版本文件提示升级。

个人版套餐会额外调用 API `/models` 交叉核对;企业版端点不提供该 API,以目录为准。`python3 scripts/check_models.py` 可将目录与官方文档对照校验。

## Claude Code

`/model` 菜单仅支持 Claude Code 的固定槽位,使用 Token Plan 模型的两种方式:

```bash
claude --model glm-5.2     # 直接指定模型 ID
claude-tokenplan           # 列出当前套餐全部模型,选择后启动
```

完整模型目录写入 `~/.claude/tokenplan-models.json`。

模型与思考强度为两个独立设置,需分两次输入,拼接在一起会返回 403:

```text
/model glm-5.3     # 先切换模型
/effort low        # 切换成功后再调整强度,支持 low/high/max
```

配置脚本写入 `alwaysThinkingEnabled: true`。旧会话如提示"该模型始终思考",退出 Claude Code、重新运行配置并新建会话。

## 其它工具备注

- **OpenClaw**:写入 `~/.openclaw/openclaw.json` 与 `.env`,使用 `tencent-tokenplan` Provider,同时写入 models allowlist 以避免内置模型列表遮挡套餐模型。验证命令:`openclaw models list --provider tencent-tokenplan`
- **OpenCode**:写入 `~/.config/opencode/opencode.json`,使用 `tokenplan` Provider,按 OpenAI 兼容端点生成
- **DeepSeek Harness**:通过本机 `dsh` CLI 接入,启动命令 `dsh web`。如报 `cordis.patch.yml must be a top-level YAML array`,删除该文件或重置为空数组:
  ```bash
  rm ~/.dsh/cordis.patch.yml
  ```
- **WorkBuddy**:写入配置前需完全退出 WorkBuddy,否则其退出时会以内存中的列表覆盖写入结果;用户自建模型条目会保留,重复运行结果幂等

## 开发与测试

```bash
python3 tests/run_tests.py          # 回归测试(135 项,零依赖)
python3 tests/run_tests.py codex    # 运行单个测试组
python3 scripts/check_models.py     # 模型目录与官方文档对照
python3 scripts/sync_npm_lib.py     # 修改 setup.command 后同步 npm 产物
```

测试通过 exec 直接加载 `setup.command`,覆盖注册表完整性、配置器端到端、Windows 平台行为、卸载生命周期、文件权限、交互流 EOF 安全、远程目录回退等。发布 npm 前必须先通过测试再执行同步,一致性校验失败会直接报错。
