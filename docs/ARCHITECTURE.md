# 架构与实现说明

本文面向维护者,讲清楚 tokenplan-quick-setup 的整体实现:入口链路、核心数据结构、两条流水线(安装/配置)、安全机制、测试与发布体系。面向使用者的操作指引见 [USER-GUIDE.md](USER-GUIDE.md)。

- 维护源码:`tokenplan_setup/`(按基础设施、领域、适配器、流程、CLI 分层)
- 发布产物:`setup.command`(由 `scripts/build_dist.py` 确定性生成的 bash/Python 多态单文件,零第三方运行时依赖)
- 当前版本:2.7.6(npm `tokenplan-setup@2.7.6`)

---

## 1. 定位与设计哲学

一句话定位:**装机配置器**——把"腾讯云大模型 API 的接入配置(端点、Key、模型表)"自动写进 12 个 AI 编程工具,运行一次完成安装与配置。

核心设计原则(2.5.0 起明确化,部分借鉴官方 tokenhub-cli 的工程标准):

1. **表驱动**:工具、套餐、后端类型、配置器全部是注册表数据,核心流程不为任何具体工具写分支。新增第 13 个工具 = 1 条 ToolSpec + 1 个配置器 + 1 个签名,流水线零改动
2. **单源目录**:模型列表只有一个出口 `get_model_ids()`,所有配置器从这里取数,不各自维护
3. **fail-closed**:不确定就拒绝——远程脚本非交互不执行、目录哈希对不上就回退内置、doctor --deep 缺参就报错
4. **副作用全部可逆**:写前备份、写入台账、卸载精确还原
5. **连接收敛**:全部出站 HTTP 走唯一入口 `_http_request()`,杜绝各调用点自行拼装导致行为漂移

---

## 2. 三条入口链路

### 2.1 `bash setup.command`(macOS/Linux)

多态脚本技巧:第 2 行 `"exec" "$(command -v python3 || command -v python)" "$0" "$@"` 让 bash 把自己重新交给 Python 执行,之后就是纯 Python;`python3` 缺失时回退到 `python`。

### 2.2 `npx tokenplan-setup`(跨平台)

```
npx → npm/bin/tokenplan-setup.js(零依赖 Node 包装器)
        1. 找 Python 3(Windows: py -3 → python → python3;其它: python3 → python)
        2. spawn 它执行 npm/lib/setup.command(与主脚本字节一致,由 sync 脚本保证)
        3. 透传全部 CLI 参数,传播退出码
```

### 2.3 `setup.bat`(Windows 免 Node 下载器)

```
检测 Python(py -3 / python)
  → 从三镜像下载固定版本主脚本(GitHub Release → cdn.jsdelivr → fastly.jsdelivr)
  → certutil 计算 SHA256,与内嵌的 SETUP_SHA256 比对(防镜像篡改/损坏)
  → 校验通过才执行,透传参数,退出码回显
```

`SETUP_VERSION` / `SETUP_SHA256` 由 `scripts/build_dist.py` 自动注入,手改无效——发布流程保证"批处理文件、npm 包、GitHub Release 三处的 setup.command 是同一份字节"。

因此 `setup.command` 一旦变更就必须同步升版本:`setup.bat` 内嵌的是新字节的
SHA256,而下载地址指向 `v{SETUP_VERSION}` 的 Release。若沿用旧版本号,Windows
用户会下到旧产物并在完整性校验处直接中止。

### 2.4 Python 模块入口

`python -m tokenplan_setup` 经 `__main__.py → entrypoint.py → cli.main`,
直接运行导入的包模块。`_runtime.py` **不参与生产执行**,只为构建脚本和旧回归
套件提供源码拼装能力——否则包会被执行两遍,产生两套互不相通的模块级状态,
让测试断言的对象和实际运行的对象分离。`test_entrypoints.py` 有一条守卫用例
断言普通 `import tokenplan_setup` 不会加载 `_runtime`,防止这种结构被重新引入。

静态依赖方向为 `infrastructure → domain → adapters → flows → cli`(箭头表示
构建/依赖顺序,后层只能依赖前层);import-linter 同时禁止 `_runtime` 静态反向
导入业务层,避免拼装层形成循环。跨模块可变状态一律通过 `adapters` 的访问函数
(如 `remote_catalog_size()`、`postpaid_discovered_count()`)读取,而不是导入
全局变量本身——后者在包语义下只会绑定导入时的快照。

