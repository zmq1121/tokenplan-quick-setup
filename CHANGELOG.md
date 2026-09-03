# Changelog

本项目的显著变更记录在此。版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [2.6.1] - 2026-09-03

### 修复

- 个人版 Hy 套餐的提示文案更新为"仅支持混元 Hy 系列模型: Hy3、Hy4-preview"
  (目录自 2.3.0 起已含 hy4-preview,但 `only_note` 仍写"仅支持 Hy3 模型";
  2.6.0 把该提示挪进套餐菜单行内后,过时文案被直接暴露。仅文案修正,
  模型目录无变化——已装用户经远程目录早已拿到 hy4-preview)
- `models.json` 的 `latest_version` 停留在 2.4.0(2.5.0/2.6.0 两次发布
  均漏更,旧安装器的升级提示失效)。现由 `sync_npm_lib.py` 随发布自动
  对齐,consistency 测试新增守卫断言

### 验证(发布前核验,2026-09-03)

- 9 套餐端点全探测通过(chat/anthropic 路由无漂移)
- 国际站后付费(选项 9)真 Key 补验:`/v1/models` 发现 44 模型(聊天过滤
  26 个),chat/responses/anthropic 三协议真实对话通过,Claude 槽位挑选
  与 Codex(responses)配置链路验证通过——README 验证矩阵的最后一个
  "待验证"标注已划掉,8 条产品线全部真 Key 实测完毕

## [2.6.0] - 2026-09-03

### 品牌口径统一:TokenHub(修复用户可见的名称错位)

**① 工具内显示名与 provider 键全部收敛为 TokenHub**

接入平台是腾讯云 TokenHub(端点域名/控制台口径),但 2.5.x 写入各工具的
provider 名称是安装器内部名("Token Plan"/`tokenplan`/`token-plan`/
`tencent-tokenplan`)——用户在 Hermes 等工具里看到的是与所接入平台无关的
名称。现在集中由四个常量派生(`BRAND_NAME`/`BRAND_SLUG`/`BRAND_VENDOR`/
`BRAND_LEGACY_KEYS`),12 个工具的配置全部迁移:provider 键 `tokenhub`、
展示名 TokenHub、模型前缀 `tokenhub/<model>`;Claude 的启动器命令更名为
`claude-tokenhub`,模型文件更名为 `tokenhub-models.json`。

**② 旧品牌配置平滑升级**

- 各 configurator 重写配置时自动摘除 2.5.x 旧键(JSON 逐键 pop、TOML 按
  段删除、Grok 按托管块剥离、Claude 旧启动器/旧模型文件清理),不会出现
  两套 provider 并存
- `doctor` 的 `probe_config` 对旧品牌特征同样返回"配置有效"(旧配置仍能
  正常工作,不误报缺失);重跑一次 repair 即完成品牌升级
- 刻意保留:rc 文件 marker、`TOKENPLAN_API_KEY` 环境变量名、npm 包名
  `tokenplan-setup`(避免破坏已发布文档与用户 shell 配置)

### 交互展现优化

- **修复套餐选择提示范围写死**:菜单有 9 个套餐但提示写"请输入数字 (1-4)"
  ——改为按 `PLAN_CATALOG` 动态生成(运行模式菜单同样处理)
- **套餐菜单分组**:按"套餐版(包月)/ 国际站(新加坡)/ 后付费(按量计费)"
  三组展示;模型受限的套餐(Hy 仅 Hy3、轻享仅 Auto)在菜单行内就地提示
- **工具菜单加实时状态列**:逐工具显示"✓ 已安装 / · 未安装"与
  "可自动安装 / 需手动下载",选择前即可判断
- **横幅 CJK 对齐**:新增 `print_banner()`/`display_width()`,按终端显示
  宽度(全角算 2 列)居中与补位,中文标题下右边框不再漂移;列表列对齐
  同样按显示宽度计算

### 测试

新增 `brand-migration` 测试组:品牌常量自洽、套餐分组全覆盖、各工具旧键
摘除与用户配置保留、probe 旧品牌兼容、动态提示范围、菜单状态列、横幅
对齐;回归总数 229 → 270。

## [2.5.0] - 2026-09-03

### 安全与规范性(对齐官方 tokenhub-cli 的工程标准)

