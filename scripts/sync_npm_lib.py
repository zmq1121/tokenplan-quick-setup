#!/usr/bin/env python3
"""同步构建产物:npm/lib/setup.command 与主脚本对齐。

发布 npm 前必须执行;tests/run_tests.py 的 consistency 组会校验字节一致。
"""
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
src = REPO / "setup.command"
dst = REPO / "npm" / "lib" / "setup.command"

if not src.exists():
    print(f"missing {src}", file=sys.stderr)
    sys.exit(1)

dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(src, dst)
print(f"synced {dst.relative_to(REPO)} ({src.stat().st_size} bytes)")
