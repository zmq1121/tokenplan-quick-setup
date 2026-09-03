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


@pytest.fixture(autouse=True)
def _reset_adapter_process_globals(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """adapters 的模块级缓存(远程目录/后付费发现结果)在每条用例前重置。

    这些是进程级可变状态:某条用例填充后若不清理,后续用例会读到残留值,
    测试结果将依赖执行顺序。monkeypatch 在用例结束后自动恢复原值,
    显式声明的用例(如真实网络发现)不受影响——它们在本条 fixture 之后运行。
    """
    monkeypatch.setattr(adapters, "_REMOTE_CATALOG", None)
    monkeypatch.setattr(adapters, "_REMOTE_LATEST_VERSION", None)
    monkeypatch.setattr(adapters, "_POSTPAID_DISCOVERED", None)
    monkeypatch.setattr(adapters, "_POSTPAID_SELECTED", None)
    yield
