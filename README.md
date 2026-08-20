# 腾讯云 Token Plan 一键接入

> 就一个文件，双击就能用。

---

## Mac 用户

把 `setup.command` 存到桌面 → **双击** → 三步完成。

## Windows 用户

把 `setup.bat` 存到桌面 → **双击** → 三步完成。

---

## 发给用户

| 系统 | 发哪个文件 | 怎么用 |
|------|-----------|--------|
| Mac | `setup.command` | 双击 |
| Windows | `setup.bat` | 双击 |

微信/QQ/邮件直接发一个文件就行。

## 功能

- ✅ 自动检测已安装的 AI 工具
- ✅ 自动下载安装 CLI 工具
- ✅ 自动写入配置文件
- ✅ 配置前自动备份原有配置
- ✅ API Key 实时验证
- ✅ 进度条 + 旋转动画
- ✅ 前置检查（Node.js、npm、curl、Mac 架构）
- ✅ OpenClaw 和 OpenCode 自定义 Provider 配置
- ✅ 完成后汇总报告

## macOS 使用前提

本安装器支持 Intel Mac（x86_64）和 Apple 芯片 Mac（arm64，包括 M1、M2、M3、M4）。短期版本不是完整的系统安装包，运行前请准备：

- macOS 12 Monterey 或更高版本；
- Python 3；
- 网络连接和当前用户的文件写入权限；
- 选择 CodeBuddy Code、Claude Code 或 Codex 时，需要 Node.js LTS（包含 npm）；
- 选择 Hermes Agent 或 OpenClaw 时，需要 curl；
- 选择 Cline 或 Kilo Code 时，需要已安装 VS Code 和 `code` 命令。

如果是全新 Mac，建议先安装 [Node.js LTS](https://nodejs.org/en/download)。首次安装 CLI 后请关闭并重新打开终端；如果提示 `command not found`，执行：

```bash
source ~/.zshrc
```

如果双击 `.command` 被 macOS 拦截，请右键文件，选择“打开”，再确认一次。当前版本会在安装前检查 Mac 架构和关键依赖；缺少 Node.js 或 curl 时会停止并显示修复地址，不会让用户在后续步骤中遇到难以理解的 npm 错误。

## OpenClaw 和 OpenCode

安装器会自动安装并配置这两个工具：

- OpenClaw：写入 `~/.openclaw/openclaw.json` 和 `~/.openclaw/.env`，使用 `tencent-tokenplan` Provider；安装器会同时写入 `agents.defaults.models` allowlist，避免内置的一百多个模型遮住 Token Plan 模型。启动后运行 `openclaw models list --provider tencent-tokenplan` 应只看到当前套餐模型。
- OpenCode：写入 `~/.config/opencode/opencode.json`，使用 `tokenplan` 自定义 Provider；其当前配置按 OpenAI-compatible Chat Completions 端点生成，不与 Codex 的 Responses API 配置混用。

OpenClaw 和 OpenCode 都需要 Node.js/npm；OpenClaw 的安装脚本还需要 curl。首次启动时如果工具提示需要初始化，请按工具提示完成一次初始化即可。

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

## Codex 模型说明

Codex 使用 Token Plan 时，脚本会优先写入当前套餐中的具体默认模型，并使用新版 `responses` 接口。对于只有 Auto 路由的轻享套餐仍会保留 `auto`；其它有具体模型的套餐不要把 `model` 手动改成 `auto`，否则新版 Codex 可能提示：

```text
Model metadata for `auto` not found
```

重新运行脚本配置 Codex 后即可恢复正确的默认模型。
