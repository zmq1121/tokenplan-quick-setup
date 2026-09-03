"""Shared source-bundling primitives for the single-file distribution.

``scripts/build_dist.py`` concatenates these sources into ``setup.command``,
and the legacy regression suite executes them into one flat namespace to
reproduce the bundled script's semantics. Both go through the transform
defined here so the artifact and the tests cannot drift apart.
"""
import ast
from pathlib import Path
from typing import Callable, Dict, Optional

SOURCE_ORDER = (
    "infrastructure.py",
    "_model_catalog.py",
    "domain.py",
    "adapters.py",
    "flows.py",
    "cli.py",
)
PACKAGE_DIR = Path(__file__).resolve().parent

SourceTransform = Callable[[Path, str], str]


def strip_internal_imports(text: str) -> str:
    """Remove package-internal imports, including parenthesized multiline forms."""
    lines = text.splitlines()
    for node in ast.walk(ast.parse(text)):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("tokenplan_setup.")
        ):
            end_lineno = node.end_lineno or node.lineno
            for index in range(node.lineno - 1, end_lineno):
                lines[index] = ""
    return "\n".join(lines).rstrip() + "\n"


def execute_sources(
    namespace: Dict[str, object],
    source_transform: Optional[SourceTransform] = None,
) -> Dict[str, object]:
    """Execute every source layer into ``namespace`` using its real filename."""
    for filename in SOURCE_ORDER:
        path = PACKAGE_DIR / filename
        source = strip_internal_imports(path.read_text(encoding="utf-8"))
        if source_transform is not None:
            source = source_transform(path, source)
        exec(compile(source, str(path), "exec"), namespace)
    return namespace
