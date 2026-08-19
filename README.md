# 腾讯云 Token Plan — 小白一键接入

> 只需一个 API Key，其余全自动。不会命令行？没关系，打开终端复制粘贴就行。

## 使用方法

### 第一步：获取 API Key

打开 https://console.cloud.tencent.com/tokenhub/api-key 复制 Key。

### 第二步：在终端运行

```bash
python3 setup.py
```

按提示选择版本、输入 Key、选择要配置的工具。脚本会自动：

- ⬇️ **自动下载安装** CLI 工具（CodeBuddy、Claude Code、Codex、Hermes）
- ⚙️ **自动写入配置** 所有工具的配置文件
- 📝 **给出提示** 桌面工具怎么手动配

## 支持的工具

| 工具 | 类型 | 自动安装 | 自动配置 |
|------|------|---------|---------|
| CodeBuddy | CLI | ✅ | ✅ |
| Claude Code | CLI | ✅ | ✅ |
| Codex | CLI | ✅ | ✅ |
| Hermes Agent | CLI | ✅ | ✅ |
| DeepSeek Harness | CLI | ✅ | ✅ |
| Cursor | 桌面 | ❌ (需手动下载) | ✅ |
| Windsurf | 桌面 | ❌ (需手动下载) | ✅ |
| TRAE | 桌面 | ❌ (需手动下载) | 📝 提示 |
| Cline | VS Code 插件 | ✅ | 📝 提示 |
| Kilo Code | VS Code 插件 | ✅ | 📝 提示 |

## 命令行模式（适合脚本/批量）

```bash
python3 setup.py enterprise sk-你的Key
python3 setup.py personal  sk-你的Key
```