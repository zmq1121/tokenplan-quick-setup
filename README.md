# 腾讯云 Token Plan — 小白一键接入

> 只需 API Key，自动下载 + 配置所有 AI 工具。不会命令行也没关系。

## 方式一：网页版（推荐，不需要会终端）

打开网页，勾选工具，粘贴 Key，复制命令到终端执行。

👉 **https://zmq1121.github.io/tokenplan-quick-setup**

（在 GitHub 仓库 Settings → Pages → Source: main branch → Save 启用）

## 方式二：终端直接运行

```bash
python3 setup.py
```

按提示选择：版本 → 输入 Key → 勾选工具 → 自动安装配置。

## 方式三：一行命令

```bash
python3 -c "$(curl -fsSL https://raw.githubusercontent.com/zmq1121/tokenplan-quick-setup/main/setup.py)"
```

## 支持的工具

| 工具 | 自动安装 | 自动配置 |
|------|---------|---------|
| CodeBuddy | ✅ | ✅ |
| Claude Code | ✅ | ✅ |
| Codex | ✅ | ✅ |
| Hermes Agent | ✅ | ✅ |
| DeepSeek Harness | ✅ | ✅ |
| Cursor | ❌ (需下载) | ✅ |
| Windsurf | ❌ (需下载) | ✅ |
| TRAE | ❌ (需下载) | 📝 |
| Cline | ✅ | 📝 |
| Kilo Code | ✅ | 📝 |