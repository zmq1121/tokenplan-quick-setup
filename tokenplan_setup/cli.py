"""Command-line entry and compatibility surface."""
import contextlib
import json
import os
import sys
from typing import Dict, List

from tokenplan_setup.domain import TOOLS
from tokenplan_setup.flows import (
    _run_setup_flow,
    build_arg_parser,
    resolve_plan_from_arg,
    resolve_tools_from_arg,
    run_doctor,
    run_uninstall,
)
from tokenplan_setup.infrastructure import (
    EXIT_OK,
    EXIT_USER_CANCEL,
    RESET,
    VERSION,
    YELLOW,
    enable_windows_ansi,
    json_mode_enabled,
    set_runtime_flags,
)


def main() -> int:
    """CLI entry: parse args, verify key, install and configure selected tools.

    退出码:0=成功 1=用户取消 2=环境不满足 3=部分工具配置失败/诊断异常。
    """
    enable_windows_ansi()
    parser = build_arg_parser()
    args = parser.parse_args()
    set_runtime_flags(json_mode=bool(args.json), assume_yes=bool(args.yes))

    if args.command == "doctor":
        doctor_tools = resolve_tools_from_arg(args.tools)
        if doctor_tools is None:
            doctor_tools = list(TOOLS)
        deep_plan = resolve_plan_from_arg(args.plan) if args.deep else None
        deep_key = ""
        if args.deep:
            deep_key = (args.api_key or os.environ.get("TOKENPLAN_API_KEY", "")).strip()
        if json_mode_enabled():
            rows: List[Dict[str, object]] = []
            with contextlib.redirect_stdout(sys.stderr):
                code = run_doctor(
                    doctor_tools, deep=args.deep, plan=deep_plan,
                    api_key=deep_key, rows=rows,
                )
            print(json.dumps(
                {"version": VERSION, "command": "doctor", "tools": rows, "exit_code": code},
                ensure_ascii=False, indent=2,
            ))
            return code
        return run_doctor(
            doctor_tools, deep=args.deep, plan=deep_plan, api_key=deep_key
        )
    if args.command == "uninstall":
        if json_mode_enabled():
            result: Dict[str, object] = {
                "version": VERSION,
                "command": "uninstall",
            }
            with contextlib.redirect_stdout(sys.stderr):
                code = run_uninstall(args.yes, result=result)
            result["exit_code"] = code
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return code
        return run_uninstall(args.yes)

    if json_mode_enabled():
        # stdout 只留给最终 JSON;过程日志(安装输出/交互提示)全部转 stderr,
        # 可观测性不减,管道消费者拿到的是干净的结构化结果
        with contextlib.redirect_stdout(sys.stderr):
            code, result = _run_setup_flow(args)
        result["exit_code"] = code
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    code, result = _run_setup_flow(args)
    return code


if __name__ == "__main__":
    _exit_code = EXIT_OK
    try:
        _exit_code = main()
        if sys.stdin.isatty() and not json_mode_enabled():
            input("  按回车退出...")
    except KeyboardInterrupt:
        print(f"\n  {YELLOW}已取消{RESET}")
        _exit_code = EXIT_USER_CANCEL
    except EOFError:
        pass
    sys.exit(_exit_code)
