# 工程审计记录

本文记录 2026-09-03 对当前仓库安装、验证和卸载关键路径的代码审计结果。结论来自源码检查与本仓库回归测试，不代表对所有目标工具版本、真实账号权限或全部 Windows 主机的外部认证。

## 范围与兼容边界

- 逻辑源位于 `tokenplan_setup/`；`setup.command`、`npm/lib/setup.command` 和 `setup.bat` 是 `scripts/build_dist.py` 生成或同步的发布物。
- 支持的命令退出码保持为：`0` 成功、`1` 用户取消、`2` 环境不满足、`3` 配置、验证或卸载还原失败。
- `repair` 仅修复检测为已安装的 CLI 工具，不安装缺失工具。可预写配置的桌面工具仍沿用既有行为；这不等同于安装应用本体。
- WorkBuddy 被 `pgrep -f WorkBuddy` 检测为运行中时，配置必须在写文件前失败，避免应用退出时用内存状态覆盖新配置。
- Windows 用户环境变量卸载按台账处理：存在旧值时用 `setx` 还原；安装器新增的变量用 `reg delete HKCU\Environment` 删除。
- `--json` 的 `exit_code` 必须与进程退出码一致。过程日志写入 stderr，stdout 保持为单个 JSON 文档。

## 已证实问题与风险

### 高风险：模型验证失败未影响 setup 退出码

此前 `_run_setup_flow` 只依据工具配置器的 `failed` 列表决定退出码。即使 `verify_models` 中一个或多个模型真实调用失败，setup 仍返回 `0`，自动化调用方可能把不可用配置判为成功。

整改状态：已修复。任一已执行的模型验证失败均返回 `EXIT_CONFIG_FAILED`（3），并保持 `verified` JSON 字段与退出码一致。`--verify-models off` 不执行验证，也不因此失败。

### 高风险：卸载部分失败仍返回成功

此前备份还原、生成文件删除失败只打印警告；Windows `setx` / `reg delete` 的返回码未检查，函数最终固定返回 `0`。这会掩盖残留配置或环境变量。

整改状态：已修复。备份缺失、还原异常、记录中的 rc 清理异常、文件删除异常，以及 Windows 环境变量命令异常或非零返回码都会被汇总，并使卸载返回 `EXIT_CONFIG_FAILED`（3）。成功操作不因其它项失败而停止，便于一次尽量完成清理。

### 中风险：卸载缺少结构化结果

此前 `uninstall --json` 仍走文本路径，不能像 setup/doctor 一样提供稳定的机器可读结果。

整改状态：已修复。卸载 JSON 现在包含 `version`、`command`、`operations`、`failures` 与 `exit_code`；文本和 JSON 路径共享同一执行函数和退出码判断。

### 高风险防回归项：运行中的 WorkBuddy 覆盖配置

源码已有写入前进程检测和 fail-closed 行为，但该行为需要测试保护，否则重构可能把检查移到写入之后或忽略异常。

整改状态：已增加回归测试，模拟 `pgrep` 返回运行中并验证配置器抛错、原文件字节不变。该测试验证本地控制流，不证明所有平台上的进程名始终相同。

### 高风险防回归项：repair 意外安装缺失工具

repair 的现有分支会跳过未安装 CLI；若分支顺序回退，可能触发 npm 或远程安装脚本。

整改状态：已增加回归测试，以安装器调用计数确认未安装 Codex 在 repair 中不会触发 `install_tool`。

## 验证策略

新增测试覆盖以下契约：

- repair 不安装缺失 CLI；
- WorkBuddy 运行中不写配置；
- Windows 卸载分别执行旧值还原和新增变量删除，并传播命令失败；
- setup 的任一模型验证失败返回 3；
- 卸载的还原、文件删除或环境变量操作失败返回 3；
- uninstall 文本与 JSON 的退出码一致，JSON 暴露失败操作。

最终发布物须由 `python3 scripts/build_dist.py` 重建，并通过完整的 `python3 tests/run_tests.py` 与 `python3 scripts/build_dist.py --check`。真实 Windows 注册表行为仍依赖 CI 或 Windows 主机验证；本地测试使用 Windows 分支模拟和 subprocess 桩，不将其表述为真实系统端到端测试。

## 测试正规化基线

`pytest` 现参数化执行全部旧 `TEST_GROUPS`，旧套件的 293 条断言会直接执行
`tokenplan_setup/` 分层源码并进入 coverage 统计；`python3 tests/run_tests.py` 仍保留为
零第三方依赖兼容检查。发布物一致性与子进程入口继续由 build contract 和 smoke 测试负责，
不再用发布物执行代替源码覆盖。

2026-09-03 在 Python 3.9、分支覆盖开启时的实测基线为：总体 80.50%（95 项 pytest），
`tokenplan_setup.infrastructure` 85%+，`tokenplan_setup.adapters` 82%+。CI 的
`fail_under` 设为 75%，用于阻止明显回退并保留跨平台分支差异余量。

这个数字的构成必须如实记录：**只跑分层 pytest（排除参数化的旧回归）时总覆盖为 40.68%
（65 项）**，即覆盖率主体仍由旧回归套件提供。此前该数字是 29.78%，提升来自新增的
`tests/test_failure_paths.py`（远程目录完整性三态、后付费发现失败、远程脚本 fail-closed
与执行留痕、安装命令失败、npm 精确 pin 与私有 cache、Windows setx/reg 台账）与
`tests/test_isolation.py`（路径常量沙箱守卫）。因此不能把 80.50% 解读为"分层测试已经充分"。

补测过程中发现并修复了一个真实的测试隔离缺陷：`flows` 持有 `BACKUP_DIR` 的导入期快照，
`isolated_home` 只 patch `infrastructure` 因而失效，`uninstall` 在测试中会读取真实的
`~/.tokenplan-backups` 并尝试覆盖真实用户配置。现已改为对所有持有快照的模块动态打补丁，
并由 `test_isolation.py` 遍历包内模块守住这一点。

后续应继续补交互式主流程分支与平台专属路径，而不是通过排除源码或虚构阈值提高数字。
