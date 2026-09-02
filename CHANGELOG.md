# Changelog

本项目的显著变更记录在此。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.6.0] - 2026-09-02

### 变更

- **工具列表 15 → 14**:移除 TRAE。火山方舟官方 arkcli 的二进制中
  明确写着 "Trae does not support model/provider configuration"——
  TRAE 的模型列表为服务端管控,厂商级 CLI 也无法写入,本安装器维持
  引导模式已无意义,直接移除(逆向结论存档于 1.5.0 条目)

### 安全加固(对标 arkcli)

- **setup.bat 下载完整性校验**:改从固定版本 Release 附件下载主脚本
  (不再跟随 @main 漂移),并用 certutil 做 SHA256 校验,镜像被篡改
  或文件损坏时拒绝执行;版本号与哈希由 `scripts/sync_npm_lib.py`
  自动注入,CI 校验三者一致,忘跑同步会直接红
- **备份文件权限收紧**:`~/.tokenplan-backups/ 下的备份一律 chmod
  0600(此前继承源文件权限,源为 0644 时含 Key 的备份也 0644)
- **env 文件统一走 write_env**:CodeBuddy/Codex 的 sourced env 此前
  直写无备份,现在备份 + 保留用户已有行 + 0600;write_env 新增
  export 模式(source 场景变量需导出)

[1.6.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.6.0

## [1.5.0] - 2026-09-02

### 变更

- **工具列表 17 → 15**:移除 Cursor 与 Lighthouse OpenClaw。
  Cursor 的自定义模型仅支持界面录入,无公开配置文件;Lighthouse 为
  云端部署场景,不属于本机配置。两者保留在历史版本,后续按需恢复
- TRAE 保持分步引导模式(直写其 state.vscdb 的条目无法通过启动时
  的服务端校验,已在 CHANGELOG 存档逆向结论)

### 修复(测试)

- WorkBuddy 数量断言在本机受 CDN 陈旧缓存影响:子测试此前只钉了
  `_REMOTE_CATALOG` 但 main() 内的 refresh 会重新拉取边缘缓存覆盖,
  现在 refresh 一并 mock,断言彻底离线化

[1.5.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.5.0

## [1.4.2] - 2026-09-02

### 模型目录更新(中国站个人版,官方文档 1823/130060)

- **通用套餐(选项 1)** 8 → 10 个:新增 MiniMax-M3(`minimax-m3`)、
  GLM-5.3(`glm-5.3`)、Kimi-K2.7-Code(`kimi-k2.7-code`);
  移除已下线的 Kimi-K2.5
- **Hy 套餐(选项 2)** 1 → 2 个:新增 Hy4 preview(`hy4-preview`,
  官方注明高峰可能限频)
- 新模型已用真实套餐 Key 逐个端到端验证(全部 HTTP 200)
- `scripts/check_models.py` 个人版对照文档从旧快速入门 130119
  切换到套餐详情页 130060(2026-09 起权威源);模型词根正则支持 hy4

[1.4.2]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.4.2

## [1.4.1] - 2026-09-02

### 改进

- 端到端模型验证对 **5xx 网关瞬时错误自动重试一次**(间隔 2 秒):
  此前 tokenhub 网关偶发 upstream_error 502 会被直接报告为
  "模型验证失败",实为服务端瞬时故障;重试后仍失败才如实告警,
  并注明"疑似服务端瞬时故障"。4xx(权限/参数类)不重试

[1.4.1]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.4.1

## [1.4.0] - 2026-09-02

### 新增

- **后付费模型自选**:发现模型后弹出编号列表(32 个聊天模型),
  直接回车 = 全部,输入编号/模型名(空格或逗号分隔)= 只配置所选;
  命令行可用 `--models glm-5.3,kimi-k3` 指定(自动化场景配 --yes)
- Claude Code 槽位挑选改为精确匹配优先(修复 glm-5.3 被
  glm-5.3-flash 子串抢位)

### 说明

- 后付费(选项 8)支持**全部 17 个工具**,非仅 WorkBuddy:发现列表
  填入共享模型目录后,所有配置器(Claude Code/Codex/WorkBuddy/…)
  均已验证可用;/v1/messages(Anthropic)与 /v1/responses(Codex)
  端点均实测 200

[1.4.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v1.4.0

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