**① 修复 `write_json` 浅合并静默丢失用户配置(严重)**

`merge=True` 此前用 `existing.update(data)` 只合并顶层——用户 opencode/
openclaw/claude/codebuddy 配置里**同级的其它 provider 会被整块顶掉**。
现在改为递归深合并:dict 逐键下钻,嵌套 list 在给定 `merge_key` 时按
标识合并(保留用户条目,仅替换/追加我方条目),其余类型以新值覆盖。
`.codebuddy/models.json` 同时补上 `merge_key="id"`(此前全量重写,
用户自建模型会丢,与 WorkBuddy 的合并标准不一致)。

**② 远程安装脚本不再 `curl | bash` 盲执行**

hermes / openclaw(macOS)此前直接管道执行第三方远程脚本。现在:
先完整下载到本地临时文件 → 展示来源 URL、SHA256 与大小 → 交互确认
→ 才执行。非交互环境一律拒绝(fail-closed)。上游官方脚本未发布固定
哈希,无法做下载前校验,这是该约束下的最大化改进。`--yes` 跳过确认
但指纹仍完整打印。系统 curl 依赖同时取消(改用 Python 内建下载)。

**③ npm 安装统一 `--ignore-scripts`**

此前仅 Pi 加了该参数。npm lifecycle 脚本是供应链攻击重点面(新版 npm
默认拦截的正是它),这些 CLI 均通过平台包分发二进制、不需要安装期脚本。

**④ 远程模型目录加 SHA256 完整性校验(fail-closed)**

`models.json` 从 jsDelivr 拉取时无任何完整性校验。现在同时拉取
`models.json.sha256`(由 `sync_npm_lib.py` 自动再生),哈希不匹配或
拿不到哈希文件 → 一律回退内置目录,绝不下发无法证明完整性的内容——
CDN 缓存错位与劫持同归此路径。

**⑤ 退出码契约规范化**

失败路径此前返回 0,脚本/CI 无法判断成败。现在:`0=成功 1=用户取消
2=环境不满足 3=部分工具配置失败`;doctor 按健康度返回(配置缺失=3、
前置不满足=2)。

**⑥ `--json` 结构化输出(setup / doctor)**

过程日志转 stderr,stdout 只输出结果 JSON;**密钥在 JSON 里一律打码**
(JSON 会被转发、落盘、进对话历史,暴露面远大于终端看一眼)。
字段:`plan` / `base_url` / `models` / `tools[]`(configured|failed|
skipped + error)/ `verified` / `exit_code`。

**⑦ `TOKENPLAN_API_KEY` 环境变量**

Key 解析顺序:`--api-key` 参数 > 环境变量 > 交互输入。命令行参数会留在
shell 历史里,自动化场景推荐环境变量。

**⑧ `doctor --deep` 端到端验证**

doctor 此前只查"装没装/配没配"。`--deep --plan <key>` + Key 会真实调用
一次对话接口验证套餐默认模型可用(Key 吊销/套餐过期/模型下线立刻暴露),
需联网、按量计费套餐消耗极少量 token。

### 架构收敛(对齐 thcli `core/http-agent.ts` 的教训)

全部 5 处出站 HTTP(目录刷新、目录哈希、模型发现、Key 验证、端到端
测试)收敛到唯一入口 `_http_request()`:统一的超时、User-Agent、认证头、
HTTPError/传输错误分级。thcli 曾因三处客户端各自拼装漏传配置踩过
`EPROTO`,这类收敛正是为杜绝同款事故。

### 测试

169 → 229 项(+60):深合并、codebuddy 用户模型保留、安装策略、远程
脚本 fail-closed、目录哈希三态、退出码契约、JSON 输出、环境变量 Key、
HTTP 入口、doctor --deep;`models.json.sha256` 一致性纳入 consistency 组
(改目录忘刷哈希会被 CI 拦下)。

