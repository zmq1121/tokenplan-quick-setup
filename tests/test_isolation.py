"""Guards that the test sandbox actually redirects every path the code uses.

A module that snapshots ``HOME``/``BACKUP_DIR``/``STATE_PATH`` via
``from ... import`` keeps its own binding, so patching one module is not
enough. These tests fail loudly if a new module or constant escapes the
``isolated_home`` fixture, which is the only thing standing between the suite
and the developer's real configuration.
"""
import importlib
import pkgutil
from pathlib import Path
from typing import List, Tuple

import pytest

import tokenplan_setup
from tests.conftest import PATCHED_MODULES, PATH_CONSTANTS


def _package_modules() -> List[object]:
    """Import every package submodule so no snapshot holder is missed."""
    modules = [tokenplan_setup]
    for info in pkgutil.iter_modules(tokenplan_setup.__path__):
        if info.name in {"__main__", "_runtime"}:
            continue
        modules.append(importlib.import_module(f"tokenplan_setup.{info.name}"))
    return modules


def _snapshot_holders() -> List[Tuple[object, str]]:
    return [
        (module, name)
        for module in _package_modules()
        for name in PATH_CONSTANTS
        if hasattr(module, name)
    ]


def test_every_path_snapshot_is_redirected(isolated_home: Path) -> None:
    """No live path constant may point outside the temporary home."""
    holders = _snapshot_holders()
    assert holders, "path constants disappeared; update PATH_CONSTANTS"

    escaped = [
        f"{getattr(module, '__name__', module)}.{name} = {getattr(module, name)}"
        for module, name in holders
        if not str(getattr(module, name)).startswith(str(isolated_home))
    ]
    assert not escaped, (
        "these constants still point at the real user home: " + ", ".join(escaped)
    )


def test_conftest_patches_every_module_that_holds_a_snapshot() -> None:
    """Keep the fixture's module list in sync with the package automatically."""
    patched = {getattr(module, "__name__", "") for module in PATCHED_MODULES}
    missing = sorted(
        getattr(module, "__name__", "")
        for module, _name in _snapshot_holders()
        if getattr(module, "__name__", "") not in patched
    )
    assert not missing, (
        "these modules snapshot path constants but are not patched by "
        f"isolated_home: {missing}"
    )


def test_real_home_is_never_the_backup_target(isolated_home: Path) -> None:
    """Regression guard for the uninstall path reading the real backup manifest."""
    from tokenplan_setup import flows

    assert flows.BACKUP_DIR == isolated_home / ".tokenplan-backups"
    assert flows.collect_latest_backups() == {}


@pytest.mark.parametrize("constant", PATH_CONSTANTS)
def test_constants_are_paths(constant: str, isolated_home: Path) -> None:
    for module, name in _snapshot_holders():
        if name == constant:
            assert isinstance(getattr(module, name), Path)
