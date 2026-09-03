"""Setup, repair, doctor, and uninstall application flows."""
import argparse
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from tokenplan_setup.adapters import (
    CONFIGURATOR_REGISTRY,
    _format_api_error,
    check_prerequisites,
    choose_postpaid_models,
    configure_tool,
    discover_postpaid_models,
    ensure_npm_bin_on_path,
    get_install_command,
    get_model_catalog,
    get_model_ids,
    install_tool,
    is_tool_installed,
    notify_upgrade_available,
    postpaid_chat_models,
    postpaid_discovered_count,
    probe_config,
    refresh_remote_catalog,
    remote_catalog_size,
    render_usage_lines,
    requires_backend_dependency,
    set_postpaid_selection,
    should_manual_download,
    supports_auto_install,
    verify_api_key,
)
from tokenplan_setup.domain import (
    PLAN_BY_KEY,
    PLAN_CATALOG,
    PLAN_GROUPS,
    TOOL_BY_INDEX,
    TOOL_BY_KEY,
    TOOLS,
    PlanSpec,
    ToolSpec,
)
from tokenplan_setup.infrastructure import (
    BACKUP_DIR,
    BRAND_NAME,
    CYAN,
    DIM,
    EXIT_CONFIG_FAILED,
    EXIT_ENV,
    EXIT_OK,
    EXIT_USER_CANCEL,
    GREEN,
    IS_WINDOWS,
    RESET,
    VERSION,
    WHITE,
    YELLOW,
    _http_request,
    ask,
    clear,
    dim,
    display_width,
    info,
    load_state,
    mask_secret,
    ok,
    pad_display,
    print_banner,
    warn,
)


def choose_plan() -> PlanSpec:
    """Interactive plan selection (第一步); EOF without --plan is an error."""
    total = len(PLAN_CATALOG)
    while True:
        print("  ── 第一步：选择套餐 ──")
        print()
        for group_label, group_keys in PLAN_GROUPS:
            print(f"  {CYAN}{group_label}{RESET}")
            for key in group_keys:
                item = PLAN_BY_KEY[key]
                # 模型受限的套餐在菜单里就地提示,避免选完才发现
                note = ""
                if item.only_note and item.only_note.startswith("该套餐仅支持"):
                    note = f" {DIM}（{item.only_note.replace('该套餐', '', 1)}）{RESET}"
                print(f"     [{item.choice}] {item.display_name}{note}")
            print()
        try:
            choice = ask(f"  请输入数字 (1-{total}): ")
        except EOFError:
            print()
            print(f"  {YELLOW}❌ 非交互环境无法选择套餐，请用 --plan 指定（如 --plan enterprise-pro）{RESET}")
            raise SystemExit(1)
        plan = PLAN_CATALOG.get(choice)
        if plan:
            print()
            ok(f"已选择: {plan.display_name}")
            if plan.only_note:
                warn(plan.only_note)
            print()
            return plan
        warn(f"请输入 1-{total} 之间的有效数字")
        print()


def choose_run_mode() -> bool:
    """Interactive mode selection (第三步); EOF defaults to standard."""
    options = (
        ("标准安装 / 补全配置（推荐）", False),
        ("仅修复已有安装的配置", True),
    )
    total = len(options)
    print("  ── 第三步：选择运行模式 ──")
    print()
    for i, (label, _) in enumerate(options, start=1):
        print(f"  [{i}] {label}")
    print()
    while True:
        try:
            choice = ask(f"  请输入数字 (1-{total}): ").strip()
        except EOFError:
            print()
            info("（无输入，默认: 标准安装 / 补全配置）")
            print()
            return False
        if choice in ("1", ""):
            print()
            ok("已选择: 标准安装 / 补全配置")
            print()
            return False
        if choice == "2":
            print()
            ok("已选择: 仅修复已有安装的配置")
            warn("此模式不会安装缺失依赖，只会修复已安装工具的配置")
            print()
            return True
        warn(f"请输入 1-{total}")
        print()


