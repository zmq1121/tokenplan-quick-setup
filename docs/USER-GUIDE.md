# 腾讯云大模型 API · 一键接入说明

## 这是什么

本工具是一个**配置生成器**(命令行安装器),不是 skill、不是插件,也不是模型本身。

它做的事情只有一件:把你订阅的腾讯云大模型 API(Token Plan 套餐或后付费按量计费)的接入参数——**服务端点、API Key、模型列表**——自动写入 Claude Code、Codex、Cursor 等 17 个 AI 编程工具的配置文件。

- 运行一次即可,之后正常打开那些工具就能用
- 不常驻后台、不代理流量、不上传任何数据
- 随时可用 `uninstall` 完整还原

> 与 skill 的区别:skill 是给 AI 工具扩展能力的插件;本工具帮你**配置这些工具本身**,两者互补。

## 准备:获取 API Key

API Key(`sk-` 开头)在腾讯云控制台获取,**不同套餐入口不同**:

| 你订阅的产品 | API Key 获取地址 |
|------|------|
| 个人版 - 通用 | https://console.cloud.tencent.com/tokenhub/tokenplan/common/api-key |
| 个人版 - Hy(混元) | https://console.cloud.tencent.com/tokenhub/tokenplan/hy/api-key |
| 企业版(专业/轻享) | https://console.cloud.tencent.com/tokenhub/tokenplan-e/api-key |
| 国际站(新加坡) | https://console.cloud.tencent.com/tokenhub/apikey |
| 后付费 - 按量计费 | https://console.cloud.tencent.com/lkeap/apikey |

也可以先运行安装器:选择套餐后,屏幕会显示该套餐对应的获取地址,前往即可。

**注意**:API Key 等同于账户凭证,不要转发给他人或截图外发。企业 Key 由管理员在 TokenHub 控制台分发。

## 运行

### Mac

1. 获取 `setup.command` 文件(群文件或同事转发),放到任意目录
2. 打开"终端"(Spotlight 搜索"终端"或"Terminal")
3. 执行(将文件拖入终端窗口可自动填充路径):

```bash
bash setup.command
```

### Windows

双击 `setup.bat`。

- 系统询问"是否允许更改"时选择"是"
- 首次运行会自动下载主程序(约需十几秒至一分钟)
- 若安全软件提示,选择允许:本工具仅写入本机工具配置文件

## 交互流程

安装器依次提出四个问题:

**① 选择套餐** —— 按订阅的产品选择对应编号。共 8 项:中国站个人版 2 项、企业版 2 项,国际站 3 项,后付费 1 项。不确定时,以订阅页面显示的名称为准。

**② 输入 API Key** —— 粘贴后回车。安装器会实时验证:
- 验证通过 → 继续
- 验证失败 → 检查是否复制完整、Key 与套餐是否匹配,重新粘贴

**③ 选择运行模式** —— 直接回车(标准模式)。

**④ 选择工具** —— 列出 17 个工具:
- 回车 = 全部配置(推荐)
- 输入编号(逗号分隔,如 `3,7,13`)= 只配置指定工具

之后自动执行:未安装的工具自动安装,配置自动写入,完成后逐项显示结果与使用方法。

桌面应用(Cursor、TRAE 等)无法自动写入配置,安装器会输出需要手动填写的字段值(端点地址、Key),在应用设置中粘贴一次即可。

## 完成后如何使用

新开一个终端窗口,输入工具名启动:

| 工具 | 启动命令 |
|------|---------|
| Claude Code | `claude` |
| Codex CLI | `codex` |
| CodeBuddy Code | `codebuddy` |
| WorkBuddy | 打开应用,模型列表已自动写入 |

支持的 17 个工具:Hermes Agent、CodeBuddy Code、Claude Code、OpenCode、OpenClaw、DeepSeek Harness、Codex CLI、Kilo CLI、Kilo Code、Cline、Cursor、TRAE、WorkBuddy、Lighthouse OpenClaw、AutoClaw、QClaw、CoPaw。

## 维护命令

```bash
bash setup.command doctor      # 诊断:检查环境与各工具配置状态(只读,不修改)
bash setup.command repair      # 修复:重写配置文件(不重装程序)
bash setup.command uninstall   # 卸载:从备份还原全部修改
```

## 常见问题

**Q: Mac 双击 setup.command 无反应或被文本编辑器打开**
macOS 默认不执行未知来源脚本。请使用上文"运行"一节的终端方式。

**Q: 提示 python3: command not found**
Mac:执行 `xcode-select --install` 安装命令行工具后重试。
Windows:从 https://www.python.org/downloads 安装(勾选 Add to PATH)。

**Q: API Key 验证失败**
1. 确认 Key 复制完整(`sk-` 开头的完整字符串)
2. 确认 Key 与所选套餐匹配(不同产品线的 Key 不通用)
3. 仍失败时,到对应控制台重新创建 Key

**Q: 后付费(选项 8)与套餐的区别**
套餐(Token Plan)是包月订阅,模型固定;后付费按实际用量计费,模型列表动态变化。后付费模式需联网获取模型列表,安装器会自动完成。

**Q: 安装中断或网络超时**
重新运行即可。已完成的步骤会跳过,不会重复安装。

**Q: 更换套餐或 Key**
重新运行安装器选择新套餐即可,配置会被覆盖更新。

**Q: 公司安全软件报警**
本工具仅执行三类操作:安装 AI 编程工具、写入工具配置文件、备份原配置。不收集信息、不外传数据。如有需要,可将工具路径提交 IT 部门加白。