---

## 3. 核心数据结构(全部注册表)

| 注册表 | 形态 | 作用 |
|---|---|---|
| `PLAN_CATALOG` | 编号(1-9) → `PlanSpec` | 9 个套餐:base_url、Key 控制台地址、限制提示 |
| `TOOLS` / `TOOL_BY_INDEX` / `TOOL_BY_KEY` | `ToolSpec` 元组 | 12 个工具:检测命令、安装方式、配置路径、使用提示 |
| `BACKEND_REGISTRY` | backend → 适配器 | 两类:`cli`(可自动安装)/ `desktop`(手动下载) |
| `MODEL_CATALOG` | 套餐 key → {default, display} | 内置模型目录(远程目录的离线兜底) |
| `CLAUDE_MODEL_SLOTS` | 套餐 key → opus/sonnet/haiku | Claude Code 固定槽位映射(与 OpenAI 兼容目录分离) |
| `CONFIGURATOR_REGISTRY` | 工具 key → 配置函数 | 12 个自动配置器(含 WorkBuddy/ZCode 桌面类) |
| `CONFIG_SIGNATURES` | 工具 key → (文件, 当前特征, 旧版特征) | doctor 反向探测"我们的配置块还在不在";旧版特征兼容 2.5.x 品牌配置不误报 |
| `TOOL_DEPENDENCY_REGISTRY` | 工具 key → 额外运行依赖 | 目前仅 dsh 额外需要 npx |
| `SYSTEM_DEPENDENCY_REGISTRY` | 系统命令 → 平台/用途/可选性 | Python、Node/npm/npx、bash、curl、certutil、pgrep、setx、reg 的统一口径,供 doctor/文档/测试使用 |

### 套餐与端点矩阵(9 个)

| # | 套餐 | Base URL |
|---|---|---|
| 1 | 个人版-通用 | `api.lkeap.cloud.tencent.com/plan/v3` |
| 2 | 个人版-Hy(混元) | 同 1 |
| 3 | 企业版-专业 | `tokenhub.tencentmaas.com/plan/v3` |
| 4 | 企业版-轻享 | 同 3 |
| 5-7 | 国际站(新加坡)个人/专业/轻享 | `tokenhub-intl.tencentcloudmaas.com/plan/v3` |
| 8 | 后付费-中国站 | `tokenhub.tencentmaas.com/v1` |
| 9 | 后付费-国际站 | `tokenhub-intl.tencentcloudmaas.com/v1` |

---

## 4. 安装流水线

```
is_tool_installed()          shutil.which(check_exe) —— 在 PATH 上即跳过(幂等)
        ↓
should_manual_download()     查后端注册表(desktop 类 → 只写配置不安装)
        ↓
install_tool() 三条分发路径:
  ① npm 命令     → 追加私有缓存 ~/.tokenplan-npm-cache + --ignore-scripts
  ② 远程脚本     → run_remote_script()(仅 macOS/Linux,见 §7)
  ③ 无命令       → 提示手动下载(download_url)
        ↓
run_command()     流式输出 + 600s 看门狗强杀;Windows 上 .cmd shim 先
                  which 解析再改走 shell 分支(CreateProcess 拉不起 .cmd)
```

### 12 个工具的安装方式

| 工具 | 方式 | 说明 |
|---|---|---|
| Hermes Agent | 远程脚本 | `hermes-agent.nousresearch.com/install.sh` + 三个 skip 参数;Windows 手动 |
| CodeBuddy / Claude Code / OpenCode / DSH / Codex / Kimi / Grok / Pi | npm `-g --ignore-scripts` | 统一拦截安装期 lifecycle 脚本 |
| OpenClaw | 远程脚本(macOS/Linux)+ npm(Windows) | |
| WorkBuddy / ZCode | 手动下载 | 桌面应用,但配置照写,装好即用 |

`--ignore-scripts` 与"先下载后确认"是 2.5.0 的供应链加固:lifecycle 脚本是 npm 生态供应链攻击的重点面,而这些 CLI 均通过平台包分发二进制、不需要安装期脚本。2.6.1 起 npm 包名与精确版本只由 `VERIFIED_TOOL_VERSIONS` 提供,安装命令不再跟随裸包或 `@latest`;清单同时记录查询所用 dist-tag、稳定性状态与 registry integrity。

