# Changelog

本项目的显著变更记录在此。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.3.2] - 2026-09-02

### 修复

- **后付费端点接错产品**:此前接 lkeap `/v3`(知识引擎老产品),
  导致正确的 TokenHub Key 被误判 401。现按官方文档 1823/130058
  修正为 `tokenhub.tencentmaas.com/v1`,Key 同在 TokenHub 控制台创建;
  Claude Code 用标准 Anthropic 端点 `/v1/messages`(实测 200)

### 改进

- 后付费模型发现增加**聊天能力过滤**:tokenhub /v1/models 实测返回
  130 个模型,其中约 100 个是视频/图像/语音/embedding 等非聊天能力,
  现只把 32 个聊天模型写入工具配置,避免淹没模型下拉框

[1.3.2]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.3.2

## [1.3.1] - 2026-09-02

### 修复

- **手动下载类工具(如 WorkBuddy)此前跳过了配置写入**:主循环把
  manual_download 分支当作"完全跳过",选 13 只打印下载指引,
  models.json 根本没写。现在该分支依然调用配置器(有配置器的工具),
  输出"配置已写入(应用本体需自行下载安装)"
- 工具菜单去掉"编程工具/龙虾工具"分组标题,17 项平铺

[1.3.1]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.3.1

## [1.3.0] - 2026-09-02

### 新增

- **后付费(按量计费)支持**:选项 8,端点 `api.lkeap.cloud.tencent.com/v3`,
  模型列表运行时发现(/v3/models),Claude Code 动态槽位,
  Anthropic 兼容端点 /v3/anthropic 已探活
- 用户文档重写:按产品线分列 Key 获取地址,增加定位说明

[1.3.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.3.0

## [1.2.0] - 2026-09-02

### 新增

- **WorkBuddy 全量模型自动写入**:把当前套餐的全部模型一次性写入
  `~/.workbuddy/models.json`(此前需在应用内逐个手填,每个模型 8 个字段)。
  用户自建模型条目保留;重复运行幂等;写入前检测 WorkBuddy 进程,
  运行中会提示先退出避免被覆盖;文件收紧 0o600
- `doctor` 新增状态:未安装应用但配置已就绪(桌面应用 + 配置可写类)
- `write_json` 支持列表合并(按指定 key 去重更新,保留用户条目)

[1.2.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.2.0

## [1.1.0] - 2026-09-02

### 新增

- 国际站（新加坡）套餐支持：选项 5/6/7（个人版、企业专业、企业轻享），
  端点 `tokenhub-intl.tencentmaas.com`，按官方产品线/站点严格区分
- `doctor` 配置三态：已安装+配置有效 / 配置缺失（提示 repair）/ 未安装，
  直击"工具在但突然用不了"的高频求助场景
- 安装命令 10 分钟超时保护（看门狗线程，静默进程同样生效）
- 旧安装文件版本感知：远程目录携带 latest_version，落后时提示升级

[1.1.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.1.0

## [1.0.0] - 2026-09-01

### 新增

- 17 个工具的接入支持:7 个全自动安装+配置(Hermes、CodeBuddy Code、
  Claude Code、OpenCode、OpenClaw、DeepSeek Harness、Codex CLI)、
  4 个自动安装+引导(Kilo CLI、Kilo Code、Cline)、6 个手动引导
  (Cursor、TRAE、WorkBuddy、Lighthouse OpenClaw、AutoClaw、QClaw、CoPaw)
- CLI 子命令:`setup` / `repair` / `doctor` / `uninstall`
- Windows 支持:setup.bat 三镜像下载、VT100 颜色、setx 环境变量、
  claude-tokenplan.cmd 模型选择器、npm .cmd 垫片重路由
- `uninstall`:基于 manifest.jsonl + state.json 的精确还原
- 端到端模型验证(`--verify-models off|default|all`)
- 远程模型目录 models.json(jsDelivr CDN,失败回退内置)
- npm 分发包装器(`npx tokenplan-setup`)
- 回归测试套件 tests/run_tests.py(67 项,零依赖)

### 安全

- 含 API Key 的配置文件统一 chmod 0o600
- 每次写入前备份至 ~/.tokenplan-backups(manifest 可追溯)

[1.0.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.0.0
