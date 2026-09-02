# 发布与运维存档（2026-09-02）

> 本文件记录 tokenplan-quick-setup 的发布状态、渠道、账号信息和运维要点。
> 敏感信息（token 等）不落库，只写处理状态。

## 一、当前发布状态

| 项 | 状态 |
|----|------|
| 版本 | **1.1.0** |
| GitHub 仓库 | https://github.com/zmq1121/tokenplan-quick-setup（公开） |
| npm 包 | **tokenplan-setup@1.1.0** 已发布，维护者账号 `mingqizou77` |
| npx 验证 | `npx tokenplan-setup@latest --version` → `tokenplan-setup 1.1.0` ✅ |
| 国内镜像 | npmmirror 已同步 1.1.0 ✅（国内用户可直接装） |
| CI | GitHub Actions 四矩阵全绿（ubuntu/windows × Python 3.9/3.12，92 项测试） |
| 主分支 | `main` = `feat/windows-support` = `098bf16` |

## 二、用户接入渠道（全部已激活）

```bash
# 方式 1：npx（全球）
npx tokenplan-setup

# 方式 2：npx（国内加速）
npx --registry=https://registry.npmmirror.com tokenplan-setup

# 方式 3：单文件（微信/QQ 分发）
#   Mac:     setup.command（bash setup.command 或双击）
#   Windows: setup.bat（双击，自动从 CDN 下载主脚本）
```

## 三、v1.1.0 功能清单

- 17 个工具接入（编号 1-6 为已验证工具，顺序不可变）
- 7 个套餐：中国站 4 个（选项 1-4）+ **国际站 3 个（选项 5-7，新加坡）**
  - 国际站端点：`https://tokenhub-intl.tencentmaas.com/plan/v3`
  - 国际站模型表经官方文档"新加坡"章节逐行核实，与中国站一致
  - 国际站个人版模型参照中国站通用套餐（官方国际站文档 WAF 挡脚本，无法程序化抓取）
- `doctor` 配置三态诊断：已安装+配置有效 / 配置缺失（提示 repair）/ 未安装
- 安装命令 10 分钟超时保护（看门狗线程）
- 版本感知：models.json 带 `latest_version`，旧文件运行时提示升级
  - 注意：v1.0.0 文件无此代码，只对 v1.1.0+ 生效；v1.0.0 仍能拿到模型目录更新
- 远程模型目录：`https://cdn.jsdelivr.net/gh/zmq1121/tokenplan-quick-setup@main/models.json`
  - 更新模型 = 改 models.json + setup.command 内置 MODEL_CATALOG（双源同步）→ 提交
  - jsDelivr `@main` 引用缓存最长 12 小时；可用 `https://purge.jsdelivr.net/v1/purge/jsdelivr/gh/zmq1121/tokenplan-quick-setup@main/models.json` 主动刷新；fastly 镜像收敛更快
  - 核查脚本：`python3 scripts/check_models.py`（对照官方文档 diff，退出码 0/1）

## 四、npm 账号信息（重要）

| 项 | 值 |
|----|-----|
| 包维护者账号 | **mingqizou77**（包发布在这个号下） |
| 另一账号 | mingqizou（曾尝试发布，被 2FA 挡下） |
| 2FA 模式 | auth-and-writes（登录+发布都要动态码） |

### 发布流程（下次发版照此操作）

```bash
# 1. 改版本号: setup.command 的 VERSION + npm/package.json 的 version + models.json 的 latest_version
# 2. 双源同步模型(如有变动) + 测试 + 同步 lib
python3 tests/run_tests.py && python3 scripts/sync_npm_lib.py

# 3. 生成发布 token（网页操作，不落库）:
#    npmjs.com → 头像 → Access Tokens → Generate New Token → Granular Access Token
#    → 必须勾选 "Allow bypass 2FA for automation"（bypass_2fa: True）
#    → Packages: Read and write

# 4. 发布
cd npm
echo '//registry.npmjs.org/:_authToken=<新token>' > /tmp/npmrc-publish
npm publish --cache /tmp/npm-pub-cache --userconfig /tmp/npmrc-publish

# 5. 验证
npm view tokenplan-setup version
npx tokenplan-setup@latest --version

# 6. 用完立刻 revoke token（网页 Access Tokens 页删除）+ rm /tmp/npmrc-publish
```

### 2FA 踩坑记录（别再踩）

- `npm login` 浏览器授权要在 5 分钟内完成，超时会话作废
- 邮箱收到的 8 位 OTP 码只用于**登录**，**发布不接受**
- 007913 之类的自设 6 位 PIN 不是任何 npm 认证要素
- 命令行发布的三条路：
  1. 验证器 App 的 6 位 TOTP 码：`npm publish --otp=<6位码>`（账号需绑 authenticator）
  2. **granular token + bypass 2FA**（推荐，本次成功的路径）
  3. 临时把账号 2FA 降为 "Only at login" → 发布 → 改回（不推荐）
- 判断 token 是否可用：`bypass_2fa: True` + `permissions: package write`（API 查询见下方）

```bash
# 查 token 权限（谁配的谁查）:
curl -s -H "Authorization: Bearer <token>" https://registry.npmjs.org/-/npm/v1/tokens
# 看 objects[] 里 bypass_2fa 和 permissions 字段
```

## 五、运维备忘

- **模型目录月检**：`python3 scripts/check_models.py`，有差异会报 ✚/✖ 并退出 1
- **Kimi-K2.5 已过下线日期**（2026-08-31）：官方文档摘除该行后，check_models 会在
  removed_ids 报出，届时从 models.json + 内置目录删除即可
- **测试环境独立性**：新增测试不得依赖宿主机安装状态（本项两次翻车：Windows 编码、
  CI 无 codex）。CI 裸机必须能过
- **jsDelivr 屏蔽 .bat 直链**（403）：无影响，setup.bat 内部下载的是 .command（200 正常）
- **setup.bat 必须 CRLF**：有测试守着，.editorconfig 锁定
- **本机 npm 环境**：`~/.npm` 有 root 属主缓存文件（历史遗留），用 `--cache /tmp/xxx` 绕开；
  终端里 node/npm 是 Hermes 自带版本（`~/.hermes/node/`，曾触发公司 IT 安全告警，已核实为误报）

## 六、本次发布时间线（2026-09-01 ~ 09-02）

| 时间 | 事件 |
|------|------|
| 09-01 | 仓库公开、CI 修复（Windows 编码 + 平台断言）、模型目录对齐官方（+3 企业模型）|
| 09-01 23:35 | npm login 触发公司 IT 安全告警（Hermes 自带 node，误报，已答复）|
| 09-02 | v1.1.0：国际站套餐、doctor 三态、安装超时、版本感知；测试 92 项 |
| 09-02 12:14 | **npm 发布成功**（mingqizou77 + bypass token），npmmirror 同步 |

## 七、遗留事项

- [ ] **revoke 两个已暴露的 token**（mingqizou 的 `test`、mingqizou77 的 bypass token）→ npmjs 网页 Access Tokens
- [ ] 真机 Windows 验证 setup.bat 双击流程（CI 已覆盖逻辑，人工冒烟未做）
- [ ] Mac 真实 tty 双击 setup.command 冒烟（目前只做过管道模拟）
- [ ] v1.1.0 的微信分发文件重新发放（替换存量 v1.0.0 文件，新文件才有版本感知）