需要明确边界:精确版本 pin 能防住"跟随 `@latest` 漂移",但防不住同一版本号下
tarball 被重新发布。`scripts/check_tool_versions.py` 就是为这个缺口设的门禁——它
直接查 npm registry 的精简 packument,逐包比对 `dist.integrity`,不一致即退出码 1;
每周由 `supply-chain-pins` job 执行,且**故意不设 `continue-on-error`**:偶发的网络
误报可以接受,静默的供应链漂移不行。脚本区分三种结果(0 一致 / 1 确定不一致 /
2 网络异常导致无法证明),避免把"不可用"误报成"不一致"。

仍未实现的是**安装期**强制校验:`npm install` 路径不比对 integrity,真要 enforce
需要引入 lockfile 或安装前查询。也就是说当前防护是"周期性检测",不是"实时阻断"。

DeepSeek Harness 是唯一例外:截至 2026-09-03 registry 中全部 15 个版本均为 alpha/RC,不存在可选的稳定版本。安装器固定查询时的 `latest` (`0.1.1-rc.2`)并标为 `prerelease-only`,不将其误称为稳定版。

---

## 5. 配置流水线

### 5.1 模型目录:单一来源 + 三级回退

```
get_model_ids(plan)
  ├─ 后付费套餐 → discover_postpaid_models():GET /v1/models 实时发现
  │                + _POSTPAID_EXCLUDE 正则过滤非聊天模型(视频/图像/embedding/…)
  │                + 用户交互选择子集(--models 或编号选择)
  └─ 套餐类 → refresh_remote_catalog():
        jsDelivr 从 @v{VERSION} 拉 models.json + models.json.sha256
        哈希一致 → 采用远程目录
        拿不到哈希 / 哈希不匹配 → 回退内置 MODEL_CATALOG(fail-closed)
```

- 远程目录与安装器版本绑定,同一发布版本始终读取同一份 JSON;模型增减随新版本标签发布
- `latest_version` 字段用于向旧版本安装文件提示升级
- `scripts/check_models.py` 可将目录与官方文档对照(维护者工具)
- `models.json` 与 `.sha256` 在 `.gitattributes` 中锁定 `eol=lf`(字节级完整性契约,详见 §11)

### 5.2 十二个配置器(每个工具一个,格式各异;desktop 类也写配置,装好即用)

| 工具 | 写入目标 | 手段 |
|---|---|---|
| Hermes | `~/.hermes/.env` + `config.yaml` | env 写入 + **monkey-patch** 上游 `model_switch.py` 修自定义 provider 的 slug 解析 |
| CodeBuddy | `~/.codebuddy/models.json` | 深合并 `merge_key="id"`(保留用户自建模型)+ shell env |
| Claude Code | `~/.claude/settings.json` + `tokenhub-models.json` + 启动器 | env 块(ANTHROPIC_* 三槽位)+ `claude-tokenhub` 模型选择器(`~/.local/bin`,Windows 写 .cmd 进 npm 目录) |
| OpenCode | `~/.config/opencode/opencode.json` | `provider.tokenhub` 深合并 |
| OpenClaw | `~/.openclaw/openclaw.json` + `.env` | `providers.tokenhub` + models allowlist(防内置列表遮挡)+ Key 走 env |
| DSH | `~/.dsh/settings.yaml` + `.credentials.yaml` | pi-ai provider,`apiKeyEnv: TOKENPLAN_API_KEY` 间接引用;credentials 0600;`cordis.patch.yml` 重置为 `[]` |
| Codex | `~/.codex/config.toml` | **TOML 手术**:`wire_api` 按域名分发(lkeap→chat,tokenhub→responses),`env_key` 间接引用 + `tokenplan.env`/setx |
| WorkBuddy | `~/.workbuddy/models.json` | 深合并 `merge_key="id"`;pgrep 检测进程,运行中要求先退出(否则其退出时会用内存旧列表覆盖) |
| Kimi Code | `~/.kimi-code/config.toml` | default_provider/default_model + 管理的 model 段先删后插(幂等) |
| Grok | `~/.grok/config.toml` | `[model.*]` 段 + `# TokenHub models begin/end` 托管块标记 |
| Pi | `~/.pi/agent/models.json` | `providers.tokenhub`,`api: openai-completions` |
| ZCode | `~/.zcode/v2/config.json` | `provider.<id>` 自定义 provider(闭源客户端,配置层验证) |

