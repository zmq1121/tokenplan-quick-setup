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
- ✅ 前置检查（Node.js、npm、curl）
- ✅ 完成后汇总报告

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
