"""Standard-library infrastructure, I/O, state, and terminal helpers."""
# -*- coding: utf-8 -*-
# 腾讯云 TokenHub — 小白一键接入
# Mac: 终端运行 | Windows: 右键→Python 打开
import argparse
import contextlib
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

HOME = Path.home()
VERSION = "2.7.1"

# ── 品牌口径(集中定义;所有工具配置里用户可见的名称由此派生) ──────────────
# 接入平台是腾讯云 TokenHub(端点域名/控制台口径)。2.5.x 及之前曾以
# "Token Plan"/"tokenplan"/"token-plan"/"tencent-tokenplan" 作为展示名,
# 与所接入平台不一致,已统一收敛为 TokenHub;旧键在各 configurator
# 重写时自动摘除(见 BRAND_LEGACY_KEYS),doctor 对旧品牌配置不误报。
BRAND_NAME = "TokenHub"                  # 展示名(横幅 / provider name / displayName)
BRAND_SLUG = "tokenhub"                  # 配置内 provider 键与模型前缀(tokenhub/<model>)
BRAND_VENDOR = "Tencent Cloud TokenHub"  # vendor/name 全称(WorkBuddy/ZCode/Codex/OpenCode)
# 环境变量名 TOKENPLAN_API_KEY 保留不变:已发布文档与用户 shell 配置依赖它
BRAND_LEGACY_KEYS = ("tokenplan", "token-plan", "tencent-tokenplan")  # 旧 provider 键,重写时摘除

# 退出码契约(对齐 thcli 的纪律:失败路径必须非 0 且错误进提示区,
# 脚本/CI 无需解析随语言变化的文案即可判断成败):
#   0 = 成功   1 = 用户取消   2 = 环境不满足   3 = 部分/全部工具配置失败
EXIT_OK = 0
EXIT_USER_CANCEL = 1
EXIT_ENV = 2
EXIT_CONFIG_FAILED = 3
RESET = "\033[0m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
BLUE = "\033[34m"
WHITE = "\033[37m"
DIM = "\033[2m"

BACKUP_DIR = HOME / ".tokenplan-backups"
DEFAULT_TIMEOUT = 10
# 安装命令(npm 等)的最长等待;超时视为网络受限而非无限转圈
INSTALL_TIMEOUT = 600


IS_WINDOWS = sys.platform == "win32"

# JSON 输出模式(--json):人类可读输出重定向到 stderr,stdout 只留给最终 JSON
_JSON_MODE = False
# --yes:跳过远程脚本执行确认(来源与 SHA256 仍会完整打印)
_ASSUME_YES = False


def set_runtime_flags(*, json_mode: bool, assume_yes: bool) -> None:
    """Update process-wide CLI flags for both package and bundled execution."""
    global _JSON_MODE, _ASSUME_YES
    _JSON_MODE = json_mode
    _ASSUME_YES = assume_yes


def json_mode_enabled() -> bool:
    """Return whether human-readable output is redirected away from stdout."""
    return _JSON_MODE


@dataclass
class RunContext:
    """Mutable process state grouped for gradual migration from legacy globals.

    The generated single-file artifact still exposes the historical globals, while
    new package code can pass or inspect one explicit context object.
    """

    home: Path
    backup_dir: Path
    state_path: Path
    json_mode: bool = False
    assume_yes: bool = False


RUN_CONTEXT = RunContext(
    home=HOME,
    backup_dir=BACKUP_DIR,
    state_path=BACKUP_DIR / "state.json",
)


def _sync_run_context() -> RunContext:
    """Mirror compatibility globals into the explicit runtime context."""
    RUN_CONTEXT.home = HOME
    RUN_CONTEXT.backup_dir = BACKUP_DIR
    RUN_CONTEXT.state_path = STATE_PATH if "STATE_PATH" in globals() else BACKUP_DIR / "state.json"
    RUN_CONTEXT.json_mode = _JSON_MODE
    RUN_CONTEXT.assume_yes = _ASSUME_YES
    return RUN_CONTEXT


def display_width(text: str) -> int:
    """终端显示宽度(CJK 全角按 2 列),用于中英文混排的列对齐。"""
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in text)


def pad_display(text: str, width: int) -> str:
    """按显示宽度右补空格:与 str.ljust 不同,中文按 2 列计算。"""
    return text + " " * max(0, width - display_width(text))