### 5.3 品牌口径与旧键清理(2.6.0)

所有工具配置里用户可见的名称集中由四个常量派生(`setup.command` 顶部):

| 常量 | 值 | 用途 |
|---|---|---|
| `BRAND_NAME` | TokenHub | 展示名(Hermes name、DSH displayName、横幅) |
| `BRAND_SLUG` | tokenhub | 配置内 provider 键与模型前缀(`tokenhub/<model>`) |
| `BRAND_VENDOR` | Tencent Cloud TokenHub | vendor/name 全称(WorkBuddy/ZCode/Codex/OpenCode) |
| `BRAND_LEGACY_KEYS` | tokenplan / token-plan / tencent-tokenplan | 2.5.x 旧键,重写配置时自动摘除 |

- 设计动机:接入平台是 TokenHub(端点域名/控制台口径),旧版以安装器内部名"Token Plan"作展示名造成品牌错位
- 升级路径:各 configurator 重写时摘除 `BRAND_LEGACY_KEYS` 旧键(JSON 逐键 pop,TOML 按段删除,Grok 按托管块剥离);`probe_config` 对旧品牌特征返回 True(配置仍有效,doctor 不误报),重跑 repair 即完成品牌升级
- 刻意保留的旧标识:rc 文件 marker(`# Token Plan Claude model selector` 等,换词会让升级用户得到重复的 PATH/source 块)、`TOKENPLAN_API_KEY` 环境变量名(已发布文档依赖)、`tokenplan.env` 文件名、npm 包名 `tokenplan-setup`

### 5.4 配置写入的安全网(每次写入都过这三层)

1. **`backup_file()`**:时间戳备份到 `~/.tokenplan-backups/<name>.<ts>.bak` + 追加 `manifest.jsonl` 台账;备份本身也收紧 0600(备份里含 API Key)
2. **写入**:`write_json`(递归深合并)/ `write_env` / TOML 手术
3. **`_harden()`**:chmod 0600

### 5.5 深合并语义(2.5.0 修复)

`write_json(merge=True)`:

- dict 对 dict → `_deep_merge_dicts` 递归逐键下钻
- 双方均为 list 且给了 `merge_key` → `_merge_model_lists`:保留用户条目,仅替换/追加我方同标识条目
- 其余 → 新值覆盖

修复背景:此前是顶层 `update()` 浅合并,用户 opencode/openclaw/claude 配置里**同级的其它 provider 会被整块顶掉**。

### 5.6 Key 的间接引用策略

能不落明文就不落:Codex/OpenClaw/DSH 走 `TOKENPLAN_API_KEY` 环境变量间接引用;必须内联的(CodeBuddy/WorkBuddy 条目、Grok/Kimi 段)靠 0600 文件权限保护。Windows 上 Codex 的环境变量用 `setx` 写用户级注册表,旧值记录进台账供卸载还原。

---

## 6. 主流程(`main` → `_run_setup_flow`)

```
解析参数(setup/repair/doctor/uninstall + --plan/--api-key/--tools/--models/
          --yes/--verify-models/--json/--deep)
  ↓ Key 解析优先级
--api-key 参数 > 环境变量 TOKENPLAN_API_KEY > 交互输入
(命令行参数会留在 shell 历史里,自动化场景推荐环境变量;过短的 Key 警告/拒收)
  ↓ verify_api_key()
套餐类:发一次 max_tokens=1 的 chat completion
后付费:GET /models 即验证(200+列表 = Key 有效),同时完成模型发现
(验证失败可选继续)
  ↓ refresh_remote_catalog()(§5.1)
  ↓ 交互:运行模式(标准/仅修复) → 工具选择(编号/all/none,EOF 默认全部)
  ↓ check_prerequisites():OS/Node/npm/npx/code(按所选工具的实际依赖)
  ↓ 逐工具循环:检测 → 安装(如需)→ 配置(进度条 + 三态 installed/failed/skipped)
  ↓ 汇总输出(usage 提示按模板渲染,Key 一律 mask_secret 打码)
  ↓ verify_models():真实调用端到端验证
(default=只验默认模型;all=全目录;5xx 自动重试一次防误报)
```

