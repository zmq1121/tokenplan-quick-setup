"""Shared pytest isolation fixtures."""
import os
from pathlib import Path
from typing import Iterator, Tuple

import pytest

from tokenplan_setup import adapters, cli, domain, flows, infrastructure

# HOME/BACKUP_DIR/STATE_PATH 在各层是 `from ... import` 的导入期快照,补丁必须
# 打到每个持有者身上。只patch infrastructure 是不够的:flows 持有自己的
# BACKUP_DIR 快照,卸载还原曾因此读取真实的 ~/.tokenplan-backups 并尝试覆盖
# 真实用户配置。新增模块请一并列入,test_isolation 会守住这一点。
PATCHED_MODULES: Tuple[object, ...] = (
    infrastructure,
    domain,
    adapters,
    flows,
    cli,
)
PATH_CONSTANTS = ("HOME", "BACKUP_DIR", "STATE_PATH")


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Redirect every package path and relevant environment override to tmp_path."""
    backup_dir = tmp_path / ".tokenplan-backups"
    overrides = {
        "HOME": tmp_path,
        "BACKUP_DIR": backup_dir,
        "STATE_PATH": backup_dir / "state.json",
    }
    for module in PATCHED_MODULES:
        for name, value in overrides.items():
            if hasattr(module, name):
                monkeypatch.setattr(module, name, value)
    monkeypatch.setattr(infrastructure.RUN_CONTEXT, "home", tmp_path)
    monkeypatch.setattr(infrastructure.RUN_CONTEXT, "backup_dir", backup_dir)
    monkeypatch.setattr(
        infrastructure.RUN_CONTEXT, "state_path", backup_dir / "state.json"
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("KIMI_CODE_HOME", str(tmp_path / ".kimi-code"))
    monkeypatch.setenv("GROK_HOME", str(tmp_path / ".grok"))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / ".pi" / "agent"))
    monkeypatch.setenv("ZCODE_HOME", str(tmp_path / ".zcode"))
    monkeypatch.delenv("TOKENPLAN_API_KEY", raising=False)
    yield tmp_path

    assert os.environ.get("HOME") == str(tmp_path)
