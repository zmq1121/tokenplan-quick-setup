"""Subprocess smoke tests for supported package and npm entrypoints."""
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tokenplan_setup import cli, entrypoint
from tokenplan_setup.infrastructure import VERSION

REPO = Path(__file__).resolve().parents[1]
NODE_WRAPPER = REPO / "npm" / "bin" / "tokenplan-setup.js"
EXPECTED_VERSION_LINE = f"tokenplan-setup {VERSION}"


def _isolated_environment(home: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["HOME"] = str(home)
    environment.pop("TOKENPLAN_API_KEY", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return environment


def test_python_entrypoints_delegate_and_propagate_exit_codes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Installed entrypoints must run the imported CLI, not a second exec'd copy."""
    assert entrypoint.main is cli.main

    monkeypatch.setattr(entrypoint, "main", lambda: 3)
    with pytest.raises(SystemExit) as raised:
        runpy.run_module("tokenplan_setup.__main__", run_name="__main__")
    assert raised.value.code == 3


@pytest.mark.entrypoint
def test_python_module_version_smoke(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "tokenplan_setup", "--version"],
        cwd=REPO,
        env=_isolated_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == EXPECTED_VERSION_LINE
    assert not (tmp_path / ".tokenplan-backups").exists()
    assert not (tmp_path / ".codex").exists()


@pytest.mark.entrypoint
def test_plain_import_does_not_build_flat_namespace(tmp_path: Path) -> None:
    """Guard against re-introducing a second exec'd copy of every module."""
    program = (
        "import sys, tokenplan_setup\n"
        "from tokenplan_setup import cli, entrypoint\n"
        "assert entrypoint.main is cli.main\n"
        "print('tokenplan_setup._runtime' in sys.modules)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=REPO,
        env=_isolated_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"


@pytest.mark.entrypoint
def test_node_wrapper_exports_testable_api(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    program = (
        "const w=require(process.argv[1]);"
        "console.log(JSON.stringify({main:typeof w.main,detect:typeof w.detectPython}));"
    )
    result = subprocess.run(
        [node, "-e", program, str(NODE_WRAPPER)],
        cwd=REPO,
        env=_isolated_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"main": "function", "detect": "function"}


@pytest.mark.entrypoint
def test_node_wrapper_version_smoke(tmp_path: Path) -> None:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    result = subprocess.run(
        [node, str(NODE_WRAPPER), "--version"],
        cwd=REPO,
        env=_isolated_environment(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert EXPECTED_VERSION_LINE in result.stdout
