# Changelog

本项目的显著变更记录在此。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2025-09-01

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
