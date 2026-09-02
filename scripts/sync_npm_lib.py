#!/usr/bin/env python3
"""同步构建产物:npm/lib/setup.command 与主脚本对齐,并刷新 setup.bat 的版本与 SHA256。

发布前必须执行;tests/run_tests.py 的 consistency 组会校验字节一致与哈希匹配。
"""
import hashlib
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
src = REPO / "setup.command"
dst = REPO / "npm" / "lib" / "setup.command"
bat = REPO / "setup.bat"

if not src.exists():
    print(f"missing {src}", file=sys.stderr)
    sys.exit(1)

dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(src, dst)
print(f"synced {dst.relative_to(REPO)} ({src.stat().st_size} bytes)")

# setup.bat:注入版本号与主脚本 SHA256(固定版本下载 + 完整性校验)
m = re.search(r'^VERSION = "([^"]+)"', src.read_text(encoding="utf-8"), re.M)
if not m:
    print("VERSION not found in setup.command", file=sys.stderr)
    sys.exit(1)
version = m.group(1)
sha256 = hashlib.sha256(src.read_bytes()).hexdigest()

bat_text = bat.read_bytes().decode("utf-8")  # 二进制读,保留 CRLF(Windows 批处理要求)
new_bat = re.sub(
    r'set "SETUP_VERSION=[^"]*"',
    f'set "SETUP_VERSION={version}"',
    bat_text,
)
new_bat = re.sub(
    r'set "SETUP_SHA256=[^"]*"',
    f'set "SETUP_SHA256={sha256}"',
    new_bat,
)
if new_bat != bat_text:
    bat.write_bytes(new_bat.encode("utf-8"))
    print(f"setup.bat updated: v{version} sha256={sha256[:16]}…")
else:
    print(f"setup.bat already current: v{version}")
