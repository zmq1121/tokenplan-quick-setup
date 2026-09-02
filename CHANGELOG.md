# Changelog

本项目的显著变更记录在此。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

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