[2.5.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v2.5.0

## [2.4.0] - 2026-09-03

### 新增:国际站后付费(选项 9)

官方国际站文档(product/1300/78934,按量计费)对应的后付费产品线:

- 端点 `https://tokenhub-intl.tencentcloudmaas.com/v1`(与中国站后付费
  结构一致,已探活:/models、/chat/completions、/responses、/messages、
  /embeddings 全部有鉴权层响应)
- Key 在国际站控制台创建:console.tencentcloud.com(两站 Key 不互通,
  已实测:中国站后付费 Key 打国际站 401002)
- 模型列表同样走 /v1/models 动态发现;原选项 8 更名"后付费 - 按量计费
  (中国站)",行为不变
- **模型层待验证**:国际站后付费的可用模型清单需要国际站后付费 Key
  才能拉取(README 验证矩阵已如实标注)

同时:`postpaid` 的全部特殊分支(模型发现、Key 验证、Claude 槽位
挑选、--models 选择、目录交叉检查豁免)统一扩展到 `postpaid-intl`,
两者共用同一套发现逻辑,仅 base_url 与 Key 控制台不同。

套餐选择 8 → 9 项;测试 167 → 169(国际后付费端点/控制台断言)。

[2.4.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v2.4.0

## [2.3.0] - 2026-09-02

### 修复:国际站端点域名错误 + 全部套餐模型目录按真 Key 实测重建

**① 国际站域名修正(严重)**

- 正确域名是 `tokenhub-intl.tencentcloudmaas.com`(tencent**cloud**maas),
  此前误用 `tokenhub-intl.tencentmaas.com` —— 该域名确实存在且有网关
  响应,但属于另一个系统,任何国际站 Key 打上去都报"Key 不存在"
- 来源:官方国际站文档 1300/81315、81489、78941;三把真 Key 在正确
  域名上全部验证通过

**② 模型目录全量重建(枚举实测,非文档镜像)**

用真实 Key 对全部套餐做了模型级枚举探测(每个候选模型发真实请求,
403002=不在套餐 / 200=支持),目录与实际可用模型逐一对齐:

| 套餐 | 旧目录 | 实测 |
|------|--------|------|
| 个人通用 | 10 | **13**(+hy3/hy4-preview/minimax-m2.5) |
| 企业专业 | 18 | **20**(+kimi-k2.5/minimax-m2.5) |
| 国际个人 | 8(镜像 CN,5 个不可用) | **6**(auto/deepseek×2/glm-5.2/kimi-k2.6/minimax-m3;默认模型从 tc-code-latest 改为 auto) |
| 国际企业专业 | 18(镜像 CN,5 个不可用) | **13**(glm-5.x 家族仅 5.2/5.3) |
| 企业轻享/国际轻享 | auto | auto(不变) |

**③ Codex 国际站默认模型修正**

国际站网关的 `auto` 路由不支持 Responses 协议(400005,真 Key 实测;
CN 域的 auto 支持),Codex 在国际站自动改用首个具体模型(专业版
glm-5.3、个人版 deepseek-v4-flash-202605)。

### 国际站端到端验证(全部真 Key)

国际企业专业版:codex / kimi / grok / pi / claude-code 五工具全部
真实对话通过;三协议(chat/responses/anthropic)端点全通。国际个人版
6 模型 × responses 逐一验证。

### 个人混元版:12 工具全量真 Key 端到端(2026-09-03)

混元版与通用版共用 API Key(用户确认),模型 hy3 / hy4-preview。
全部 12 个工具在隔离 HOME 下由安装器写入配置后逐个真实运行:

| 工具 | 结果 | 备注 |
|------|:---:|------|
| Hermes Agent | ✓ | `hermes chat -q -m hy3 -Q` |
| CodeBuddy Code | ✓ | `--model custom-local:hy3`(初测遇官方 key 校验服务 504,重试通过) |
| Claude Code | ✓ | hy3 / plan/anthropic 端点 |
| OpenCode | ✓ | `-m tokenplan/hy3` |
| OpenClaw | ✓ | `agent --local`,日志确认请求打 lkeap,status 200 |
| DeepSeek Harness | ✓ | `--profile headless`(profile 需用户侧已存在,settings.yaml 的 llm-pi-ai 命名空间生效) |
| Codex CLI | △ | 见下方说明 |
| WorkBuddy | ⚙️ | 配置层(models.json 写入 hy3/hy4-preview) |
| Kimi Code | ✓ | 默认 hy3 |
| Grok CLI | ✓ | hy4-preview |
| Pi | ✓ | `--model tokenplan/hy3` |
| ZCode | ⚙️ | 配置层(config.json) |

**Codex 专测结论**:实测 0.115–0.152 全部拒绝 `wire_api = "chat"`
(报"no longer supported"),比 #7782 讨论宣布的移除时间更早;而 lkeap
个人版无 /responses 端点。即**当前所有可安装的 Codex 版本都无法在
个人版上工作**——官方文档 1823/130071 的配置在现行 Codex 上同样
报错,属上游冲突;安装器按官方文档写入 chat 并在配置时警告。

至此 8 个产品线全部完成真 Key 实测(混元与通用共用 Key)。

[2.3.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v2.3.0

## [2.2.0] - 2026-09-02

### 修复:全产品线真 Key 实测发现的两处严重配置 bug

用全部 8 条产品线的真实 API Key 做了端到端验证(工具真实运行、
真实模型输出),发现并修复:

**① Kimi Code / Grok 的 TOML 点号 bug(企业版套餐完全不可用)**

- 模型 id 含点号(glm-5.3、minimax-m2.7、kimi-k2.7-code…)时,
  `[models.glm-5.3]` 会被 TOML 解析成嵌套表,且与平级
  `[models.glm-5]` 冲突 → **整个 config.toml 解析失败**
- 企业专业版(3/6)同时含 glm-5.x 家族 → kimi/grok 直接报
  "No model configured";个人版默认模型无点号所以侥幸可用
- 修复:表头引号包裹 `[models."glm-5.3"]`;kimi 升级路径自动
  清理 2.1.x 写入的无引号旧段
- 真 Key 端到端验证:kimi/grok/pi 在企业专业、个人通用、后付费
  三条产品线全部真实对话成功(Grok 用 glm-5.3 验证点号修复)

**② Codex 的 wire_api 按域分治(个人版 404 / 新版 Codex 不兼容 chat)**

- 官方文档(1823/130071、130666)写 `wire_api = "chat"`,但
  Codex 0.152+ 已**移除 chat 模式**(openai/codex#7782),配置
  直接报错;而 lkeap 个人版又没有 `/responses` 端点(真 Key 404)
- 修复:tokenhub 域(企业/国际/后付费)写 `responses`(真 Key
  实测 200 + Codex 0.152.1 端到端真实对话成功);lkeap 个人版按
  官方文档写 `chat` 并警告需降级 Codex 版本
- 这是新版 Codex 在个人版上的官方级无解困境(官方文档自身也
  已失效),已在配置时明确告知用户

### 真 Key 验证矩阵(2026-09-02)

| 产品线 | 协议验证 | 工具端到端 |
|--------|---------|-----------|
| 个人通用/混元(lkeap) | cc ✓ anthropic ✓(responses 404) | kimi ✓ |
| 企业专业/轻享(tokenhub) | cc ✓ responses ✓ anthropic ✓ | codex/kimi/grok/pi/claude-code ✓ |
| 后付费(tokenhub /v1) | cc ✓ responses ✓ anthropic ✓ | kimi ✓(130 模型发现) |
| 国际版(tokenhub-intl) | 域名路由正常 | **提供的 3 个 Key 均无效(401002)**,待有效 Key 复验 |

注:无 Key 探测的 401 只能证明鉴权层拦截,**不能证明路由存在**
(lkeap /responses 即反例:无 Key 401、有 Key 404)——此前 2.1.x
的"端点已验证"说法据此修正。

[2.2.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v2.2.0

## [2.1.1] - 2026-09-02

### 修复:后付费套餐的 Claude Code 配置不可用

- **bug**:后付费(选项 8)写入的 `ANTHROPIC_BASE_URL` 以 `/v1` 结尾,
  而 Anthropic SDK 固定在 base 后拼接 `/v1/messages`,导致实际请求
  `…/v1/v1/messages` → 404。此前注释"客户端自动拼 /messages"判断错误
  (已读 SDK 源码确认:`this._client.post('/v1/messages', …)`)
- **修复**:base 写到域名根(不带 `/v1`),SDK 拼出正确的
  `https://tokenhub.tencentmaas.com/v1/messages`(已探活:401 鉴权层
  响应,路径正确)
- 附带:套餐版(3-7,tokenhub 域)不提供 `/models` 列表端点(探活
  404),`fetch_remote_models` 对这些域直接跳过目录交叉校验提示
  (该提示本来就只是锦上添花,lkeap 个人版与后付费不受影响)

### 全产品线端点矩阵验证(本次审计结果)

4 个域 × 3 协议路径全部探活通过(无 Key 请求均得到鉴权层 401,
证明路由正确):

| 域 | chat/completions | /responses | anthropic |
|----|-----------------|-----------|-----------|
| lkeap(个人版) | ✓ | ✓ | /plan/anthropic/v1/messages ✓ |
| tokenhub(企业版) | ✓ | ✓ | /plan/anthropic/v1/messages ✓ |
| tokenhub-intl(国际版) | ✓ | ✓ | /plan/anthropic/v1/messages ✓ |
| tokenhub /v1(后付费) | ✓ | ✓ | /v1/messages ✓ |

`/plan/anthropic` 路径已对照官方文档(cloud.tencent.com 130665/
130070)确认。

[2.1.1]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v2.1.1

## [2.1.0] - 2026-09-02

### 新增:四个 AI 编程工具(对标火山方舟 arkcli 的支持面)

- **Kimi Code CLI**(Moonshot):写入 `~/.kimi-code/config.toml`,
  openai provider + 套餐模型 + 默认模型;npm 自动安装
- **Grok CLI**(xAI 官方):写入 `~/.grok/config.toml` 的
  `[model.*]` 段,chat completions 协议;npm 自动安装
- **Pi**(badlogic/pi-mono coding-agent):写入
  `~/.pi/agent/models.json`,openai-completions provider;npm 自动安装
- **ZCode**(智谱):写入 `~/.zcode/v2/config.json` 自定义 provider
  (kind=openai-compatible);应用手动下载

验证口径:Kimi Code / Grok CLI / Pi 均已**端到端实测**——安装器写入
配置后,三个工具对 Token Plan 端点发起真实请求(假 key 得到网关
401,证明链路通);ZCode 为闭源 Electron 客户端,配置格式经
zcode-account-switcher 与 dsh-zcode-sync 两个第三方实现交叉确认,
标注为配置层验证。工具列表 8 → 12。

选型依据:火山方舟 arkcli `helper list` 认识 13 个 Agent,其中模型
可配置的 11 个里我们已覆盖 10 个(独有 CodeBuddy;arkcli 独有
ZCode 现已补齐);TRAE 与 Cursor 按 arkcli 官方结论(模型配置
不支持)与既定决策排除。

### 技术细节

- `_toml_upsert_section` 支持数值/布尔字段(kimi 的
  max_context_size 必须是裸数字,字符串会被 schema 拒绝)
- TOML 顶层键(default_provider/default_model)必须位于首个表头
  之前,`_toml_upsert_root_key` 已保证
- ZCode provider id 使用 uuid5("tokenplan") 确定性生成,重跑幂等

[2.1.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v2.1.0

## [2.0.0] - 2026-09-02

### 破坏性变更:工具列表 14 → 8

只保留安装器**真正自动写入配置**的工具,移除全部纯引导型条目:

- 移除 Kilo CLI、Kilo Code、Cline(此前仅自动安装本体,配置靠
  用户在向导/界面手动填写)
- 移除 AutoClaw、QClaw、CoPaw(下载与配置均为手动)
- 保留:7 个自动安装+自动配置的 CLI(Hermes/CodeBuddy/Claude
  Code/OpenCode/OpenClaw/DSH/Codex)+ WorkBuddy(模型清单自动落盘)

背景:支持声明与实际能力对齐。此前"17/14 个工具"的口径中,多数
条目只是打印填写指引,README 却一并写作"支持"。火山方舟 arkcli
的口径同样是只把 `helper configure` 能写入的目标算作支持;对无法
写入模型配置的工具(如 TRAE/Cursor)其明确标注"不支持模型配置"。

### 清理

- 删除 plugin/deploy 后端及其全部死代码路径(插件检测、扩展 ID
  表、VS Code 依赖检查、菜单标签)
- `--tools` 不再接受已移除工具的编号/键名

[2.0.0]: https://github.com/zmq1121/tokenplan-quick-setup/releases/tag/v2.0.0

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