def print_banner(*lines: str) -> None:
    """统一横幅:按显示宽度居中,保证中文标题下右边框也对齐。"""
    width = 46
    print("  ╔" + "═" * width + "╗")
    for line in lines:
        pad = width - display_width(line)
        left = pad // 2
        print("  ║" + " " * left + line + " " * (pad - left) + "║")
    print("  ╚" + "═" * width + "╝")


def clear() -> None:
    """Clear the terminal (cls on Windows, ANSI reset elsewhere)."""
    if _sync_run_context().json_mode:
        return
    if IS_WINDOWS:
        # Tests emulate Windows on POSIX; invoke cls only on a real NT host.
        if os.name == "nt":
            os.system("cls")
        return
    print("\033[2J\033[H", end="")


def ok(msg: str) -> None:
    """Print a green success line."""
    print(f"  {GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    """Print a yellow warning line."""
    print(f"  {YELLOW}⚠{RESET}  {msg}")


def info(msg: str) -> None:
    """Print a blue informational line."""
    print(f"  {BLUE}→{RESET} {msg}")


def dim(msg: str) -> None:
    """Print a plain neutral line."""
    print(f"  {WHITE}{msg}{RESET}")


def ask(msg: str) -> str:
    """Prompt for input, stripped of whitespace."""
    return input(f"  {msg}").strip()


def mask_secret(secret: str, visible: int = 4) -> str:
    """Mask a secret for display, keeping only the first `visible` chars."""
    if not secret:
        return ""
    if len(secret) <= visible:
        return "*" * len(secret)
    return f"{secret[:visible]}…"


class Spinner:
    """Terminal spinner with tty detection and CJK-safe line erasing."""

    def __init__(self, msg: str):
        self.msg = msg
        self.running = False
        self.thread: Optional[threading.Thread] = None
        # CJK characters are double-width, so clearing by character count
        # never fully erases the line; use ANSI \x1b[K instead, and skip
        # animation entirely when stdout is not a terminal (pipes/logs).
        self.tty = bool(sys.stdout.isatty())

    def _spin(self) -> None:
        """Animation loop; skipped entirely when stdout is not a tty."""
        if not self.tty:
            return
        frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        i = 0
        while self.running:
            sys.stdout.write(f"\r  {CYAN}{frames[i % len(frames)]}{RESET} {self.msg}")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1

    def start(self) -> None:
        """Start the spinner thread."""
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()

    def stop(self, success: bool = True) -> None:
        """Stop the spinner, erase the line with ANSI \x1b[K, print the final status."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.3)
        if self.tty:
            sys.stdout.write("\r\x1b[K")
            sys.stdout.flush()
        if success:
            ok(self.msg)
        else:
            warn(f"{self.msg} (失败)")


def enable_windows_ansi() -> None:
    """Enable VT100/ANSI escape processing on legacy Windows consoles."""
    if not IS_WINDOWS:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0007)
    except Exception:
        pass


def backup_file(path: Path) -> Optional[Path]:
    """Copy path to ~/.tokenplan-backups with a timestamp and append to manifest.jsonl."""
    if not path.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BACKUP_DIR / f"{path.name}.{ts}.bak"
    shutil.copy2(path, backup)
    # 备份常含 API Key:无论源文件权限如何,一律收紧为仅属主可读写
    try:
        backup.chmod(0o600)
    except OSError:
        pass
    manifest = BACKUP_DIR / "manifest.jsonl"
    entry = {"backup": backup.name, "original": str(path), "ts": ts}
    with manifest.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return backup


STATE_PATH = BACKUP_DIR / "state.json"


def load_state() -> Dict[str, list]:
    """Load the side-effect ledger (rc blocks, env files, setx keys) for uninstall."""
    if STATE_PATH.exists():
        try:
            data = json.loads(STATE_PATH.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {"rc_blocks": [], "setx_keys": [], "files_written": [], "env_files": []}


def save_state(state: Dict[str, list]) -> None:
    """Persist the side-effect ledger to state.json."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2) + "\n"
    )


def record_state(kind: str, value: object) -> None:
    """Track a side effect so `uninstall` can revert it precisely."""
    state = load_state()
    bucket = state.setdefault(kind, [])
    if value not in bucket:
        bucket.append(value)
    save_state(state)


def cfg_path(*parts: str) -> Path:
    """Resolve a path under HOME (creating parent dirs) for config files."""
    p = _sync_run_context().home.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _harden(path: Path) -> None:
    """Owner-only permissions for files that carry API keys."""
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _merge_model_lists(
    existing: List[object], incoming: List[object], merge_key: str
) -> List[object]:
    """Merge two lists by identity key: user entries kept, ours replaced/appended."""
    ours_keys = {
        str(entry.get(merge_key))
        for entry in incoming
        if isinstance(entry, dict)
    }
    kept = [
        entry
        for entry in existing
        if not (isinstance(entry, dict) and str(entry.get(merge_key)) in ours_keys)
    ]
    return kept + list(incoming)


def _deep_merge_dicts(
    existing: Dict[str, object],
    incoming: Dict[str, object],
    merge_key: Optional[str],
) -> Dict[str, object]:
    """递归深合并:dict 逐键下钻;双方均为 list 且给了 merge_key 时按标识
    合并(保留用户条目,仅替换/追加我方条目);其余类型以新值覆盖。

    (修复 2.4.0 及之前 existing.update() 的顶层浅合并——它会把用户
    opencode/openclaw/claude 配置里同级的其它 provider 整块顶掉。)
    """
    result: Dict[str, object] = dict(existing)
    for key, value in incoming.items():
        old = result.get(key)
        if isinstance(old, dict) and isinstance(value, dict):
            result[key] = _deep_merge_dicts(old, value, merge_key)
        elif merge_key and isinstance(old, list) and isinstance(value, list):
            result[key] = _merge_model_lists(old, value, merge_key)
        else:
            result[key] = value
    return result


def write_json(
    path: Path,
    data: object,
    merge: bool = False,
    merge_key: Optional[str] = None,
) -> None:
    """Backup then write JSON; hardens to 0o600.

    merge=True with dicts deep-merges (dicts recurse per-key; nested lists
    merge by merge_key when provided, else replace).
    merge=True with lists and merge_key set keeps user entries and
    replaces only entries whose merge_key matches ours (list order:
    user's non-conflicting entries first, then ours).
    """
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if merge and path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            existing = None
        if isinstance(existing, dict) and isinstance(data, dict):
            data = _deep_merge_dicts(existing, data, merge_key)
        elif (
            isinstance(existing, list)
            and isinstance(data, list)
            and merge_key
        ):
            data = _merge_model_lists(existing, data, merge_key)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _harden(path)


def write_env(
    path: Path, remove_keys: Iterable[str] = (), export: bool = False, **kv: str
) -> None:
    """Backup then rewrite a dotenv file, replacing only managed keys. Hardens to 0o600.

    export=True writes `export KEY=VALUE` lines for files that are `source`d
    from shell rc files (vars must be exported to reach child processes).
    User's own unmanaged lines are preserved verbatim.
    """
    backup_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    old_lines = path.read_text().splitlines() if path.exists() else []

    def _is_managed(line: str, keys: set) -> bool:
        stripped = line
        if stripped.startswith("export "):
            stripped = stripped[len("export "):]
        return any(stripped.startswith(f"{key}=") for key in keys)

    managed_keys = set(kv) | set(remove_keys)
    keep_lines = [line for line in old_lines if not _is_managed(line, managed_keys)]
    prefix = "export " if export else ""
    for key, value in kv.items():
        keep_lines.append(f"{prefix}{key}={value}")
    path.write_text("\n".join(line for line in keep_lines if line.strip()) + "\n")
    _harden(path)


def run_command(command: Union[Tuple[str, ...], str], message: str) -> bool:
    """Run an install command, streaming output; returns success."""
    print(f"  {CYAN}→{RESET} {message}")
    print()
    # Windows: npm/code etc. are .cmd shims that CreateProcess cannot launch
    # directly without a shell; resolve and reroute through the string branch.
    if isinstance(command, tuple) and IS_WINDOWS:
        exe = shutil.which(command[0])
        if exe and exe.lower().endswith((".cmd", ".bat")):
            command = subprocess.list2cmdline(command)
    try:
        if isinstance(command, tuple):
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        elif IS_WINDOWS:
            proc = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        else:
            proc = subprocess.Popen(
                command,
                shell=True,
                executable="/bin/bash",
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        assert proc.stdout is not None
        # 看门狗:到点 kill 进程,让阻塞中的 readline 以 EOF 退出。
        # (按行检查对无输出的静默进程无效——readline 永远等不到第一行。)
        state = {"timed_out": False}

        def _kill_on_timeout() -> None:
            state["timed_out"] = True
            try:
                proc.kill()
            except OSError:
                pass

        watchdog = threading.Timer(INSTALL_TIMEOUT, _kill_on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            for line in proc.stdout:
                line = line.rstrip()
                if line:
                    print(f"     {WHITE}{line}{RESET}")
            proc.wait()
        finally:
            watchdog.cancel()
        if state["timed_out"]:
            print()
            warn(f"{message} — 超时(超过 {INSTALL_TIMEOUT // 60} 分钟,已终止)")
            warn("网络可能受限;可用 --tools 跳过该工具,或先手动安装后重跑")
            return False
        print()
        if proc.returncode == 0:
            ok(f"{message} — 完成")
            return True
        warn(f"{message} — 失败")
        return False
    except Exception as exc:
        warn(f"{message} — 失败: {exc}")
        return False


def _http_request(
    url: str,
    *,
    method: str = "GET",
    api_key: Optional[str] = None,
    payload: Optional[Dict[str, object]] = None,
    user_agent: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> Tuple[int, bytes]:
    """所有出站 HTTP 的唯一入口(对齐 thcli core/http-agent.ts 的教训:
    连接配置收敛到一处,避免各调用点自行拼装导致行为漂移——thcli 曾因
    三处客户端漏传配置踩过 EPROTO)。

    Returns (status, body):status 0 = 成功(body 已读全),否则为 HTTP
    错误码;网络层失败抛 RuntimeError(带原因,提示口径由调用方决定)。
    """
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if user_agent:
        headers["User-Agent"] = user_agent
    data = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(payload).encode()
        method = "POST"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 0, resp.read()
    except urllib.error.HTTPError as exc:
        body = exc.read() if exc.fp else b""
        return exc.code, body
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _format_http_error(body: str, limit: int = 160) -> str:
    """Format a remote-script HTTP error without depending on adapter helpers."""
    message = body.strip()
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = str(error.get("message") or message)
    except ValueError:
        pass
    return message if len(message) <= limit else message[: limit - 1].rstrip() + "…"


def run_remote_script(url: str, script_args: Tuple[str, ...], tool_name: str) -> bool:
    """下载远程安装脚本 → 展示来源与 SHA256 → 确认 → 本地执行。

    (取代 `curl | bash` 盲管道:先完整落盘再执行,杜绝"边下边执行";
    展示指纹供人工核对;非交互环境一律拒绝——thcli 的 fail-closed 口径。
    上游官方脚本未发布固定哈希,无法做下载前校验,这里是该约束下
    能做到的最大化。)
    """
    print(f"  {CYAN}→{RESET} 下载远程安装脚本: {url}")
    try:
        status, body = _http_request(
            url, user_agent=f"tokenplan-setup/{VERSION}", timeout=60
        )
    except RuntimeError as exc:
        warn(f"下载失败: {exc}")
        return False
    if status != 0:
        warn(f"下载失败: HTTP {status}: {_format_http_error(body.decode(errors='ignore'))}")
        return False
    digest = hashlib.sha256(body).hexdigest()
    fd, tmp_name = tempfile.mkstemp(suffix="-tokenplan-install.sh")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
        os.chmod(tmp_name, 0o700)
        dim(f"来源: {url}")
        dim(f"SHA256: {digest}")
        dim(f"大小: {len(body)} 字节")
        if not _ASSUME_YES:
            warn("即将以当前用户身份执行该第三方脚本,请核对来源与哈希")
            try:
                confirmed = ask("  确认执行? (y/n): ").strip().lower()
            except EOFError:
                confirmed = "n"
            if confirmed not in ("y", "yes"):
                warn(f"已跳过 {tool_name}(远程脚本未获确认)")
                return False
        command = ("bash", tmp_name, *script_args)
        # 留痕:上游未发布固定哈希,事前校验做不到,但"这台机器上到底执行过
        # 哪份第三方脚本"必须可事后审计。记录在执行前落账,确保即使脚本
        # 中途失败也留有指纹。
        record_state("remote_scripts", {
            "tool": tool_name,
            "url": url,
            "sha256": digest,
            "bytes": len(body),
        })
        return run_command(command, f"正在安装 {tool_name}(远程脚本)...")
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)


# Internal helpers remain importable across package boundaries. The standalone
# bundler removes those imports and preserves the historical flat namespace.
__all__ = [name for name in globals() if not name.startswith("__")]