### 退出码契约(2.5.0)

| 码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 用户取消(未选工具/未输 Key/验证失败后选否) |
| 2 | 环境不满足(缺 Node、后付费无法联网发现模型、doctor --deep 缺参) |
| 3 | 部分工具配置失败 / doctor 检出配置缺失 / --deep 验证失败 |

### `--json` 模式

`_JSON_MODE` 全局开关:过程日志经 `redirect_stdout(sys.stderr)` 全部转 stderr,stdout 只输出最终 JSON。字段:`version / command / plan / base_url / api_key(打码) / models / tools[](configured|failed|skipped+error) / verified{} / exit_code`。**密钥在 JSON 里一律打码**——JSON 会被转发、落盘、进对话历史,暴露面远大于终端看一眼。

---

## 7. 安全机制总览

| 机制 | 实现 |
|---|---|
| 远程脚本执行 | Hermes/OpenClaw 上游没有发布可预先固定的官方摘要,不能进行下载前摘要验证。`run_remote_script()`:完整下载到临时文件 → 展示本次内容的来源 URL + SHA256 + 大小 → 交互确认 → `bash <tmpfile>` 执行;非交互环境一律拒绝;`--yes` 跳过确认但指纹仍打印。取代 `curl \| bash` 盲管道 |
| 目录完整性 | `models.json.sha256` 哈希校验,不匹配/拿不到 → 回退内置(fail-closed) |
| 供应链 | npm 使用已验证清单的精确版本并统一 `--ignore-scripts`;setup.bat 下载固定版本 + certutil SHA256 |
| 密钥卫生 | 终端与 JSON 输出全部 `mask_secret()`(前 4 位 + …);配置文件 0600;env 间接引用优先 |
| 可逆性 | 备份 + manifest.jsonl + state.json 台账(见 §8) |
| HTTP 收敛 | `_http_request()`:统一超时/User-Agent/认证头;HTTPError → `(code, body)`,传输错误 → RuntimeError(调用方决定提示口径) |

---

## 8. 卸载与还原(`uninstall`)

台账 `~/.tokenplan-backups/state.json` 记录副作用:

| 类别 | 还原动作 |
|---|---|
| `rc_blocks` | `strip_rc_block()` 删除标记行及其后一行 |
| `files_written` / `env_files` | 删除生成的文件(启动器/env 文件等) |
| `setx_keys` | `setx` 还原旧值,无旧值则 `reg delete` |
| manifest.jsonl | `collect_latest_backups()` 按原路径取最新备份,`copy2` 还原 |
| `remote_scripts` | **不可回滚**,仅登记并披露(见下) |

不卸载工具本体(npm 包、CLI 程序保留),只还原配置与安装器写入的修改。备份目录保留供人工确认后删除。

`remote_scripts` 是审计条目而非还原条目:第三方安装脚本以当前用户身份执行,
其副作用(装了什么、写到哪)不在本工具掌握范围内,声称能回滚就是不诚实。因此
`run_remote_script()` 在执行前登记 `{tool, url, sha256, bytes}`,`uninstall` 在
两条返回路径上都会列出这些记录并明确说明无法自动清理,`--json` 输出同样带
`remote_scripts` 字段,保证契约形状稳定。

---

## 9. doctor(只读诊断)

- 前置检查 + 逐工具三态:未安装 / 已安装+配置有效 / 已安装+配置缺失(建议 repair)
- 配置探测:`probe_config()` 按签名特征串判断配置块是否还在(能发现"被外部工具覆盖")
- `--deep --plan <key> --api-key <KEY>`:真实调用一次 chat completion 验证默认模型端到端可用——Key 吊销、套餐过期、模型下线一次暴露
- 退出码按健康度返回(见 §6),可被脚本消费;`--json` 输出结构化 rows

---

## 10. 测试体系

`tests/run_tests.py`:**293 项断言,零依赖,单命令运行**。该计数是旧回归
套件的断言数,不是对真实云端端到端调用的承诺。

- 加载方式:`tokenplan_setup._runtime.execute_sources()` 按构建顺序把分层源码
  执行进一个独立命名空间,复现单文件产物的扁平语义;剥离内部 import 的转换函数
  与 `scripts/build_dist.py` 共用同一份实现,产物与测试无法各自漂移。每层仍以真实
  `tokenplan_setup/*.py` 文件名编译,覆盖率与异常定位都指向源码;Windows 行为通过
  替换 `IS_WINDOWS = True` 模拟
