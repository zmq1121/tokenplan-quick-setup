"""Expose every zero-dependency regression group through pytest."""
import importlib.util
import sys
from pathlib import Path
from typing import Callable

import pytest

RUN_TESTS = Path(__file__).with_name("run_tests.py")
SPEC = importlib.util.spec_from_file_location("legacy_run_tests", RUN_TESTS)
assert SPEC is not None and SPEC.loader is not None
legacy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = legacy
SPEC.loader.exec_module(legacy)


@pytest.mark.parametrize(
    ("group_name", "group"),
    legacy.TEST_GROUPS,
    ids=[name for name, _group in legacy.TEST_GROUPS],
)
def test_legacy_regression_group(
    group_name: str,
    group: Callable[[], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run one legacy group with isolated counters and pytest failure reporting."""
    legacy.PASSES.clear()
    legacy.FAILS.clear()
    monkeypatch.setattr(sys, "argv", [str(RUN_TESTS)])

    group()

    failures = tuple(legacy.FAILS)
    passed = len(legacy.PASSES)
    legacy.PASSES.clear()
    legacy.FAILS.clear()
    assert not failures, (
        f"legacy group {group_name!r}: {passed} passed, "
        f"{len(failures)} failed: {failures}"
    )
    # 组被改空或提前 return 时不能算通过,否则回归套件会静默失去覆盖。
    assert passed, f"legacy group {group_name!r} asserted nothing"
