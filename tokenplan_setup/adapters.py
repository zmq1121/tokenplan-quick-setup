"""Tool installation and configuration adapters."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Union

from tokenplan_setup.domain import (
    BACKEND_REGISTRY,
    CLAUDE_MODEL_SLOTS,
    MODEL_CATALOG,
    SYSTEM_DEPENDENCY_REGISTRY,
    TOOL_DEPENDENCY_REGISTRY,
    PlanSpec,
    ToolSpec,
)
from tokenplan_setup.infrastructure import (
    BRAND_LEGACY_KEYS,
    BRAND_NAME,
    BRAND_SLUG,
    BRAND_VENDOR,
    HOME,
    IS_WINDOWS,
    VERSION,
    Spinner,
    _harden,
    _http_request,
    ask,
    backup_file,
    cfg_path,
    dim,
    info,
    mask_secret,
    ok,
    record_state,
    run_command,
    run_remote_script,
    warn,
    write_env,
    write_json,
)


def get_backend_adapter(tool: ToolSpec) -> Dict[str, object]:
    """Look up the backend adapter config, defaulting to a generic one."""
    return BACKEND_REGISTRY.get(tool.backend, {
        "label": tool.backend,
        "auto_install": False,
        "manual_download": False,
        "requires": (),
        "usage_template": (),
    })


def get_npm_prefix_dir() -> Optional[Path]:
    """Return the npm global prefix directory, or None if unavailable."""
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        prefix = subprocess.check_output(
            [npm, "config", "get", "prefix"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not prefix or prefix in {"null", "undefined"}:
        return None
    return Path(prefix)


def query_windows_user_env(key: str) -> Optional[str]:
    """Best-effort read of a current-user env var from the registry."""
    try:
        result = subprocess.run(
            ["reg", "query", "HKCU\\Environment", "/v", key],
            capture_output=True, text=True, check=False,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if key in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        return " ".join(parts[2:])
    except (OSError, ValueError):
        pass
    return None


def install_codebuddy_shell_env(api_key: str, base_url: str) -> None:
    """Provide CodeBuddy Code's documented API-key authentication path."""
    if IS_WINDOWS:
        for key, value in (
            ("CODEBUDDY_API_KEY", api_key),
            ("OPENAI_API_KEY", api_key),
            ("OPENAI_BASE_URL", base_url),
        ):
            old_value = query_windows_user_env(key)
            record_state("setx_keys", {"key": key, "old": old_value})
            os.environ[key] = value
            subprocess.run(["setx", key, value], capture_output=True, check=False)
        info("已写入 Windows 用户环境变量，重新打开终端后生效")
        return
    env_path = cfg_path(".codebuddy", "tokenplan.env")
    write_env(
        env_path,
        export=True,
        CODEBUDDY_API_KEY=api_key,
        OPENAI_API_KEY=api_key,
        OPENAI_BASE_URL=base_url,
    )
    record_state("env_files", str(env_path))
    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan CodeBuddy Code API-key authentication"
    existing = rc_path.read_text() if rc_path.exists() else ""
    source_line = f'[ -f "{env_path}" ] && source "{env_path}"'
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(existing.rstrip() + f"\n{marker}\n{source_line}\n")
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    os.environ["CODEBUDDY_API_KEY"] = api_key
    os.environ["OPENAI_API_KEY"] = api_key
    os.environ["OPENAI_BASE_URL"] = base_url


def install_claude_tokenhub_path() -> None:
    """Expose the full TokenHub model selector in future shells."""
    launcher_dir = cfg_path(".local", "bin")
    launcher_dir.mkdir(parents=True, exist_ok=True)
    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    # marker 文案保持不变:换词会让升级用户得到重复的 PATH 块
    marker = "# Token Plan Claude model selector"
    existing = rc_path.read_text() if rc_path.exists() else ""
    path_line = f'export PATH="{launcher_dir}:$PATH"'
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(existing.rstrip() + f"\n{marker}\n{path_line}\n")
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    record_state("files_written", str(launcher_dir / "claude-tokenhub"))
    current_path = os.environ.get("PATH", "")
    if str(launcher_dir) not in current_path.split(":"):
        os.environ["PATH"] = f"{launcher_dir}:{current_path}"


def _claude_tokenhub_cmd(model_ids: List[str]) -> str:
    """Render a Windows batch launcher for the TokenHub model selector."""
    models = " ".join(model_ids)
    lines = [
        "@echo off",
        "chcp 65001 >nul",
        "setlocal enabledelayedexpansion",
        f"set MODELS={models}",
        f"echo {BRAND_NAME} models:",
        "set /a IDX=0",
        "for %%M in (%MODELS%) do (",
        "  set /a IDX+=1",
        "  echo   !IDX!. %%M",
        ")",
        "set /p CHOICE=Select number or type full model ID: ",
        "set MODEL=",
        "set /a IDX=0",
        "for %%M in (%MODELS%) do (",
        "  set /a IDX+=1",
        '  if "!CHOICE!"=="!IDX!" set MODEL=%%M',
        ")",
        "if not defined MODEL set MODEL=%CHOICE%",
        'if "%MODEL%"=="" (',
        "  echo Invalid selection",
        "  endlocal & exit /b 1",
        ")",
        "endlocal & claude --model %MODEL% %*",
    ]
    return "\r\n".join(lines) + "\r\n"


def install_claude_tokenhub_launcher_win(model_ids: List[str]) -> None:
    """Write claude-tokenhub.cmd into the npm global dir (already on PATH)."""
    prefix = get_npm_prefix_dir()
    target_dir = prefix if prefix and prefix.is_dir() else cfg_path(".local", "bin")
    target_dir.mkdir(parents=True, exist_ok=True)
    launcher = target_dir / "claude-tokenhub.cmd"
    launcher.write_text(_claude_tokenhub_cmd(model_ids), encoding="utf-8")
    record_state("files_written", str(launcher))
    # 2.5.x 的旧启动器一并清掉,避免两套命令并存
    legacy = target_dir / "claude-tokenplan.cmd"
    if legacy.exists():
        try:
            legacy.unlink()
        except OSError:
            pass
    if prefix:
        info(f"已写入模型选择器: {launcher}")
    else:
        warn(f"未检测到 npm 全局目录，请手动将该目录加入 PATH: {target_dir}")


def ensure_npm_bin_on_path() -> None:
    """Make globally installed npm CLI commands available in future shells."""
    prefix = get_npm_prefix_dir()
    if not prefix:
        return

    if IS_WINDOWS:
        # Windows npm shims (.cmd) live in the prefix root itself.
        path_value = str(prefix)
        current_path = os.environ.get("PATH", "")
        parts = [p for p in current_path.split(";") if p]
        if path_value.lower() not in [p.lower() for p in parts]:
            os.environ["PATH"] = f"{path_value};{current_path}"
        return

    npm_bin = prefix / "bin"
    if not npm_bin.is_dir():
        return

    path_value = str(npm_bin)
    current_path = os.environ.get("PATH", "")
    if path_value not in current_path.split(":"):
        os.environ["PATH"] = f"{path_value}:{current_path}"

    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan npm global CLI path"
    existing = rc_path.read_text() if rc_path.exists() else ""
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        block = f'\n{marker}\nexport PATH="{npm_bin}:$PATH"\n'
        rc_path.write_text(existing.rstrip() + block)
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    info(f"npm 全局命令路径已加入: {npm_bin}")


def is_tool_installed(tool: ToolSpec) -> bool:
    """Detect installation via executable on PATH."""
    return bool(tool.check_exe and shutil.which(tool.check_exe))