- 沙箱:`sandbox()` 把模块 HOME 重定向到临时目录,测试不碰真实用户目录
- 覆盖:注册表完整性、TOML 手术、各配置器端到端、卸载生命周期、权限、交互流 EOF 安全、远程目录回退与哈希三态、远程脚本 fail-closed、退出码契约、JSON 输出、环境变量 Key、HTTP 入口、doctor --deep、**一致性组**(npm/lib 字节一致、setup.bat 版本+SHA256 一致、models.json.sha256 一致、无死代码、无硬编码路径)
- 交互测试不触网:`run_remote_script` 打桩、`TOKENPLAN_API_KEY` 显式清理(防宿主机环境污染)

```bash
python3 tests/run_tests.py            # 全部
python3 tests/run_tests.py codex      # 单组
python3 -m pytest                     # 模块化分层测试
python3 -m pytest --cov=tokenplan_setup
python3 -m ruff check .
python3 -m mypy
lint-imports
python3 scripts/check_tool_versions.py   # npm 版本与 integrity 实时核对(需联网)
```

pytest 套件按职责拆分为 domain/registry、12 配置器参数化契约、build
artifact、entrypoint 四层。配置器测试使用临时 HOME、mock 外部命令与网络,
fixtures 覆盖旧品牌和损坏配置,不会读取或改写真实用户配置。

覆盖率的真实构成需要说清楚:`fail_under = 75` 是防回退下限,当前总覆盖约
80.5%,其中相当一部分来自参数化执行的 293 项旧回归;若只跑分层 pytest,
覆盖率约 40.7%(65 项)。也就是说**行为保障的主体仍是旧回归套件**,但分层
测试已从"只守注册表和文件契约"扩展到覆盖高风险失败路径。覆盖率只证明代码
被执行过,不证明行为被断言正确。

`tests/test_failure_paths.py` 专门覆盖那些会触网、动用户 shell 或写注册表的
分支,均以显式桩断言可观测行为:远程目录的完整性三态(哈希匹配 / 不匹配 /
`.sha256` 拿不到)与哈希通过但内容不可解析、后付费发现的 HTTP 错误与连接失败、
远程脚本 fail-closed 与执行留痕、安装命令失败与可执行文件缺失、npm 命令的精确
pin 与私有 cache、Windows `setx`/`reg` 台账(含"原值不存在应记为 None")。

`tests/test_isolation.py` 守的是测试本身的安全性。`HOME`/`BACKUP_DIR`/
`STATE_PATH` 在各层是 `from ... import` 的导入期快照,只 patch `infrastructure`
并不够——`flows` 持有自己的 `BACKUP_DIR`,曾因此在测试中读取真实的
`~/.tokenplan-backups` 并尝试覆盖真实用户配置。该文件用 `pkgutil` 遍历包内所有
模块,断言没有任何路径常量逃出临时目录,新增模块忘记纳入沙箱会被直接点名。

剩余未覆盖部分集中在交互式主流程分支与部分平台专属路径,应继续补测,不应通过
排除源码或下调阈值来改善数字。

开发依赖只存在于 `project.optional-dependencies.dev`:pytest、pytest-cov/
coverage、Ruff、mypy、import-linter;`project.dependencies` 保持为空。
mypy 对显式模块边界、源码拼装层和构建脚本执行严格检查,层级完整性另由
import-linter 对全部业务模块守卫。

---

## 11. 发布链路

```
改 tokenplan_setup/ 或 models.json
  → python3 scripts/build_dist.py      # 重建五项确定性产物
  → 旧回归 + pytest + ruff + mypy + lint-imports + build --check
  → 同步 pyproject/npm/models 的精确 SemVer
  → git commit + tag vX.Y.Z + push
  → 标签工作流重跑三平台矩阵并执行 git diff 门禁
  → 创建 GitHub Release 并上传 setup.command/setup.bat/models*
  → Release 资产可用后 npm publish
```

### 一致性保障

- **CI**(`.github/workflows/tests.yml`):Ubuntu/macOS/Windows × Python
  3.9/3.12/3.13,运行旧回归、pytest、Ruff、mypy、import-linter、
  `build_dist.py --check`、Python module 与 npm wrapper 冒烟