def choose_tools() -> List[ToolSpec]:
    """Interactive tool selection menu (第四步); EOF/empty selects all."""
    print("  ── 第四步：选择工具 ──")
    print()
    print("  输入编号选择，空格分隔；直接回车 = 全部")
    print("  支持输入 all 或 * 选择全部，输入 none 取消选择")
    print()
    # 列宽按显示宽度对齐(中文名按 2 列),再用颜色包裹补齐后的纯文本
    name_width = max(display_width(tool.name) for tool in TOOLS)
    status_width = display_width("✓ 已安装")
    for idx, tool in enumerate(TOOLS, start=1):
        installed = tool.backend == "cli" and is_tool_installed(tool)
        status = pad_display("✓ 已安装" if installed else "· 未安装", status_width)
        if tool.backend == "desktop":
            mode = pad_display("需手动下载", status_width)
            mode_col = f"{YELLOW}{mode}{RESET}"
            status_col = f"{DIM}{status}{RESET}"
        else:
            mode = pad_display("可自动安装", status_width)
            mode_col = f"{GREEN}{mode}{RESET}"
            status_col = (
                f"{GREEN}{status}{RESET}" if installed else f"{DIM}{status}{RESET}"
            )
        print(f"     [{idx:2d}] {pad_display(tool.name, name_width)}  {status_col} {mode_col}")
    print()

    while True:
        try:
            raw = ask("  > ")
        except EOFError:
            info("（无输入，默认选择全部工具）")
            print()
            return list(TOOLS)
        if not raw:
            return list(TOOLS)
        tokens = raw.replace(",", " ").split()
        lowered = {token.lower() for token in tokens}
        if lowered & {"all", "*"}:
            return list(TOOLS)
        if lowered & {"none", "0"}:
            return []
        selected: List[ToolSpec] = []
        invalid: List[str] = []
        for token in tokens:
            candidate = TOOL_BY_INDEX.get(token) or TOOL_BY_KEY.get(token)
            if candidate and candidate not in selected:
                selected.append(candidate)
            elif not candidate:
                invalid.append(token)
        if selected:
            if invalid:
                warn(f"已忽略无效项: {', '.join(invalid)}")
            print()
            return selected
        warn("未识别有效工具编号，请重新输入，或直接回车选择全部")
        print()


