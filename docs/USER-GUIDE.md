# 腾讯云大模型 API 接入工具使用说明

## 工具定位

本工具是命令行配置安装器,用于将腾讯云大模型 API 的接入参数(服务端点、API Key、模型列表)写入 Claude Code、Codex 等 12 个 AI 编程工具的配置文件。

它属于配置类工具,与 skill/插件、模型服务是不同的概念:

| 概念 | 说明 |
|------|------|
| 本工具 | 配置安装器,将 API 接入参数写入各工具的配置文件 |
| skill / 插件 | 为 AI 工具扩展能力的程序 |
| 模型服务 | 腾讯云提供的推理能力本身,通过 API Key 调用 |

运行特性:

- 运行一次完成全部配置,之后直接使用对应的 AI 工具
- 不常驻后台、不代理网络流量、不上传数据
- 支持通过 `uninstall` 从备份完整还原
- 当前安装器版本为 2.7.1;Python 运行时要求 3.9+,且无第三方运行时依赖
- 安装器对 npm 工具使用审核清单中的精确版本,不会在安装时自动追随 `latest`

## 获取 API Key

API Key 以 `sk-` 开头,在腾讯云控制台创建。不同产品线对应不同入口:

| 产品线 | API Key 获取地址 |
|--------|------------------|
| 个人版 - 通用 | https://console.cloud.tencent.com/tokenhub/tokenplan/common/api-key |
| 个人版 - Hy(混元) | https://console.cloud.tencent.com/tokenhub/tokenplan/hy/api-key |
| 企业版(专业/轻享) | https://console.cloud.tencent.com/tokenhub/tokenplan-e/api-key |
| 国际站(新加坡) | https://console.cloud.tencent.com/tokenhub/apikey |
| 后付费(按量计费,中国站) | https://console.cloud.tencent.com/tokenhub/apikey |
| 后付费(按量计费,国际站) | https://console.tencentcloud.com/tokenhub/apikey |

安装器在选定套餐后会显示对应的获取地址,可直接前往。

API Key 为账户凭证,请勿转发或截图外发。企业版 Key 由管理员在 TokenHub 控制台分发。

## 运行方式

### 方式一:npx

适用于已安装 Node.js 的环境:

```bash
npx tokenplan-setup
```

国内网络:

```bash
npx --registry=https://registry.npmmirror.com tokenplan-setup
```

### 方式二:下载单文件

