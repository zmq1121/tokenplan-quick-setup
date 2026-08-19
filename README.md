# 腾讯云 Token Plan 一键接入工具

只需 API Key，自动检测并配置所有已安装的 AI 工具。

## 使用方法

### 第一步：获取 API Key

打开 https://console.cloud.tencent.com/tokenhub/api-key 复制 Key。

### 第二步：运行

```bash
python3 setup.py
```

按提示选择版本（个人版/企业版），输入 Key。脚本会自动：

- ✅ 扫描已安装的 AI 工具
- ✅ 自动配置能自动配的（写配置文件）
- 📝 告诉你怎么手动配 GUI 工具

### 命令行模式

```bash
python3 setup.py enterprise sk-你的Key
python3 setup.py personal  sk-你的Key
```

## 支持的工具

| 工具 | 配置方式 |
|------|---------|
| CodeBuddy | ✅ 自动 |
| Claude Code | ✅ 自动 |
| Codex | ✅ 自动 |
| Hermes Agent | ✅ 自动 |
| Cursor | 📝 手动（GUI 设置） |
| Windsurf | 📝 手动（GUI 设置） |
| TRAE | 📝 手动（GUI 设置） |
| DeepSeek Harness | 📝 手动（Web UI） |
| Cline | 📝 手动（插件设置） |
| Kilo Code | 📝 手动（插件设置）