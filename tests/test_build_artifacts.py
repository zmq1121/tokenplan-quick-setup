"""Deterministic distribution artifact tests."""
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import build_dist

REPO = Path(__file__).resolve().parents[1]


@pytest.mark.artifact
def test_build_check_reports_all_artifacts_current() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/build_dist.py", "--check"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "5 artifacts" in result.stdout


@pytest.mark.artifact
def test_expected_outputs_are_exact_bytes_on_disk() -> None:
    expected = build_dist.expected_outputs()
    assert len(expected) == 5
    for path, content in expected.items():
        assert path.read_bytes() == content
    launcher = expected[REPO / "setup.command"].splitlines()[:2]
    assert b"command -v python3 || command -v python" in launcher[1]


@pytest.mark.artifact
def test_windows_launcher_digest_targets_standalone_script() -> None:
    script = (REPO / "setup.command").read_bytes()
    digest = hashlib.sha256(script).hexdigest()
    assert digest.encode() in (REPO / "setup.bat").read_bytes()