def requires_backend_dependency(tool: ToolSpec, dependency: str) -> bool:
    """True if the backend adapter or TOOL_DEPENDENCY_REGISTRY requires it."""
    adapter = get_backend_adapter(tool)
    requires = adapter.get("requires", ())
    if isinstance(requires, (list, tuple, set)) and dependency in requires:
        return True
    return dependency in TOOL_DEPENDENCY_REGISTRY.get(tool.key, ())


def system_dependency_available(dependency: str) -> bool:
    """Check one dependency using SYSTEM_DEPENDENCY_REGISTRY command aliases."""
    if dependency == "python":
        return sys.version_info.major >= 3
    spec = SYSTEM_DEPENDENCY_REGISTRY[dependency]
    commands = spec["commands"]
    if not isinstance(commands, (list, tuple)):
        return False
    return any(shutil.which(str(command)) for command in commands)


def get_install_command(tool: ToolSpec) -> Optional[Union[Tuple[str, ...], str]]:
    """Return the install command for the current platform.

    Windows prefers an explicit install_cmd_win when present; otherwise it
    falls back to install_cmd only when that command is platform-neutral
    (e.g. npm tuples), never for bash/curl pipelines.
    """
    if IS_WINDOWS:
        if tool.install_cmd_win is not None:
            return tool.install_cmd_win
        cmd = tool.install_cmd
        if isinstance(cmd, tuple) and cmd and cmd[0] not in {"bash", "sh"}:
            return cmd
        return None
    return tool.install_cmd


def should_manual_download(tool: ToolSpec) -> bool:
    """True when the user must fetch the app manually (platform or backend)."""
    if IS_WINDOWS and tool.win_manual:
        return True
    return bool(get_backend_adapter(tool).get("manual_download"))


def supports_auto_install(tool: ToolSpec) -> bool:
    """True when the backend allows auto-install and an install path exists."""
    adapter = get_backend_adapter(tool)
    has_path = bool(get_install_command(tool)) or bool(
        tool.install_script and not IS_WINDOWS
    )
    return bool(adapter.get("auto_install")) and has_path


def install_tool(tool: ToolSpec) -> bool:
    """Install a tool: remote scripts download-then-confirm; npm gets a private cache."""
    if tool.install_script and not IS_WINDOWS and not should_manual_download(tool):
        return run_remote_script(tool.install_script, tool.install_script_args, tool.name)
    command = get_install_command(tool)
    if not command:
        return True
    if should_manual_download(tool):
        return False
    if isinstance(command, tuple) and command and command[0] == "npm":
        npm_cache = cfg_path(".tokenplan-npm-cache")
        npm_cache.mkdir(parents=True, exist_ok=True)
        command = (*command, "--cache", str(npm_cache))
    return run_command(command, f"正在安装 {tool.name}...")


def render_usage_lines(tool: ToolSpec, base_url: str, api_key: str) -> List[str]:
    """Render backend template + tool usage_lines, filling base_url/api_key placeholders."""
    rendered: List[str] = []
    adapter = get_backend_adapter(tool)
    template_lines = adapter.get("usage_template", ())
    if not isinstance(template_lines, (list, tuple)):
        template_lines = ()
    for line in template_lines:
        if not isinstance(line, str):
            continue
        rendered.append(
            line.format(
                name=tool.name,
                base_url=base_url,
                api_key_mask=mask_secret(api_key),
                start_hint=tool.start_hint,
                cfg_hint=tool.cfg_hint,
            )
        )
    for line in tool.usage_lines:
        rendered.append(line.format(base_url=base_url, api_key_mask=mask_secret(api_key)))
    return rendered