def print_usage(tool: ToolSpec, base_url: str, api_key: str) -> None:
    """Print one tool's usage block in the final summary."""
    print(f"  {tool.name}:")
    for line in render_usage_lines(tool, base_url, api_key):
        print(f"    {line}")
    print()


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the argparse CLI (subcommands, plan/key/tools/yes/verify-models)."""
    parser = argparse.ArgumentParser(
        prog="tokenplan-setup",
        description=f"腾讯云 {BRAND_NAME} 一键接入 CLI",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"tokenplan-setup {VERSION}",
        help="显示版本号并退出",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("setup", "repair", "doctor", "uninstall"),
        default="setup",
        help="setup=安装配置（默认），repair=仅修复已安装工具，doctor=仅检查环境，\nuninstall=还原配置并清理安装器写入的修改",
    )
    parser.add_argument(
        "--plan",
        choices=tuple(item.key for item in PLAN_CATALOG.values()),
        help="套餐 key，例如 enterprise-pro",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        help="直接传入 API Key；不传则读环境变量 TOKENPLAN_API_KEY，再退回交互输入"
             "（注意：命令行参数会留在 shell 历史里，自动化场景推荐环境变量）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="结构化输出(setup/doctor)：过程日志转 stderr，stdout 只输出结果 JSON，密钥一律打码",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="doctor 子命令：端到端验证（真实调用一次对话接口；需配合 --plan 与 API Key）",
    )
    parser.add_argument(
        "--tools",
        help="要处理的工具，支持编号或 key，逗号/空格分隔；不传则交互选择",
    )
    parser.add_argument(
        "--models",
        help="只配置指定模型(逗号分隔;后付费套餐按发现列表校验,其余套餐暂不支持)",
        default=None,
        dest="models",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="尽量跳过确认提示（适合自动化）",
    )
    parser.add_argument(
        "--verify-models",
        dest="verify_models",
        choices=("off", "default", "all"),
        default="default",
        help="配置完成后的端到端验证：off=关闭，default=只验默认模型，all=验证全部模型（默认 default）",
    )
    return parser


def resolve_plan_from_arg(plan_key: Optional[str]) -> Optional[PlanSpec]:
    """Map --plan value (key or choice number) to a PlanSpec."""
    if not plan_key:
        return None
    for item in PLAN_CATALOG.values():
        if plan_key in {item.key, item.choice}:
            return item
    return None


def resolve_tools_from_arg(raw: Optional[str]) -> Optional[List[ToolSpec]]:
    """Parse --tools (indices or keys, comma/space) into ToolSpec list."""
    if raw is None:
        return None
    tokens = raw.replace(",", " ").split()
    if not tokens:
        return []
    lowered = {token.lower() for token in tokens}
    if lowered & {"all", "*"}:
        return list(TOOLS)
    if lowered & {"none", "0"}:
        return []
    selected: List[ToolSpec] = []
    invalid: List[str] = []
    for token in tokens:
        tool = TOOL_BY_INDEX.get(token) or TOOL_BY_KEY.get(token) or TOOL_BY_KEY.get(token.lower())
        if tool and tool not in selected:
            selected.append(tool)
        elif not tool:
            invalid.append(token)
    if invalid:
        warn(f"已忽略无效工具项: {', '.join(invalid)}")
    return selected


def run_doctor(
    selected_tools: List[ToolSpec],
    deep: bool = False,
    plan: Optional[PlanSpec] = None,
    api_key: str = "",
    rows: Optional[List[Dict[str, object]]] = None,
) -> int:
    """Read-only diagnosis: prerequisites plus per-tool install status.

    退出码:0=全部健康,2=前置条件不满足,3=存在"已安装但配置缺失"的工具
    或 --deep 端到端验证失败(对齐 thcli:doctor 可被脚本判断,而非只读文案)。
    rows 供 --json 模式收集结构化结果(不影响文本输出)。
    """
    clear()
    print()
    print_banner(f"{BRAND_NAME} 环境诊断")
    print()
    prerequisites_ready = check_prerequisites(selected_tools)
    print()
    print("  ── 工具状态 ──")
    print()
    misconfigured = 0
    for tool in selected_tools:
        installed = is_tool_installed(tool)
        configured = probe_config(tool)
        if configured is True and not installed:
            # 配置已写好但应用本体不在(桌面应用手动安装类,如 WorkBuddy)
            status = f"未安装应用,但 {BRAND_NAME} 模型配置已就绪"
        elif installed and configured is True:
            status = f"已安装,{BRAND_NAME} 配置有效"
        elif installed and configured is False:
            status = f"已安装,{BRAND_NAME} 配置缺失"
        elif installed:
            status = "已安装"
        else:
            status = "未安装"
        if installed and configured is False:
            misconfigured += 1
        if rows is not None:
            rows.append(
                {
                    "key": tool.key,
                    "name": tool.name,
                    "installed": installed,
                    "configured": configured,
                    "status": status,
                    "config_path": tool.cfg_hint,
                }
            )
        print(f"  {tool.name}: {status}")
        print(f"    配置位置: {tool.cfg_hint}")
        if installed and configured is False:
            print("    建议: 运行 repair 子命令恢复配置(不会重装程序)")
        if not installed and should_manual_download(tool):
            if tool.backend == "desktop":
                print("    接入方式: 手动获取应用，运行 setup 查看分步引导")
            else:
                print("    将自动安装: 否（当前平台需手动安装）")
            if tool.download_url:
                print(f"    手动安装: {tool.download_url}")
        elif not installed and supports_auto_install(tool):
            print("    将自动安装: 是")
            if tool.install_script and not IS_WINDOWS:
                print(f"    安装方式: 远程脚本（{tool.install_script}，下载后校验确认再执行）")
            command = get_install_command(tool)
            if command:
                if isinstance(command, tuple):
                    print(f"    安装命令: {' '.join(command)}")
                else:
                    print(f"    安装命令: {command}")
        elif not installed:
            print("    将自动安装: 否")
        print()

    deep_failed = False
    if deep:
        if not plan:
            warn("doctor --deep 需要 --plan 指定要验证的套餐(如 --plan enterprise-pro)")
            return EXIT_ENV
        if not api_key:
            warn("doctor --deep 需要 API Key(--api-key 或环境变量 TOKENPLAN_API_KEY)")
            return EXIT_ENV
        print("  ── 端到端验证（真实调用一次 /chat/completions） ──")
        print()
        default_model = str(get_model_catalog(plan.key)["default"])
        passed, reason = test_model(plan.base_url, api_key, default_model)
        if rows is not None:
            rows.append(
                {
                    "key": "e2e",
                    "name": f"端到端验证({plan.key}/{default_model})",
                    "passed": passed,
                    "reason": reason,
                }
            )
        if passed:
            ok(f"{default_model} 端到端可用")
        else:
            warn(f"{default_model} 端到端失败: {reason}")
        deep_failed = not passed
        print()

    if not prerequisites_ready:
        return EXIT_ENV
    if misconfigured or deep_failed:
        return EXIT_CONFIG_FAILED
    return EXIT_OK


def collect_latest_backups() -> Dict[str, str]:
    """Group manifest entries by original path, keeping the newest backup."""
    manifest = BACKUP_DIR / "manifest.jsonl"
    newest: Dict[str, Tuple[str, str]] = {}  # original -> (ts, backup_name)
    if not manifest.exists():
        return {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        original = entry.get("original")
        backup = entry.get("backup")
        ts = entry.get("ts", "")
        if not original or not backup:
            continue
        current = newest.get(original)
        if current is None or ts >= current[0]:
            newest[original] = (ts, backup)
    return {original: backup for original, (_, backup) in newest.items()}


def strip_rc_block(rc_path_str: str, marker: str) -> bool:
    """Remove the marker line plus its single following line from an rc file."""
    rc_path = Path(rc_path_str)
    if not rc_path.exists() or not marker:
        return False
    lines = rc_path.read_text().splitlines()
    if marker not in lines:
        return False
    out: List[str] = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.strip() == marker:
            skip_next = True
            continue
        out.append(line)
    rc_path.write_text("\n".join(out).rstrip() + "\n")
    return True


def run_uninstall(
    yes: bool, result: Optional[Dict[str, object]] = None
) -> int:
    """Restore tracked side effects; return 3 if any operation fails."""
    failures: List[Dict[str, str]] = []
    operations: List[Dict[str, str]] = []

    def succeeded(kind: str, target: str) -> None:
        operations.append({"kind": kind, "target": target, "status": "ok"})

    def failed(kind: str, target: str, reason: str) -> None:
        operations.append(
            {"kind": kind, "target": target, "status": "failed", "error": reason}
        )
        failures.append({"kind": kind, "target": target, "error": reason})

    clear()
    print()
    print_banner(f"{BRAND_NAME} 接入卸载 / 还原")
    print()
    info("卸载范围：配置还原 + 安装器写入的文件/环境变量/PATH 修改")
    warn("不会卸载工具本体（npm 包、CLI 程序不会被删除）")
    print()

    state = load_state()
    latest = collect_latest_backups()
    rc_blocks = state.get("rc_blocks", [])
    files_written = state.get("files_written", [])
    env_files = state.get("env_files", [])
    setx_keys = state.get("setx_keys", [])
    remote_scripts = state.get("remote_scripts", [])

    def report_remote_scripts() -> None:
        """远程脚本的副作用不在可回滚台账内,无论有无其他记录都必须如实告知。"""
        if not remote_scripts:
            return
        print("  ── 远程安装脚本（无法自动回滚） ──")
        print()
        warn("以下第三方脚本曾以当前用户身份执行，其副作用不在本工具台账内：")
        for item in remote_scripts:
            if not isinstance(item, dict):
                continue
            info(f"{item.get('tool', '?')}: {item.get('url', '?')}")
            dim(f"  SHA256: {item.get('sha256', '?')}")
        info("如需彻底清理，请按对应工具的官方卸载说明处理")
        print()

    def publish(code: int) -> int:
        """统一 JSON 出口,保证两条返回路径的字段形状一致。"""
        if result is not None:
            result.update({
                "operations": operations,
                "failures": failures,
                "remote_scripts": [
                    item for item in remote_scripts if isinstance(item, dict)
                ],
            })
        return code

    if not latest and not rc_blocks and not files_written and not env_files and not setx_keys:
        warn("没有可还原的记录（~/.tokenplan-backups 为空或缺少清单）")
        report_remote_scripts()
        return publish(EXIT_OK)

    print(f"  可还原配置文件: {len(latest)} 个")
    print(f"  可移除 rc 修改: {len(rc_blocks)} 处")
    print(f"  可删除生成文件: {len(files_written) + len(env_files)} 个")
    if IS_WINDOWS:
        print(f"  可还原环境变量: {len(setx_keys)} 个")
    print()

    if not yes:
        confirm = ask("  确认执行卸载还原？(y/n): ")
        if confirm.lower() != "y":
            print(f"\n  {YELLOW}已取消{RESET}")
            return 0
        print()

    print("  ── 还原配置文件 ──")
    print()
    for original, backup_name in latest.items():
        backup = BACKUP_DIR / backup_name
        target = Path(original)
        if backup.exists():
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, target)
                ok(f"已还原: {original}")
                succeeded("restore", original)
            except OSError as exc:
                warn(f"还原失败: {original} ({exc})")
                failed("restore", original, str(exc))
        else:
            reason = f"备份文件缺失: {backup_name}"
            warn(f"{reason}，无法还原: {original}")
            failed("restore", original, reason)
    print()

    if rc_blocks:
        print("  ── 移除 rc 文件修改 ──")
        print()
        cleaned = 0
        for block in rc_blocks:
            if not isinstance(block, dict):
                failed("remove_rc", repr(block), "无效的 rc 台账记录")
                continue
            path_str = str(block.get("file", ""))
            marker = str(block.get("marker", ""))
            try:
                if strip_rc_block(path_str, marker):
                    cleaned += 1
                succeeded("remove_rc", path_str)
            except OSError as exc:
                warn(f"rc 修改清理失败: {path_str} ({exc})")
                failed("remove_rc", path_str, str(exc))
        if cleaned:
            ok(f"已清理 {cleaned} 处 rc 修改")
        else:
            info("没有需要清理的 rc 修改")
        print()

    if files_written or env_files:
        print("  ── 删除安装器生成的文件 ──")
        print()
        for path_str in list(files_written) + list(env_files):
            p = Path(path_str)
            if p.exists():
                try:
                    p.unlink()
                    ok(f"已删除: {path_str}")
                    succeeded("delete", path_str)
                except OSError as exc:
                    warn(f"删除失败: {path_str} ({exc})")
                    failed("delete", path_str, str(exc))
        print()

    if IS_WINDOWS and setx_keys:
        print("  ── 还原 Windows 环境变量 ──")
        print()
        for item in setx_keys:
            if not isinstance(item, dict):
                failed("environment", repr(item), "无效的环境变量台账记录")
                continue
            key = item.get("key", "")
            if not key:
                failed("environment", repr(item), "环境变量名为空")
                continue
            old = item.get("old")
            command = (
                ["setx", key, str(old)]
                if old is not None
                else ["reg", "delete", "HKCU\\Environment", "/v", key, "/f"]
            )
            try:
                completed = subprocess.run(
                    command, capture_output=True, text=True, check=False
                )
                if completed.returncode != 0:
                    detail = (completed.stderr or completed.stdout or "").strip()
                    reason = f"命令退出码 {completed.returncode}"
                    if detail:
                        reason = f"{reason}: {detail}"
                    warn(f"环境变量操作失败: {key} ({reason})")
                    failed("environment", key, reason)
                    continue
                if old is not None:
                    os.environ[key] = str(old)
                    ok(f"已还原原值: {key}")
                else:
                    os.environ.pop(key, None)
                    ok(f"已删除: {key}")
                succeeded("environment", key)
            except OSError as exc:
                warn(f"环境变量操作失败: {key} ({exc})")
                failed("environment", key, str(exc))
        print()

    report_remote_scripts()

    print("  ── 完成 ──")
    print()
    info(f"备份目录保留在 {BACKUP_DIR}，确认无误后可手动删除")
    if failures:
        warn(f"卸载还原有 {len(failures)} 项失败，请根据上方提示处理后重试")
    return publish(EXIT_CONFIG_FAILED if failures else EXIT_OK)


def fetch_remote_models(base_url: str, api_key: str) -> Optional[List[str]]:
    """Fetch the model list from the OpenAI-compatible /models endpoint.

    Note: only lkeap (personal plans) and the postpaid tokenhub /v1
    expose /models; the tokenhub plan/v3 domains return 404. Callers
    treat None as "skip the cross-check" — cosmetic only.
    """
    if "/plan/v3" in base_url and "lkeap" not in base_url:
        return None  # tokenhub plan 域不提供 /models(已探活确认)
    try:
        status, body = _http_request(
            f"{base_url}/models", api_key=api_key, method="GET"
        )
        if status != 0:
            return None
        payload = json.loads(body.decode(errors="ignore"))
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, list):
            ids = [
                model_id
                for item in data
                if isinstance(item, dict)
                for model_id in [item.get("id")]
                if isinstance(model_id, str) and model_id
            ]
            if ids:
                return sorted(ids)
    except Exception:
        pass
    return None


def _test_model_once(
    base_url: str, api_key: str, model: str, retry_no5xx: bool = True,
    prev_error: str = "",
) -> Tuple[bool, str]:
    """Single verification attempt; optionally retry once on 5xx gateway errors."""
    try:
        status, body = _http_request(
            f"{base_url}/chat/completions",
            api_key=api_key,
            payload={
                "model": model,
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        if status == 0:
            return True, ""
        if retry_no5xx and 500 <= status <= 599:
            # 网关瞬时错误(upstream_error 等):稍候重试一次,避免误报
            time.sleep(2)
            return _test_model_once(base_url, api_key, model, retry_no5xx=False,
                                    prev_error=f"HTTP {status}")
        detail = f"HTTP {status}: {_format_api_error(body.decode(errors='ignore'), limit=100)}"
        if prev_error and 500 <= status <= 599:
            return False, f"{detail}（重试后仍失败,疑似服务端瞬时故障）"
        return False, detail
    except RuntimeError as exc:
        return False, str(exc)


def test_model(base_url: str, api_key: str, model: str) -> Tuple[bool, str]:
    """Verify a model end to end (with one retry on transient 5xx)."""
    return _test_model_once(base_url, api_key, model)


def verify_models(
    base_url: str, api_key: str, plan: PlanSpec, mode: str = "default"
) -> Dict[str, Tuple[bool, str]]:
    """End-to-end verification of the model IDs that were written to configs."""
    catalog_ids = get_model_ids(plan.key)
    default_model = str(get_model_catalog(plan.key)["default"])
    if mode == "all":
        targets = catalog_ids or [default_model]
    else:
        targets = [default_model]
    print("  ── 端到端验证（真实调用 /chat/completions） ──")
    print()
    results: Dict[str, Tuple[bool, str]] = {}
    for model in targets:
        passed, reason = test_model(base_url, api_key, model)
        results[model] = (passed, reason)
        if passed:
            ok(f"{model}")
        else:
            warn(f"{model} — {reason}")
    print()
    failed = [m for m, (p, _) in results.items() if not p]
    if failed:
        warn(f"{len(failed)} 个模型验证失败；配置仍已写入，请检查模型 ID 或套餐权限")
    else:
        ok(f"全部 {len(targets)} 个模型验证通过，配置立即可用")
    print()
    return results


def _run_setup_flow(args: argparse.Namespace) -> Tuple[int, Dict[str, object]]:
    """The setup/repair flow; returns (exit_code, machine-readable result).

    (拆出 main 供 --json 复用:人类可读输出在外层被重定向到 stderr,
    返回值携带结构化结果——对齐 thcli 的 --json 口径:密钥在 JSON 里
    一律打码,因为 JSON 会被转发、落盘、进对话历史。)
    """
    result: Dict[str, object] = {"version": VERSION, "command": args.command}

    clear()
    print()
    print_banner(f"腾讯云 {BRAND_NAME} — 一键接入 CLI", "只需 API Key，其余尽可能自动")
    print()
    print("  命令: setup / repair / doctor / uninstall")
    print(f"  版本: v{VERSION}（默认: setup）")
    print()

    plan = resolve_plan_from_arg(args.plan) or choose_plan()
    base_url = plan.base_url
    key_url = plan.key_url
    result.update({"plan": plan.key, "plan_name": plan.display_name, "base_url": base_url})

    print("  ── 第二步：输入 API Key ──")
    print()
    info(f"获取地址: {key_url}")
    print()
    info("建议使用有权限的完整 API Key，粘贴时请避免前后空格")
    print()
    # Key 解析优先级:--api-key 参数 > 环境变量 TOKENPLAN_API_KEY > 交互输入
    # (命令行参数会留在 shell 历史里,自动化场景推荐环境变量)
    api_key = args.api_key.strip() if args.api_key else ""
    if api_key and len(api_key) < 10:
        print(f"\n  {YELLOW}❌ --api-key 传入的 Key 无效（长度过短），请检查后重试。{RESET}")
        return EXIT_USER_CANCEL, result
    if not api_key:
        env_key = os.environ.get("TOKENPLAN_API_KEY", "").strip()
        if env_key:
            if len(env_key) >= 10:
                info("已从环境变量 TOKENPLAN_API_KEY 读取 API Key")
                api_key = env_key
            else:
                warn("环境变量 TOKENPLAN_API_KEY 中的 Key 长度过短，已忽略")
    while not api_key:
        try:
            api_key = ask("  请粘贴 API Key: ").strip()
        except EOFError:
            print(f"\n  {YELLOW}未输入 API Key，已取消。{RESET}")
            return EXIT_USER_CANCEL, result
        if not api_key:
            print(f"\n  {YELLOW}未输入 API Key，已取消。{RESET}")
            return EXIT_USER_CANCEL, result
        if len(api_key) < 10:
            warn("API Key 看起来不完整（长度过短），请重新粘贴完整 Key")
            print()
            api_key = ""
            continue
    result["api_key"] = mask_secret(api_key)
    print()

    if not verify_api_key(base_url, api_key, plan):
        warn("API Key 验证失败，请检查 Key 是否正确")
        print()
        try:
            confirmed = ask("  是否继续？(y/n): ").lower()
        except EOFError:
            confirmed = "n"
        if not args.yes and confirmed != "y":
            return EXIT_USER_CANCEL, result
    else:
        ok("API Key 验证通过")
    print()

    refresh_remote_catalog()
    remote_count = remote_catalog_size()
    if remote_count:
        info(f"模型目录已更新（远程 {remote_count} 条）")
    else:
        info("使用内置模型目录（远程目录不可用或未通过完整性校验）")
    notify_upgrade_available()
    print()

    if plan.key in ("postpaid", "postpaid-intl"):
        # 后付费:目录即发现结果,无交叉检查
        if not postpaid_discovered_count():
            # verify 失败后用户仍选择继续:再试一次发现,失败则中止
            ids = discover_postpaid_models(base_url, api_key)
            if not ids:
                warn("后付费模式需要联网获取模型列表,无法继续")
                return EXIT_ENV, result
        chat = postpaid_chat_models()
        ok(f"后付费模型列表已获取（{postpaid_discovered_count()} 个,其中聊天模型 {len(chat)} 个）")
        if args.models:
            chosen = set_postpaid_selection(
                [t for t in re.split(r"[\s,，]+", args.models) if t]
            )
            ok(f"按 --models 配置 {len(chosen)} 个模型")
        elif not args.yes:
            choose_postpaid_models()
    else:
        remote_models = fetch_remote_models(base_url, api_key)
        if remote_models:
            catalog_ids = get_model_ids(plan.key)
            missing = [m for m in catalog_ids if m not in remote_models]
            if missing:
                warn(f"以下目录模型未出现在 API 模型列表中（可能已下线）: {', '.join(missing)}")
            else:
                ok(f"API 模型列表可用（{len(remote_models)} 个），目录模型全部在列")
    result["models"] = get_model_ids(plan.key)
    print()

    if args.models and plan.key not in ("postpaid", "postpaid-intl"):
        warn("--models 目前仅支持后付费套餐,已忽略")

    repair_mode = args.command == "repair" or (args.command == "setup" and choose_run_mode())

    selected_tools = resolve_tools_from_arg(args.tools)
    if selected_tools is None:
        # choose_tools handles EOF (non-interactive) by defaulting to all.
        selected_tools = choose_tools()
    if not selected_tools:
        warn("未选择任何工具，脚本已结束")
        return EXIT_USER_CANCEL, result

    prerequisites_ready = check_prerequisites(selected_tools)
    if not prerequisites_ready:
        warn("关键前置条件未满足，请先按上面的提示完成安装，再重新运行本安装器")
        return EXIT_ENV, result

    print(f"  ── 正在配置 {len(selected_tools)} 个工具 ──")
    print()

    installed: List[ToolSpec] = []
    failed: List[Tuple[ToolSpec, str]] = []
    skipped: List[ToolSpec] = []

    total = len(selected_tools)
    bar_len = 20

    ensure_npm_bin_on_path()
    for index, tool in enumerate(selected_tools, start=1):
        filled = int((index / total) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        print(f"  [{bar}] {index}/{total}")
        print(f"  📦 {tool.name}")
        print()

        already_installed = is_tool_installed(tool)

        if should_manual_download(tool):
            # 桌面应用无法自动安装,但配置可写的工具(如 WorkBuddy)仍要写配置:
            # 用户装好应用后打开即用,不需要重跑安装器
            if tool.key in CONFIGURATOR_REGISTRY:
                try:
                    configure_tool(tool, base_url, api_key, plan)
                    installed.append(tool)
                    ok("配置已写入(应用本体需自行下载安装)")
                except Exception as exc:
                    failed.append((tool, str(exc)))
                    warn(f"配置失败: {exc}")
            else:
                skipped.append(tool)
                warn(f"请先下载 {tool.name}")
            if tool.download_url:
                info(f"下载: {tool.download_url}")
            if tool.backend == "desktop" and tool.key not in CONFIGURATOR_REGISTRY:
                info("手动接入步骤:")
                for line in render_usage_lines(tool, base_url, api_key):
                    info(f"  {line}")
            print()
            continue

        if repair_mode and not already_installed:
            skipped.append(tool)
            warn(f"{tool.name} 尚未安装，已跳过修复")
            print()
            continue

        if requires_backend_dependency(tool, "npx") and not shutil.which("npx"):
            failed.append((tool, f"缺少 npx，无法启动 {tool.name}"))
            warn(f"{tool.name} 需要 Node.js / npx（含 npm 的 LTS 版本即可）")
            info("安装地址: https://nodejs.org/en/download")
            print()
            continue

        if not already_installed and supports_auto_install(tool):
            if repair_mode:
                skipped.append(tool)
                warn(f"{tool.name} 未检测到已安装状态，修复模式已跳过安装")
                print()
                continue
            if not install_tool(tool):
                failed.append((tool, "安装失败"))
                print()
                continue
        elif not already_installed and get_install_command(tool):
            if repair_mode:
                skipped.append(tool)
                warn(f"{tool.name} 未检测到已安装状态，修复模式已跳过安装")
                print()
                continue
            failed.append((tool, "当前环境不支持自动安装"))
            warn(f"{tool.name} 无法在当前环境自动安装")
            print()
            continue
        else:
            dim("已安装")

        try:
            configure_tool(tool, base_url, api_key, plan)
            installed.append(tool)
            ok("配置完成")
        except Exception as exc:
            failed.append((tool, str(exc)))
            warn(f"配置失败: {exc}")

        if should_manual_download(tool):
            info(f"打开 {tool.name} → 设置 → 模型")
            info(f"Base URL: {base_url}")
            info(f"API Key:  {mask_secret(api_key)}")
        print()

    print(f"  [{'█' * bar_len}] {total}/{total}")
    print()
    print_banner("配 置 完 成")
    print()

    if repair_mode:
        print("  本次运行采用的是修复模式，只会修复已安装工具的配置。")
        print()
    if installed:
        print(f"  {GREEN}✅ 已配置 {len(installed)} 个工具:{RESET}")
        for tool in installed:
            print(f"       {tool.name}")
            for line in render_usage_lines(tool, base_url, api_key):
                print(f"         {line}")
    if skipped:
        print(f"  {YELLOW}📝 需手动下载 {len(skipped)} 个工具:{RESET}")
        for tool in skipped:
            print(f"       {tool.name} — {tool.download_url or '见使用说明'}")
            if tool.backend == "desktop":
                for line in render_usage_lines(tool, base_url, api_key):
                    print(f"         {line}")
    if failed:
        print(f"  {YELLOW}❌ 失败 {len(failed)} 个工具:{RESET}")
        for tool, reason in failed:
            print(f"       {tool.name} — {reason}")
    if BACKUP_DIR.exists():
        backups = list(BACKUP_DIR.glob("*.bak"))
        if backups:
            print(f"  {WHITE}💾 原有配置已备份到: {BACKUP_DIR}{RESET}")
    if load_state().get("rc_blocks"):
        shell = os.environ.get("SHELL", "")
        rc_name = ".zshrc" if shell.endswith("/zsh") else ".bashrc"
        print(f"  {WHITE}💡 新装命令在新开终端中生效；当前终端可先执行: source ~/{rc_name}{RESET}")
    print()
    print("  ── 如何使用 ──")
    print()

    for tool in installed:
        print_usage(tool, base_url, api_key)

    print(f"  API 端点: {base_url}")
    print(f"  模型参考: {key_url.replace('api-key', '')}")
    print()

    catalog = get_model_catalog(plan.key)
    raw_models = catalog.get("display", ())
    models = (
        tuple(model for model in raw_models if isinstance(model, str))
        if isinstance(raw_models, (list, tuple))
        else ()
    )
    if models:
        count = len(models)
        print(f"  可用模型 ({count}个):")
        for model_line in models:
            print(f"    {model_line}")
        print()

    verified: Dict[str, Tuple[bool, str]] = {}
    if installed and args.verify_models != "off":
        verified = verify_models(base_url, api_key, plan, mode=args.verify_models)

    result["tools"] = (
        [
            {"key": t.key, "name": t.name, "status": "configured"}
            for t in installed
        ]
        + [
            {"key": t.key, "name": t.name, "status": "failed", "error": reason}
            for t, reason in failed
        ]
        + [
            {"key": t.key, "name": t.name, "status": "skipped"}
            for t in skipped
        ]
    )
    result["verified"] = {m: passed for m, (passed, _) in verified.items()}
    verification_failed = any(not passed for passed, _ in verified.values())
    exit_code = EXIT_CONFIG_FAILED if failed or verification_failed else EXIT_OK
    return exit_code, result


__all__ = [name for name in globals() if not name.startswith("__")]