- weekly schedule 另有 `supply-chain-pins` job 实时核对 npm 版本与 integrity,
  该 job 不允许失败(见 §6 的供应链边界说明)
- PR 路径不访问模型官方文档;`check_models.py` 只在 weekly schedule 的
  allow-failure job 运行,外部网络波动不会阻塞合并
- **标签发布**(`release.yml`):最小权限、environment 与按标签 concurrency;
  先上传不可变 GitHub Release 资产,再发布 npm,避免 `setup.bat` 已经分发
  但其固定版本下载目标尚不存在
- **`.gitattributes`**:`setup.command` / `npm/lib/setup.command` / `models.json` / `models.json.sha256` 锁 `eol=lf`(字节级完整性契约——哈希校验要求所有平台检出为相同字节);`setup.bat` 锁 `eol=crlf`;规则必须在 `*.json text=auto` 之后(gitattributes 后行覆盖前行)
- **真实事故记录**(v2.5.0 发布过程):`models.json` 起初只有 `*.json text=auto` 规则,Windows runner 检出时 LF→CRLF,字节变化导致 SHA256 一致性测试失败;macOS 本地永远测不出来。修复 = 补 `eol=lf` 规则。这是"哈希契约必须锁行尾"的直接教训

---

## 12. 平台差异处理(Windows 清单)

| 差异点 | 处理 |
|---|---|
| ANSI 转义 | `enable_windows_ansi()` 经 kernel32 SetConsoleMode 开 VT100 |
| 代码页 | setup.bat `chcp 65001`;测试套件统一强制 UTF-8 |
| Python 启动 | `py -3` 优先,回退 `python` |
| 行尾 | setup.bat 必须 CRLF(gitattributes 锁定) |
| `.cmd` shim | CreateProcess 拉不起,先 `shutil.which` 解析再走 shell |
| 环境变量 | `setx` 写用户级(需重开终端生效);旧值经 `reg query` 读出进台账 |
| Claude 启动器 | `claude-tokenhub.cmd` 写入 npm 全局目录而非 `~/.local/bin` |
| 工具缺口 | Hermes 无官方 Windows 安装器 → `win_manual=True`,提示手动安装后重跑 repair |

---

## 13. 环境敏感性与边界

与官方 tokenhub-cli 的本质差异(决定了各自要驯服的方差方向):

> **thcli = 1 个集成面(云 API)× N 个命令;本工具 = N 个集成面(每个工具一种格式、一条安装通道)× 1 个命令。**

- thcli 的敏感轴是**网络与运行时**(代理、TLS、Node 版本、浏览器 OAuth),所以它把连接配置收敛到 `core/http-agent.ts`
- 本工具的敏感轴是 **OS × shell × 目标工具自身版本**:Codex 0.152+ 删了 chat 模式(按域名分发 wire_api 规避)、WorkBuddy 运行中会覆盖写入(pgrep 检测)、Claude `/model` 只有固定槽位(独立槽位映射)、检出行尾破坏哈希契约(gitattributes 锁定)
- 兜底组合相同:CI 矩阵 + doctor 探测 + 对不确定场景 fail-closed

---

## 14. 关键文件索引

| 文件 | 职责 |
|---|---|
| `tokenplan_setup/` | 模块化维护源码与 Python 模块入口 |
| `setup.command` | 从模块化源码确定性生成的单文件发布产物 |
| `models.json` / `models.json.sha256` | 远程模型目录 + 完整性哈希 |
| `setup.bat` | Windows 免 Node 下载器 |
| `npm/bin/tokenplan-setup.js` | npx 入口(Python 探测 + 透传) |
| `npm/package.json` / `npm/lib/` | npm 包定义与载荷 |
| `scripts/build_dist.py` | 生成单文件、npm 载荷、模型目录代码、摘要与 bat 元数据 |
| `scripts/sync_npm_lib.py` | 旧同步命令兼容层 |
| `scripts/check_models.py` | 目录与官方文档对照 |
| `scripts/check_tool_versions.py` | npm 版本/integrity 实时核对门禁 |
| `tests/run_tests.py` / `tests/test_*.py` | 293 项旧回归 + 分层 pytest |
| `.github/workflows/tests.yml` | CI 矩阵 |
| `.gitattributes` | 行尾策略(完整性契约的组成部分) |