从 [Releases 页面](https://github.com/zmq1121/tokenplan-quick-setup/releases/latest) 下载对应系统的文件,不依赖 Node.js。

**Mac**

1. 下载 `setup.command`
2. 打开终端(Spotlight 搜索"终端"或"Terminal")
3. 执行以下命令,可将文件拖入终端窗口自动填充路径:

```bash
bash setup.command
```

**Windows**

下载 `setup.bat`,双击运行。系统询问是否允许更改时选择"是";首次运行自动下载主程序,约需十几秒至一分钟;如安全软件提示,选择允许。

### 方式三:使用他人转发的文件

通过微信、QQ、邮件接收的 `setup.command`(Mac)或 `setup.bat`(Windows)可直接使用,运行方式同上,无需其它依赖。

## 交互流程

安装器依次完成四个步骤:

**步骤一:选择套餐**。按已订阅的产品选择对应编号,共 9 项:中国站个人版 2 项、企业版 2 项、国际站 3 项、后付费 2 项(中国站/国际站)。不确定时以订阅页面显示的名称为准。

**步骤二:输入 API Key**。粘贴后回车,安装器实时验证。验证失败时检查 Key 是否复制完整、与所选套餐是否匹配,然后重新粘贴。

**步骤三:选择运行模式**。直接回车采用标准模式。

**步骤四:选择工具**。列出 12 个工具,直接回车配置全部;输入编号(逗号或空格分隔,如 `3,7,12`)仅配置指定工具。

确认后自动执行:未安装的工具自动安装,配置自动写入,完成后逐项显示结果。

桌面应用中 WorkBuddy 与 ZCode 支持自动写入(模型清单直接落盘);其余桌面应用不在支持范围内。

## 配置完成后

新开终端窗口,输入工具名启动:

| 工具 | 启动命令 |
|------|---------|
| Claude Code | `claude` |
| Codex CLI | `codex` |
| CodeBuddy Code | `codebuddy` |

WorkBuddy 为桌面应用,打开后模型列表已写入完成。

支持的 12 个工具:Hermes Agent、CodeBuddy Code、Claude Code、OpenCode、OpenClaw、DeepSeek Harness、Codex CLI、WorkBuddy、Kimi Code、Grok CLI、Pi、ZCode。

## 维护命令

```bash
bash setup.command doctor      # 诊断:检查环境与各工具配置状态,只读不修改
bash setup.command repair      # 修复:重写配置文件,不重新安装程序
bash setup.command uninstall   # 卸载:从备份还原全部修改
```

诊断的退出码:`0` 全部健康,`2` 环境前置不满足,`3` 存在已安装但配置缺失的工具。

**端到端诊断(doctor --deep)**

普通 doctor 只检查"装没装、配没配";加 `--deep` 会用你的 API Key 真实调用一次对话接口,验证套餐默认模型端到端可用(Key 是否被吊销、套餐是否过期、模型是否下线,一次说清):

```bash
bash setup.command doctor --deep --plan enterprise-pro --api-key <KEY>
# 或使用环境变量
TOKENPLAN_API_KEY=<KEY> bash setup.command doctor --deep --plan enterprise-pro
```

**自动化/脚本场景**

- API Key 优先级:`--api-key` 参数 > 环境变量 `TOKENPLAN_API_KEY` > 交互输入。命令行参数会留在 shell 历史里,推荐环境变量
- `--json`(setup 与 doctor 支持):过程日志转 stderr,stdout 只输出结构化结果,密钥自动打码,便于 jq 解析或落盘存档
- 退出码契约:`0` 成功,`1` 用户取消,`2` 环境或必要参数不满足,
  `3` 配置/诊断/模型验证失败。2.5.0 起失败不再统一返回 0,自动化必须按
  退出码处理

```bash
TOKENPLAN_API_KEY=<KEY> bash setup.command --plan enterprise-pro --yes --json > result.json 2> setup.log
```

## 常见问题

**Mac 双击 setup.command 无反应,或被文本编辑器打开**

macOS 默认不执行未知来源的脚本,请按"运行方式"一节在终端中运行。

**提示 python3: command not found**

- Mac:执行 `xcode-select --install` 安装命令行工具后重试
- Windows:从 https://www.python.org/downloads 安装 Python 3,安装时勾选 Add to PATH

**API Key 验证失败**

1. 确认 Key 复制完整(以 `sk-` 开头的完整字符串)
2. 确认 Key 与所选套餐匹配,不同产品线的 Key 不通用
3. 仍然失败时,到对应控制台重新创建

**后付费与套餐的区别**

套餐(Token Plan)为包月订阅,模型列表固定;后付费按 token 计费,API Key 在 TokenHub 控制台创建,模型列表动态变化,安装器联网自动获取。参考:[TokenHub 首次调用指南](https://cloud.tencent.com/document/product/1823/130058)。

选择后付费后,安装器列出发现的全部聊天模型供选择:

- 直接回车配置全部
- 输入编号(空格或逗号分隔)仅配置所选模型

自动化场景可通过参数指定:

```bash
bash setup.command --plan postpaid --api-key <KEY> --models glm-5.3,kimi-k3 --yes
```

后付费支持全部 12 个工具,与套餐一致。

**安装中断或网络超时**

重新运行即可,已完成的步骤会自动跳过。

**如何确认下载版本与 npm 版本一致**

正式版本使用 `vX.Y.Z` 标签驱动发布。`pyproject.toml`、npm 包、
安装器内置版本和 `models.json.latest_version` 必须精确一致;发布流程会
先跑 Ubuntu/macOS/Windows 的 Python 3.9/3.12/3.13 检查并重建产物,
随后先创建 GitHub Release 并上传固定版本资产,再发布 npm。文档中的真实端到端结果来自
历史人工核验,本地/CI 自动测试不会使用真实 API Key 或宣称重新执行了云端
端到端验证。

**更换套餐或 Key**

重新运行安装器并选择新套餐,配置自动覆盖更新。

**企业安全软件告警**

本工具仅执行三类操作:安装 AI 编程工具、写入工具配置文件、备份原配置;不收集信息、不外传数据。安装来源均可审计:npm 走官方源并统一 `--ignore-scripts`;远程安装脚本(Hermes/OpenClaw,仅 macOS)先下载展示 SHA256 指纹、经确认后才执行。如有需要,可将工具路径提交 IT 部门审核。