def check_prerequisites(selected_tools: Iterable[ToolSpec]) -> bool:
    """Check OS/Node/npm/npx/code for the selected tools; returns readiness."""
    print("  ── 前置检查 ──")
    print()

    if sys.platform == "darwin":
        architecture = os.uname().machine
        macos_version = "未知"
        try:
            macos_version = subprocess.check_output(
                ["sw_vers", "-productVersion"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (OSError, subprocess.SubprocessError):
            pass
        ok(f"macOS {macos_version} ({architecture})")
        if architecture not in {"arm64", "x86_64"}:
            warn(f"未验证的 Mac 架构: {architecture}")
    elif IS_WINDOWS:
        try:
            win_ver = sys.getwindowsversion()  # type: ignore[attr-defined]
            info(f"Windows {win_ver.major}.{win_ver.minor} (build {win_ver.build})")
        except AttributeError:
            info("Windows")
    else:
        info(f"当前平台: {sys.platform}")

    needs_node = any(
        tool.backend == "cli"
        and get_install_command(tool)
        and any("npm" in part or "npx" in part for part in (get_install_command(tool) or ("",)))
        for tool in selected_tools
    )
    needs_bash = not IS_WINDOWS and any(
        tool.install_script and not should_manual_download(tool)
        for tool in selected_tools
    )
    prerequisites_ready = True
    if system_dependency_available("python"):
        ok("Python 3")
    else:
        prerequisites_ready = False
        warn("需要 Python 3")

    if needs_bash:
        if system_dependency_available("bash"):
            ok("bash")
        else:
            prerequisites_ready = False
            warn("未安装 bash，Hermes/OpenClaw 远程安装脚本无法执行")

    if needs_node:
        node_ok = system_dependency_available("node")
        npm_ok = system_dependency_available("npm")
        npx_ok = system_dependency_available("npx")
        if node_ok:
            ok("Node.js")
        else:
            warn("未安装 Node.js，依赖 npm/npx 的工具可能无法安装或运行")
            info("安装地址: https://nodejs.org/en/download")
            info("Windows 也可使用: winget install OpenJS.NodeJS.LTS")
            info("macOS 也可使用: brew install node")
            info("Ubuntu/Debian 也可使用: sudo apt install nodejs npm")
            info("如果您没有安装权限，请联系企业 IT 管理员")
        if npm_ok:
            ok("npm")
        else:
            warn("未安装 npm，Node 工具安装可能失败")
        if npx_ok:
            ok("npx")
        else:
            npx_tools = [t.name for t in selected_tools if requires_backend_dependency(t, "npx")]
            if npx_tools:
                warn(f"未安装 npx，{('、'.join(npx_tools))} 将无法启动")
        if not node_ok or not npm_ok:
            prerequisites_ready = False
            warn("当前环境缺少 Node 依赖，所选 Node 工具无法安装")
            info("请安装 Node.js LTS 后重新运行本安装器")
            if sys.platform == "darwin":
                info("推荐地址: https://nodejs.org/en/download")

    if shutil.which("git"):
        ok("git")

    print()
    return prerequisites_ready


# 远程模型目录:优先于内置 MODEL_CATALOG,由 refresh_remote_catalog() 填充。
# 仓库根目录的 models.json 通过 jsDelivr CDN 分发,更新模型只需提交一次 JSON;
# models.json.sha256 由 scripts/sync_npm_lib.py 自动再生,二者必须一起提交
# (tests 的 consistency 组会校验一致,防止"改了目录忘了刷哈希")。
# VERSION maps to the immutable release tag used by setup.bat. The catalog and
# its digest must always come from the same tag; never follow mutable @main.
REMOTE_CATALOG_URL = (
    f"https://cdn.jsdelivr.net/gh/zmq1121/tokenplan-quick-setup@v{VERSION}/models.json"
)
REMOTE_CATALOG_SHA256_URL = REMOTE_CATALOG_URL + ".sha256"
_REMOTE_CATALOG: Optional[Dict[str, Dict[str, object]]] = None
_REMOTE_LATEST_VERSION: Optional[str] = None


def remote_catalog_size() -> int:
    """Return the number of display rows in the active remote catalog."""
    if not _REMOTE_CATALOG:
        return 0
    return sum(len(_catalog_display(plan)) for plan in _REMOTE_CATALOG.values())


def _parse_sha256(text: str) -> Optional[str]:
    """Extract the first 64-hex digest from a .sha256 file body (sha256sum format)."""
    match = re.search(r"\b[0-9a-fA-F]{64}\b", text)
    return match.group(0).lower() if match else None


def refresh_remote_catalog() -> None:
    """Fetch the remote model catalog with SHA256 integrity verification.

    (对齐 thcli skills 分发的纪律:清单与内容分离,哈希对不上就不用。
    .sha256 拿不到或不匹配 → 一律回退内置目录,绝不下发无法证明
    完整性的远程内容——CDN 缓存错位与劫持同归此路径。)
    """
    global _REMOTE_CATALOG, _REMOTE_LATEST_VERSION
    try:
        status, body = _http_request(
            REMOTE_CATALOG_URL, user_agent=f"tokenplan-setup/{VERSION}"
        )
        if status != 0:
            return
        digest_status, digest_body = _http_request(
            REMOTE_CATALOG_SHA256_URL, user_agent=f"tokenplan-setup/{VERSION}"
        )
        if digest_status != 0:
            warn("远程目录完整性无法校验(获取 models.json.sha256 失败),已回退内置目录")
            return
        expected = _parse_sha256(digest_body.decode(errors="ignore"))
        actual = hashlib.sha256(body).hexdigest()
        if expected is None or expected != actual:
            warn("远程目录 SHA256 不匹配(疑似 CDN 缓存错位或内容异常),已回退内置目录")
            return
        payload = json.loads(body.decode(errors="ignore"))
        plans = payload.get("plans") if isinstance(payload, dict) else None
        if isinstance(plans, dict) and plans:
            _REMOTE_CATALOG = plans
        latest = payload.get("latest_version") if isinstance(payload, dict) else None
        if isinstance(latest, str) and latest:
            _REMOTE_LATEST_VERSION = latest
    except Exception:
        # 内容已通过哈希校验却仍解析失败,说明上游产物本身异常,必须让用户看见。
        warn("远程目录内容解析失败,已回退内置目录")


def _version_tuple(version: str) -> Tuple[int, ...]:
    """Parse '1.2.3' into (1, 2, 3); non-numeric parts are ignored."""
    parts = []
    for chunk in version.split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            break
    return tuple(parts) or (0,)


def notify_upgrade_available() -> None:
    """Old distributed files learn about new releases via the remote catalog."""
    if not _REMOTE_LATEST_VERSION:
        return
    if _version_tuple(VERSION) >= _version_tuple(_REMOTE_LATEST_VERSION):
        return
    dim(f"发现新版本: 当前 v{VERSION},最新 v{_REMOTE_LATEST_VERSION}")
    dim("建议重新获取安装文件,或使用: npx tokenplan-setup@latest")


# 后付费:运行时通过 /v3/models 发现的模型列表(verify 阶段填充)
_POSTPAID_DISCOVERED: Optional[List[str]] = None

# 后付费默认模型的挑选优先级(基于 tokenhub /v1/models 实测列表)
_POSTPAID_PREFERRED = ("glm-5.3", "glm-5.3-flash", "deepseek-v4-pro", "hy4-preview")

# 后付费非聊天能力排除(视频/图像/语音/embedding/音乐/翻译/3D 等;
# 命中的模型不写入聊天类工具,避免淹没模型下拉框)
_POSTPAID_EXCLUDE = re.compile(
    r"video|image|embed|tts|speech|asr|whisper|rerank|dubbing|3d|mt2|-mt-|actor|"
    r"-as-fast|voice|speak|listen|txt2img|caption|ocr|seedream|pixverse|vidu|"
    r"kling|tripo|wand|youtu-vita|hi3d|hy-mt|music|world2|tokenhub-",
    re.I,
)


def discover_postpaid_models(base_url: str, api_key: str) -> Optional[List[str]]:
    """Fetch the live model list from the postpaid /models endpoint.

    Also serves as key verification for the postpaid plan: a 200 with a
    model list means the key is valid. Returns None on any failure.
    """
    global _POSTPAID_DISCOVERED
    try:
        status, body = _http_request(
            f"{base_url}/models", api_key=api_key, method="GET"
        )
        if status != 0:
            warn(f"API 返回错误 [{status}]: {_format_api_error(body.decode(errors='ignore')[:400])}")
            return None
        payload = json.loads(body.decode(errors="ignore"))
        data = payload.get("data") if isinstance(payload, dict) else None
        ids = [
            item["id"]
            for item in (data or [])
            if isinstance(item, dict) and item.get("id")
        ]
        if ids:
            _POSTPAID_DISCOVERED = ids
            return ids
    except RuntimeError as exc:
        warn(f"连接失败: {exc}")
    except Exception as exc:
        warn(f"解析失败: {exc}")
    return None


# 后付费:用户自选的模型子集(None = 全部聊天模型)
_POSTPAID_SELECTED: Optional[List[str]] = None


def postpaid_discovered_count() -> int:
    """Return the current live postpaid model count."""
    return len(_POSTPAID_DISCOVERED or ())


def postpaid_chat_models() -> List[str]:
    """Discovered postpaid models filtered to chat capability (raw fallback)."""
    assert _POSTPAID_DISCOVERED is not None
    chat = [m for m in _POSTPAID_DISCOVERED if not _POSTPAID_EXCLUDE.search(m)]
    return chat or list(_POSTPAID_DISCOVERED)


def set_postpaid_selection(models: List[str]) -> List[str]:
    """Restrict the postpaid catalog to a user-chosen subset (validated)."""
    global _POSTPAID_SELECTED
    chat = postpaid_chat_models()
    chosen = [m for m in chat if m in models]  # 保持发现顺序
    if not chosen:
        warn("所选模型均不在发现列表中,保持全部")
        return chat
    dropped = [m for m in models if m not in chat]
    if dropped:
        warn(f"忽略未知模型: {', '.join(dropped)}")
    _POSTPAID_SELECTED = chosen
    return chosen


def choose_postpaid_models() -> None:
    """Interactive model selection for postpaid; Enter/EOF = all chat models."""
    chat = postpaid_chat_models()
    print()
    print("  ── 选择要配置的模型 ──")
    print()
    print("  直接回车 = 全部聊天模型;输入编号(空格/逗号分隔)只配置所选")
    print()
    for i, m in enumerate(chat, 1):
        print(f"     [{i:2d}] {m}")
    print()
    try:
        raw = ask("编号(回车=全部): ")
    except EOFError:
        return
    tokens = [t for t in re.split(r"[\s,，]+", raw) if t]
    if not tokens or raw in {"all", "*", "全部"}:
        return
    picked: List[str] = []
    for tok in tokens:
        if tok.isdigit():
            idx = int(tok)
            if 1 <= idx <= len(chat):
                picked.append(chat[idx - 1])
                continue
        hit = next((m for m in chat if tok == m), None)
        if hit:
            picked.append(hit)
    if picked:
        global _POSTPAID_SELECTED
        _POSTPAID_SELECTED = picked
        ok(f"已选择 {len(picked)} 个模型")


def _postpaid_catalog() -> Optional[Dict[str, object]]:
    """Build a catalog view from the discovered postpaid models (chat-capable only)."""
    if not _POSTPAID_DISCOVERED:
        return None
    if _POSTPAID_SELECTED:
        ids = list(_POSTPAID_SELECTED)
    else:
        ids = postpaid_chat_models()
    preferred = next((m for m in _POSTPAID_PREFERRED if m in ids), ids[0])
    return {
        "default": preferred,
        "display": tuple(f"{mid}: {mid}" for mid in ids),
    }


def get_model_catalog(plan_key: str) -> Dict[str, object]:
    """Remote catalog first (when refreshed), built-in MODEL_CATALOG as fallback.

    Postpaid is special: its model list is discovered live from the API
    (dynamic catalog, no built-in curation); discovery result wins.
    """
    if plan_key in ("postpaid", "postpaid-intl"):
        discovered = _postpaid_catalog()
        if discovered:
            return discovered
        return {"default": "", "display": ()}
    remote = (_REMOTE_CATALOG or {}).get(plan_key)
    if isinstance(remote, dict) and remote.get("default") and remote.get("display"):
        return remote
    return dict(MODEL_CATALOG.get(plan_key, {"default": "auto", "display": ()}))


def _catalog_display(catalog: Dict[str, object]) -> Tuple[str, ...]:
    """Return validated display rows from a loosely typed catalog payload."""
    display = catalog.get("display", ())
    if not isinstance(display, (list, tuple)):
        return ()
    return tuple(line for line in display if isinstance(line, str))


def get_model_ids(plan_key: str) -> List[str]:
    """Return the canonical model IDs shared by every tool adapter."""
    catalog = get_model_catalog(plan_key)
    result: List[str] = []
    for line in _catalog_display(catalog):
        if ":" not in line:
            continue
        model_id = line.split(":", 1)[1].strip().split(" ", 1)[0]
        if model_id and model_id not in result:
            result.append(model_id)
    return result


def _format_api_error(body: str, limit: int = 160) -> str:
    """Humanize an API error body: prefer the JSON message field, truncate cleanly."""
    msg = body.strip()
    try:
        payload = json.loads(body)
        if isinstance(payload, dict):
            err = payload.get("error")
            if isinstance(err, dict):
                msg = str(err.get("message") or msg)
                code = err.get("code")
                if code:
                    msg = f"[{code}] {msg}"
    except ValueError:
        pass
    if len(msg) > limit:
        msg = msg[: limit - 1].rstrip() + "…"
    return msg


def verify_api_key(base_url: str, api_key: str, plan: PlanSpec) -> bool:
    """Probe the endpoint with a 1-token chat completion using the plan's default model."""
    if plan.key in ("postpaid", "postpaid-intl"):
        # 后付费:GET /models 即验证(200+列表 = Key 有效),同时完成模型发现
        spinner = Spinner("验证 API Key 并发现模型...")
        spinner.start()
        ids = discover_postpaid_models(base_url, api_key)
        spinner.stop(success=ids is not None)
        if ids:
            ok(f"Key 有效,发现 {len(ids)} 个可用模型")
            return True
        warn("后付费 Key 验证失败或模型列表获取失败(需联网)")
        return False
    spinner = Spinner("验证 API Key...")
    spinner.start()
    try:
        status, body = _http_request(
            f"{base_url}/chat/completions",
            api_key=api_key,
            payload={
                "model": get_model_catalog(plan.key)["default"],
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            },
        )
        if status == 0:
            spinner.stop(success=True)
            return True
        spinner.stop(success=False)
        warn(f"API 返回错误 [{status}]: {_format_api_error(body.decode(errors='ignore')[:400])}")
        return False
    except RuntimeError as exc:
        spinner.stop(success=False)
        warn(f"连接失败: {exc}")
        return False


def configure_codebuddy(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.codebuddy/models.json (per-model provider entries)."""
    model_ids = get_model_ids(plan.key)
    default_model = str(get_model_catalog(plan.key)["default"])
    write_json(
        cfg_path(".codebuddy", "models.json"),
        {
            "models": [
                {
                    "id": model_id,
                    "name": model_id,
                    "vendor": BRAND_VENDOR,
                    "apiKey": api_key,
                    "url": base_url,
                }
                for model_id in model_ids
            ]
        },
        # 按模型 id 合并:保留用户自建条目(与 WorkBuddy 同一标准;
        # 此前全量重写会静默丢弃用户手填的模型)
        merge=True,
        merge_key="id",
    )
    write_json(
        cfg_path(".codebuddy", "settings.json"),
        {
            "env": {
                "CODEBUDDY_API_KEY": api_key,
                "OPENAI_API_KEY": api_key,
                "OPENAI_BASE_URL": base_url,
            },
            "model": default_model,
        },
        merge=True,
    )
    install_codebuddy_shell_env(api_key, base_url)


def configure_claude_code(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.claude/settings.json env block + model slots + tokenhub launcher."""
    if base_url.rstrip("/").endswith("/v1"):
        # 后付费(tokenhub /v1):Anthropic SDK 硬拼 /v1/messages,
        # base 必须写到域名根(不带 /v1),否则会请求 /v1/v1/messages → 404
        anthropic_url = base_url.rstrip("/")[: -len("/v1")]
    else:
        # 套餐版:官方文档规定 ANTHROPIC_BASE_URL = <host>/plan/anthropic
        # (SDK 拼接 /v1/messages 后即 <host>/plan/anthropic/v1/messages,已探活验证)
        anthropic_url = base_url.replace("/plan/v3", "/plan/anthropic")
    catalog = get_model_catalog(plan.key)
    default_model = str(catalog["default"])
    model_ids = get_model_ids(plan.key)
    claude_slots = CLAUDE_MODEL_SLOTS.get(plan.key, {})
    if not claude_slots and plan.key in ("postpaid", "postpaid-intl") and model_ids:
        # 后付费无固定槽位映射:从发现列表按能力倾向挑选
        def _pick(*keywords: str) -> str:
            for kw in keywords:
                hit = next((m for m in model_ids if m == kw), "")
                if not hit:
                    hit = next((m for m in model_ids if kw in m), "")
                if hit:
                    return hit
            return model_ids[0]
        claude_slots = {
            "opus": _pick("glm-5.3", "pro", "r1"),
            "sonnet": _pick("glm-5.3", "chat", "v3"),
            "haiku": _pick("flash", "lite", "turbo"),
        }
    env = {
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_BASE_URL": anthropic_url,
        "ANTHROPIC_MODEL": default_model,
        "CLAUDE_CODE_EFFORT_LEVEL": "high",
    }
    if claude_slots:
        env.update(
            {
                "ANTHROPIC_DEFAULT_OPUS_MODEL": claude_slots["opus"],
                "ANTHROPIC_DEFAULT_SONNET_MODEL": claude_slots["sonnet"],
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": claude_slots["haiku"],
            }
        )
    write_json(
        cfg_path(".claude", "settings.json"),
        {
            "env": env,
            "model": default_model,
            "alwaysThinkingEnabled": True,
            BRAND_SLUG: {
                "provider": "anthropic",
                "base_url": anthropic_url,
                "models": model_ids,
            },
        },
        merge=True,
    )
    # 摘除 2.5.x 的旧记账键(仅是安装器的记录块,不影响 Claude 读取)
    settings_path = cfg_path(".claude", "settings.json")
    settings_data = _read_json_object(settings_path)
    if any(k in settings_data for k in BRAND_LEGACY_KEYS):
        for legacy in BRAND_LEGACY_KEYS:
            settings_data.pop(legacy, None)
        settings_path.write_text(
            json.dumps(settings_data, indent=2, ensure_ascii=False) + "\n"
        )
    write_json(
        cfg_path(".claude", f"{BRAND_SLUG}-models.json"),
        {
            "provider": "anthropic",
            "base_url": anthropic_url,
            "models": model_ids,
            "default": default_model,
        },
    )
    # 2.5.x 的旧模型文件/旧启动器清理,避免用户看到两套
    legacy_models = cfg_path(".claude", "tokenplan-models.json")
    if legacy_models.exists():
        try:
            legacy_models.unlink()
        except OSError:
            pass
    legacy_launcher = cfg_path(".local", "bin", "claude-tokenplan")
    if legacy_launcher.exists():
        try:
            legacy_launcher.unlink()
        except OSError:
            pass
    if IS_WINDOWS:
        install_claude_tokenhub_launcher_win(model_ids)
        return
    install_claude_tokenhub_path()
    launcher = cfg_path(".local", "bin", "claude-tokenhub")
    launcher.write_text(
        "#!/bin/sh\n"
        f"models={' '.join(model_ids)!r}\n"
        f"printf '{BRAND_NAME} 模型列表:\\n'\n"
        "i=1; for model in $models; do printf '  %s. %s\\n' \"$i\" \"$model\"; i=$((i + 1)); done\n"
        "printf '请选择序号或输入完整模型 ID: '\n"
        "read -r choice\n"
        "case $choice in\n"
        "  ''|*[!0-9]*) model=$choice ;;\n"
        "  *) model=$(printf '%s\\n' $models | sed -n \"${choice}p\") ;;\n"
        "esac\n"
        "[ -n \"$model\" ] || { printf '无效选择\\n' >&2; exit 1; }\n"
        "CLAUDE_CODE_EFFORT_LEVEL=\"${CLAUDE_CODE_EFFORT_LEVEL:-high}\" exec claude --model \"$model\" \"$@\"\n"
    )
    launcher.chmod(0o755)


def patch_hermes_model_routing() -> None:
    """Patch Hermes' model_switch.py so custom providers resolve their own slug."""
    install_dir = HOME / ".hermes" / "hermes-agent"
    target = install_dir / "hermes_cli" / "model_switch.py"
    if not target.exists():
        warn("未找到 Hermes 模型切换文件，跳过兼容补丁")
        return
    source = target.read_text()
    old = '            slug = f"custom:{name}"\n            if slug in matches:\n'
    new = '            slug = custom_provider_slug(name, str(entry.get("provider_key") or ""))\n            if slug in matches:\n'
    if old in source:
        backup_file(target)
        target.write_text(source.replace(old, new, 1))
    info("Hermes 模型切换兼容已启用")


def configure_hermes(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.hermes/.env custom provider and patch model routing."""
    patch_hermes_model_routing()
    write_env(
        cfg_path(".hermes", ".env"),
        remove_keys=("TERMINAL_CWD",),
        OPENAI_API_KEY=api_key,
    )
    default_model = get_model_catalog(plan.key)["default"]
    models = tuple(get_model_ids(plan.key))
    config_path = cfg_path(".hermes", "config.yaml")
    backup_file(config_path)
    model_entries = ", ".join(
        f'"{model}": {{}}' for model in models
    )
    config_path.write_text(
        "model:\n"
        f"  default: {default_model}\n"
        f"  provider: {BRAND_SLUG}\n"
        f"  base_url: {base_url}\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "providers:\n"
        f"  {BRAND_SLUG}:\n"
        f"    name: {BRAND_NAME}\n"
        f"    api: {base_url}\n"
        "    api_key: ${OPENAI_API_KEY}\n"
        f"    default_model: {default_model}\n"
        "    discover_models: false\n"
        f"    models: {{{model_entries}}}\n"
    )
    info(f"Hermes 已配置为 {BRAND_NAME} custom 端点")
    info(f"当前产品线: {plan.display_name}")
    info(f"已写入模型数量: {len(models)}")
    info(f"默认模型: {default_model}")


def get_openai_compatible_default_model(plan_key: str) -> str:
    """Resolve 'auto' defaults to a concrete preferred model for tools that need one."""
    catalog = get_model_catalog(plan_key)
    default_model = str(catalog["default"])
    if default_model != "auto":
        return default_model
    model_ids = get_model_ids(plan_key)
    preferred_models = ("glm-5.2", "deepseek-v4-pro-202606", "hy3")
    return next(
        (model for model in preferred_models if model in model_ids),
        next((model for model in model_ids if model not in {"auto", "glm-5.3"}), default_model),
    )


def _purge_openclaw_legacy(config_path: Path) -> None:
    """摘除 2.5.x 旧品牌键(tencent-tokenplan provider 及 agents 里的模型引用)。"""
    data = _read_json_object(config_path)
    changed = False
    models = data.get("models")
    if isinstance(models, dict):
        providers = models.get("providers")
        if isinstance(providers, dict):
            for legacy in BRAND_LEGACY_KEYS:
                if legacy in providers:
                    providers.pop(legacy)
                    changed = True
    agents = data.get("agents")
    if isinstance(agents, dict):
        defaults = agents.get("defaults")
        if isinstance(defaults, dict):
            entries = defaults.get("models")
            if isinstance(entries, dict):
                stale = [
                    key for key in entries
                    if isinstance(key, str)
                    and any(key.startswith(f"{legacy}/") for legacy in BRAND_LEGACY_KEYS)
                ]
                for key in stale:
                    entries.pop(key)
                    changed = True
    if changed:
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def configure_openclaw(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.openclaw/openclaw.json provider and .env key."""
    model_ids = get_model_ids(plan.key)
    default_model = get_openai_compatible_default_model(plan.key)
    config_path = cfg_path(".openclaw", "openclaw.json")
    write_env(cfg_path(".openclaw", ".env"), TOKENPLAN_API_KEY=api_key)
    full_model_ids = [f"{BRAND_SLUG}/{model_id}" for model_id in model_ids]
    write_json(
        config_path,
        {
            "models": {
                "mode": "merge",
                "providers": {
                    BRAND_SLUG: {
                        "baseUrl": base_url,
                        "apiKey": "${TOKENPLAN_API_KEY}",
                        "api": "openai-completions",
                        "models": [
                            {
                                "id": model_id,
                                "name": model_id,
                                "reasoning": model_id not in {"auto"},
                            }
                            for model_id in model_ids
                        ],
                    }
                },
            },
            "agents": {
                "defaults": {
                    "model": {"primary": f"{BRAND_SLUG}/{default_model}"},
                    "models": {
                        full_model_id: {
                            "alias": full_model_id.split("/", 1)[1],
                            "agentRuntime": {"id": "openclaw"},
                        }
                        for full_model_id in full_model_ids
                    },
                }
            },
        },
        merge=True,
    )
    _purge_openclaw_legacy(config_path)
    info(f"OpenClaw 已写入 {BRAND_NAME} 自定义 Provider")


def configure_opencode(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.config/opencode/opencode.json provider entry."""
    model_ids = get_model_ids(plan.key)
    default_model = get_openai_compatible_default_model(plan.key)
    config_dir = cfg_path(".config", "opencode")
    config_path = config_dir / "opencode.json"
    write_json(
        config_path,
        {
            "$schema": "https://opencode.ai/config.json",
            "model": f"{BRAND_SLUG}/{default_model}",
            "provider": {
                BRAND_SLUG: {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": BRAND_VENDOR,
                    "options": {
                        "baseURL": base_url,
                        "apiKey": api_key,
                    },
                    "models": {
                        model_id: {"name": model_id}
                        for model_id in model_ids
                    },
                }
            },
        },
        merge=True,
    )
    # 摘除 2.5.x 的旧 provider 键,避免模型列表里出现两套来源
    data = _read_json_object(config_path)
    provider = data.get("provider")
    if isinstance(provider, dict) and any(k in provider for k in BRAND_LEGACY_KEYS):
        for legacy in BRAND_LEGACY_KEYS:
            provider.pop(legacy, None)
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    info(f"OpenCode 已写入 {BRAND_NAME} 自定义 Provider")


def _workbuddy_model_entry(
    model_id: str, plan: PlanSpec, base_url: str, api_key: str
) -> Dict[str, object]:
    """Build one WorkBuddy models.json entry (format reverse-engineered
    from a real user's hand-added entry; fields verified against it)."""
    catalog = get_model_catalog(plan.key)
    display = _catalog_display(catalog)
    # 显示名优先用目录里的友好名;找不到就裸 ID
    friendly = ""
    for line in display:
        if ":" in line and line.split(":", 1)[1].strip().split(" ")[0] == model_id:
            friendly = line.split(":", 1)[0].strip()
            break
    plan_short = plan.display_name.split(" - ")[-1].split("（")[0]
    # 多模态模型(如 deepseek-vision-exp)开图片;其余企业/个人模型按文本对话模型处理
    multimodal = "vision" in model_id.lower()
    return {
        "id": model_id,
        "name": f"{BRAND_NAME} {plan_short} / {friendly or model_id}",
        "vendor": BRAND_VENDOR,
        "url": f"{base_url}/chat/completions",
        "apiKey": api_key,
        "supportsToolCall": True,
        "supportsImages": multimodal,
        "supportsReasoning": True,
        "maxInputTokens": 1000000,
        "maxOutputTokens": 131072,
    }


def configure_workbuddy(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write all plan models into ~/.workbuddy/models.json in one shot.

    WorkBuddy's manual UI adds models one field-form at a time; this
    writes the whole plan catalog at once. User's own entries in the
    list are preserved (merge by id); if WorkBuddy is running we ask
    the user to quit first so it doesn't overwrite the file on exit.
    """
    try:
        running = any(
            proc
            for proc in ("WorkBuddy",)
            if shutil.which("pgrep") and subprocess.run(
                ["pgrep", "-f", proc], capture_output=True
            ).returncode == 0
        )
    except Exception:
        running = False
    if running:
        warn("检测到 WorkBuddy 正在运行;请先完全退出(菜单栏图标 → 退出)后重跑")
        warn("否则 WorkBuddy 退出时会用内存中的旧模型列表覆盖本次写入")
        raise RuntimeError("WorkBuddy 正在运行,请退出后重试")

    entries = [
        _workbuddy_model_entry(m, plan, base_url, api_key)
        for m in get_model_ids(plan.key)
    ]
    write_json(
        cfg_path(".workbuddy", "models.json"),
        entries,
        merge=True,
        merge_key="id",
    )
    ok(f"已写入 {len(entries)} 个模型到 ~/.workbuddy/models.json(原有自建模型已保留)")


def configure_dsh(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Write ~/.dsh/settings.yaml pi-ai provider and credentials."""
    settings_path = cfg_path(".dsh", "settings.yaml")
    credentials_path = cfg_path(".dsh", ".credentials.yaml")
    patch_path = cfg_path(".dsh", "cordis.patch.yml")
    model_entries = "\n".join(
        f"              - id: {model}\n                name: {model}"
        for model in get_model_ids(plan.key)
    )
    backup_file(settings_path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        "llm-pi-ai:\n"
        "  providers:\n"
        f"    {BRAND_SLUG}:\n"
        f"      displayName: {BRAND_NAME}\n"
        "      apiKeyEnv: TOKENPLAN_API_KEY\n"
        "      api: openai-completions\n"
        f"      baseURL: {base_url}\n"
        "      models:\n"
        f"{model_entries}\n"
        "agent-default-model:\n"
        f"  provider: {BRAND_SLUG}\n"
        f"  model: {get_model_catalog(plan.key)['default']}\n"
    )
    backup_file(credentials_path)
    credentials_path.write_text(
        json.dumps({"TOKENPLAN_API_KEY": api_key}, ensure_ascii=False, indent=2) + "\n"
    )
    _harden(credentials_path)
    backup_file(patch_path)
    patch_path.write_text("[]\n")
    info("DeepSeek Harness 已更新内置 pi-ai Provider 设置")
    warn("若启动时提示 cordis.patch.yml 格式错误，可执行：")
    if IS_WINDOWS:
        info(r"del %USERPROFILE%\.dsh\cordis.patch.yml")
        info("然后重新运行: dsh web")
    else:
        info("rm ~/.dsh/cordis.patch.yml")
        info("然后重新运行: dsh web")
        info("也可以保留文件并执行: printf '%s\\n' '[]' > ~/.dsh/cordis.patch.yml")


def install_codex_shell_env(api_key: str) -> None:
    """Expose TOKENPLAN_API_KEY to Codex via a sourced env file (or setx)."""
    if IS_WINDOWS:
        old_value = query_windows_user_env("TOKENPLAN_API_KEY")
        record_state("setx_keys", {"key": "TOKENPLAN_API_KEY", "old": old_value})
        os.environ["TOKENPLAN_API_KEY"] = api_key
        subprocess.run(
            ["setx", "TOKENPLAN_API_KEY", api_key], capture_output=True, check=False
        )
        info("已写入 Windows 用户环境变量 TOKENPLAN_API_KEY，重新打开终端后生效")
        return
    env_path = cfg_path(".codex", "tokenplan.env")
    write_env(env_path, export=True, TOKENPLAN_API_KEY=api_key)
    record_state("env_files", str(env_path))
    shell = os.environ.get("SHELL", "")
    rc_path = HOME / (".zshrc" if shell.endswith("/zsh") else ".bashrc")
    marker = "# Token Plan Codex API key"
    existing = rc_path.read_text() if rc_path.exists() else ""
    source_line = f'[ -f "{env_path}" ] && source "{env_path}"'
    if marker not in existing:
        rc_path.parent.mkdir(parents=True, exist_ok=True)
        rc_path.write_text(existing.rstrip() + f"\n{marker}\n{source_line}\n")
        record_state("rc_blocks", {"file": str(rc_path), "marker": marker})
    os.environ["TOKENPLAN_API_KEY"] = api_key


_ZCODE_PROVIDER_ID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "tokenplan"))


def _display_name(catalog: Dict[str, object], model_id: str) -> str:
    """Human label for a model id from the catalog display lines."""
    for line in _catalog_display(catalog):
        if ":" not in line:
            continue
        label, mid = line.split(":", 1)
        if mid.strip().split(" ", 1)[0] == model_id:
            return label.strip()
    return model_id


def _read_json_object(path: Path) -> Dict[str, object]:
    """Read a JSON object, tolerating missing/corrupt files (start fresh)."""
    if path.exists():
        try:
            data = json.loads(path.read_text())
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _strip_managed_block(lines: List[str], begin: str, end: str) -> List[str]:
    """Remove an inclusive managed marker block from TOML lines."""
    out: List[str] = []
    inside = False
    for line in lines:
        if line.strip() == begin:
            inside = True
            continue
        if line.strip() == end:
            inside = False
            continue
        if not inside:
            out.append(line)
    return out


def _normalize_blank_lines(lines: List[str]) -> List[str]:
    """Trim edge whitespace and collapse repeated blank lines."""
    normalized: List[str] = []
    for line in lines:
        if line.strip() or (normalized and normalized[-1].strip()):
            normalized.append(line)
    while normalized and not normalized[-1].strip():
        normalized.pop()
    return normalized


def _toml_normalize_header(header: str) -> str:
    """[models."glm-5.3"] and [models.glm-5.3] both -> models.glm-5.3."""
    inner = header.strip()[1:-1]
    parts = [p.strip().strip('"').strip("'") for p in inner.split(".")]
    return ".".join(parts)


def _toml_remove_sections(lines: List[str], targets: set) -> List[str]:
    """Drop whole [table] sections whose normalized header is in targets.

    Used to clean legacy unquoted sections written by <= 2.1.1 (dotted
    model ids parsed as nested tables there).
    """
    out: List[str] = []
    skipping = False
    for line in lines:
        s = line.strip()
        if s.startswith("[") and s.endswith("]") and not s.startswith("[["):
            skipping = _toml_normalize_header(s) in targets
            if skipping:
                continue
        if not skipping:
            out.append(line)
    return out


def _toml_upsert_root_key(lines: List[str], key: str, value: str) -> List[str]:
    """Set a root-level TOML key (before the first table header), preserving the rest."""
    rendered = f'{key} = "{value}"'
    root_end = len(lines)
    for i, line in enumerate(lines):
        if line.lstrip().startswith("["):
            root_end = i
            break
    for i in range(root_end):
        stripped = lines[i].strip()
        if stripped.startswith(f"{key} ") or stripped.startswith(f"{key}="):
            lines[i] = rendered
            return lines
    lines.insert(root_end, rendered)
    return lines


def _toml_upsert_section(
    lines: List[str], header: str, entries: Dict[str, object]
) -> List[str]:
    """Create or update a [table] section; unknown lines inside are preserved."""
    def _render(k: str, v: object) -> str:
        if isinstance(v, bool):
            return f"{k} = {'true' if v else 'false'}"
        if isinstance(v, (int, float)):
            return f"{k} = {v}"
        return f'{k} = "{v}"'

    rendered_entries = [_render(k, v) for k, v in entries.items()]
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header:
            start = i
            break
    if start is None:
        block = ["", header, *rendered_entries]
        return lines + block
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].lstrip().startswith("["):
            end = i
            break
    section = lines[start + 1:end]
    kept: List[str] = []
    handled = set()
    for line in section:
        stripped = line.strip()
        matched = False
        for k, v in entries.items():
            if stripped.startswith(f"{k} ") or stripped.startswith(f"{k}="):
                if k not in handled:
                    kept.append(_render(k, v))
                    handled.add(k)
                matched = True
                break
        if not matched:
            kept.append(line)
    for k, v in entries.items():
        if k not in handled:
            kept.append(_render(k, v))
    return lines[:start + 1] + kept + lines[end:]


def configure_codex(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure Codex CLI; wire_api is domain-dependent (real-key verified).

    - tokenhub domains (enterprise/intl/postpaid): "responses" — endpoint
      serves 200, and Codex >=0.152 dropped chat support so responses is
      the only mode that works on current Codex
    - lkeap (personal plans): "chat" per official doc 1823/130071 — lkeap
      has no /responses (404). Codex >=0.152 rejects chat at config load;
      personal-plan users need a Codex from before the deprecation
      (openai/codex discussion #7782)
    - intl gateway (tencentcloudmaas): the "auto" router rejects the
      Responses protocol (400005, real-key verified) even though every
      concrete model accepts it — Codex defaults to the first concrete
      model there. CN tokenhub serves auto over responses fine.
    """
    config_path = cfg_path(".codex", "config.toml")
    default_model = str(get_model_catalog(plan.key)["default"])
    if "tencentcloudmaas" in base_url and default_model == "auto":
        concrete = [m for m in get_model_ids(plan.key) if m != "auto"]
        if concrete:
            default_model = concrete[0]
    wire_api = "chat" if "lkeap" in base_url else "responses"
    existing_lines = (
        config_path.read_text().splitlines() if config_path.exists() else []
    )
    backup_file(config_path)
    lines = _toml_upsert_root_key(existing_lines, "model_provider", BRAND_SLUG)
    lines = _toml_upsert_root_key(lines, "model", default_model)
    # 摘除 2.5.x 旧 provider 段,避免残留一个失效的 tokenplan 入口
    lines = _toml_remove_sections(
        lines, {f"model_providers.{legacy}" for legacy in BRAND_LEGACY_KEYS}
    )
    lines = _toml_upsert_section(
        lines,
        f"[model_providers.{BRAND_SLUG}]",
        {
            "name": BRAND_VENDOR,
            "base_url": base_url,
            "wire_api": wire_api,
            "env_key": "TOKENPLAN_API_KEY",
        },
    )
    config_path.write_text("\n".join(lines).rstrip() + "\n")
    install_codex_shell_env(api_key)
    if wire_api == "chat":
        warn(
            "个人版(lkeap)无 Responses 端点,已按官方文档写入 wire_api=chat;"
            "注意 Codex 0.152+ 已移除 chat 模式,如报错需降级 Codex 版本"
        )
    info(f"Codex 已配置: {config_path} (model = {default_model}, wire_api = {wire_api})")


def _kimi_home() -> Path:
    home = os.environ.get("KIMI_CODE_HOME")
    return Path(home) if home else HOME / ".kimi-code"


def configure_kimi(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure Kimi Code CLI (~/.kimi-code/config.toml) as an OpenAI-compatible provider.

    Schema (kimi-code 0.40.x): top-level default_provider/default_model must
    appear BEFORE any [table] header (TOML rule); [providers.<id>] carries
    type/base_url/api_key; [models.<id>] requires provider + model +
    max_context_size (display_name optional). Verified end-to-end against
    the TokenHub chat-completions endpoint.
    """
    home = _kimi_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.toml"
    existing_lines = (
        config_path.read_text().splitlines() if config_path.exists() else []
    )
    backup_file(config_path)
    catalog = get_model_catalog(plan.key)
    default_model = str(catalog["default"])
    managed = {f"models.{m}" for m in get_model_ids(plan.key)}
    lines = _toml_remove_sections(existing_lines, managed)
    # 摘除 2.5.x 旧 provider 段(其 model 段已随 managed 集合重写)
    lines = _toml_remove_sections(
        lines, {f"providers.{legacy}" for legacy in BRAND_LEGACY_KEYS}
    )
    lines = _normalize_blank_lines(lines)
    lines = _toml_upsert_root_key(lines, "default_provider", BRAND_SLUG)
    lines = _toml_upsert_root_key(lines, "default_model", default_model)
    lines = _toml_upsert_section(
        lines,
        f"[providers.{BRAND_SLUG}]",
        {
            "type": "openai",
            "base_url": base_url,
            "api_key": api_key,
        },
    )
    for model_id in get_model_ids(plan.key):
        display = _display_name(catalog, model_id)
        # 模型 id 含点号(glm-5.3):TOML 表头中点是分隔符,必须引号包裹,
        # 否则解析成嵌套表并与平级 [models.glm-5] 冲突 → 整个文件解析失败
        lines = _toml_upsert_section(
            lines,
            f'[models."{model_id}"]',
            {
                "provider": BRAND_SLUG,
                "model": model_id,
                "display_name": display,
                "max_context_size": 128000,
            },
        )
    config_path.write_text("\n".join(lines).rstrip() + "\n")
    _harden(config_path)
    info(f"Kimi Code 已配置: {config_path} ({len(get_model_ids(plan.key))} 个模型)")


def _grok_home() -> Path:
    home = os.environ.get("GROK_HOME")
    return Path(home) if home else HOME / ".grok"


def configure_grok(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure Grok CLI (~/.grok/config.toml) custom models.

    Grok models are flat [model.<id>] tables; api_backend defaults to
    chat_completions, which TokenHub exposes on every site. Verified
    end-to-end: grok sent requests to <base_url>/chat/completions.
    """
    home = _grok_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.toml"
    existing = config_path.read_text() if config_path.exists() else ""
    backup_file(config_path)
    catalog = get_model_catalog(plan.key)
    # 移除旧的托管块(模型集合可能变化),再重写;2.5.x 的旧品牌标记也一并剥离
    lines = _strip_managed_block(
        existing.splitlines(), "# Token Plan models begin", "# Token Plan models end"
    )
    lines = _strip_managed_block(
        lines, f"# {BRAND_NAME} models begin", f"# {BRAND_NAME} models end"
    )
    lines = _normalize_blank_lines(lines)
    block: List[str] = ["", f"# {BRAND_NAME} models begin"]
    for model_id in get_model_ids(plan.key):
        display = _display_name(catalog, model_id)
        block.append(f'[model."{model_id}"]')
        block.append(f'model = "{model_id}"')
        block.append(f'base_url = "{base_url}"')
        block.append(f'name = "{display}"')
        block.append(f'api_key = "{api_key}"')
        block.append("")
    block.append(f"# {BRAND_NAME} models end")
    lines = lines + block
    config_path.write_text("\n".join(lines).rstrip() + "\n")
    _harden(config_path)
    info(f"Grok 已配置: {config_path} ({len(get_model_ids(plan.key))} 个模型)")


def _pi_agent_dir() -> Path:
    override = os.environ.get("PI_CODING_AGENT_DIR")
    if override:
        return Path(override)
    config_dir = os.environ.get("PI_CONFIG_DIR")
    base = Path(config_dir) if config_dir else HOME / ".pi"
    return base / "agent"


def configure_pi(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure the Pi coding agent (~/.pi/agent/models.json).

    Provider entry under providers.<BRAND_SLUG> with api openai-completions;
    models need only id (name/context defaults apply). Verified
    end-to-end: pi listed the provider and reached the TokenHub endpoint.
    """
    agent_dir = _pi_agent_dir()
    agent_dir.mkdir(parents=True, exist_ok=True)
    models_path = agent_dir / "models.json"
    data = _read_json_object(models_path)
    backup_file(models_path)
    catalog = get_model_catalog(plan.key)
    models = []
    for model_id in get_model_ids(plan.key):
        entry: Dict[str, object] = {"id": model_id, "name": _display_name(catalog, model_id)}
        models.append(entry)
    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
    for legacy in BRAND_LEGACY_KEYS:
        providers.pop(legacy, None)
    providers[BRAND_SLUG] = {
        "baseUrl": base_url,
        "api": "openai-completions",
        "apiKey": api_key,
        "models": models,
    }
    data["providers"] = providers
    models_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _harden(models_path)
    info(f"Pi 已配置: {models_path} ({len(models)} 个模型)")


def _zcode_v2_dir() -> Path:
    home = os.environ.get("ZCODE_HOME")
    base = Path(home) if home else HOME / ".zcode"
    return base / "v2"


def configure_zcode(base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Configure ZCode (~/.zcode/v2/config.json) as a custom provider.

    ZCode (z.ai coding client) keeps custom providers in config.json:
    provider.<id> = {name, kind, options{baseURL, apiKey}, models{<id>}}.
    ids must not start with builtin:; a deterministic UUID keeps reruns
    idempotent. Config-layer tested (format cross-confirmed by two
    third-party ZCode tools); the closed client itself is not verified.
    """
    v2 = _zcode_v2_dir()
    v2.mkdir(parents=True, exist_ok=True)
    config_path = v2 / "config.json"
    data = _read_json_object(config_path)
    backup_file(config_path)
    catalog = get_model_catalog(plan.key)
    models: Dict[str, object] = {}
    for model_id in get_model_ids(plan.key):
        models[model_id] = {
            "name": _display_name(catalog, model_id),
            "limit": {"context": 128000, "output": 16384},
        }
    providers = data.get("provider")
    if not isinstance(providers, dict):
        providers = {}
    providers[_ZCODE_PROVIDER_ID] = {
        "name": BRAND_VENDOR,
        "kind": "openai-compatible",
        "options": {"baseURL": base_url, "apiKey": api_key},
        "models": models,
    }
    data["provider"] = providers
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    _harden(config_path)
    info(f"ZCode 已配置: {config_path} ({len(models)} 个模型,客户端未实测)")


CONFIGURATOR_REGISTRY: Dict[str, Callable[[str, str, PlanSpec], None]] = {
    "workbuddy": configure_workbuddy,
    "codebuddy": configure_codebuddy,
    "claude-code": configure_claude_code,
    "hermes": configure_hermes,
    "dsh": configure_dsh,
    "openclaw": configure_openclaw,
    "opencode": configure_opencode,
    "codex": configure_codex,
    "kimi": configure_kimi,
    "grok": configure_grok,
    "pi": configure_pi,
    "zcode": configure_zcode,
}

# doctor 用来判断"我们的配置块还在不在"的签名:工具 key -> (HOME 相对路径,
# 当前特征串, 旧版特征串)。旧特征用于兼容 2.5.x 写入的旧品牌配置——
# 那些配置仍可正常工作,doctor 不应误报"配置缺失"(重跑 repair 即升级品牌)。
# 必须与对应 configurator 实际写入的内容保持同步(有测试守着)。
CONFIG_SIGNATURES: Dict[str, Tuple[str, str, str]] = {
    "codebuddy": (".codebuddy/settings.json", "CODEBUDDY_API_KEY", ""),
    "claude-code": (".claude/settings.json", f'"{BRAND_SLUG}"', '"tokenplan"'),
    "hermes": (".hermes/config.yaml", f"provider: {BRAND_SLUG}", "token-plan"),
    "openclaw": (".openclaw/openclaw.json", f'"{BRAND_SLUG}"', '"tencent-tokenplan"'),
    "opencode": (".config/opencode/opencode.json", f'"{BRAND_SLUG}"', '"tokenplan"'),
    "dsh": (".dsh/settings.yaml", f"{BRAND_SLUG}:", "tokenplan:"),
    "codex": (".codex/config.toml", f"[model_providers.{BRAND_SLUG}]", "[model_providers.tokenplan]"),
    "workbuddy": (".workbuddy/models.json", BRAND_VENDOR, "Tencent Cloud Token Plan"),
    "kimi": (".kimi-code/config.toml", f"[providers.{BRAND_SLUG}]", "[providers.tokenplan]"),
    "grok": (".grok/config.toml", f"# {BRAND_NAME} models begin", "# Token Plan models begin"),
    "pi": (".pi/agent/models.json", f'"{BRAND_SLUG}"', '"tokenplan"'),
    "zcode": (".zcode/v2/config.json", BRAND_VENDOR, "Tencent Cloud Token Plan"),
}


def probe_config(tool: ToolSpec) -> Optional[bool]:
    """Check whether this installer's config block still exists.

    Returns None when the tool has no auto-config (guided only); True/False
    when the signature file exists and contains/misses our marker.
    旧版品牌特征也算存在:配置仍有效,只是品牌名待升级(repair 可刷新)。
    """
    signature = CONFIG_SIGNATURES.get(tool.key)
    if not signature:
        return None
    rel_path, marker, legacy_marker = signature
    path = HOME / rel_path
    if not path.exists():
        return False
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        return marker in text or (bool(legacy_marker) and legacy_marker in text)
    except OSError:
        return False


def configure_tool(tool: ToolSpec, base_url: str, api_key: str, plan: PlanSpec) -> None:
    """Dispatch to the tool's configurator if one is registered."""
    configurator = CONFIGURATOR_REGISTRY.get(tool.key)
    if configurator:
        configurator(base_url, api_key, plan)


__all__ = [name for name in globals() if not name.startswith("__")]
