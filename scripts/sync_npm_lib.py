#!/usr/bin/env python3
"""同步构建产物:npm/lib/setup.command 与主脚本对齐,并刷新 setup.bat 的版本与 SHA256。

发布前必须执行;tests/run_tests.py 的 consistency 组会校验字节一致与哈希匹配。
同时再生 models.json.sha256(远程目录完整性校验依赖,改 models.json 后必须刷新;
在这里自动再生保证"改了目录忘刷哈希"不可能发生)。
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
catalog = REPO / "models.json"
catalog_sha = REPO / "models.json.sha256"

if not src.exists():
    print(f"missing {src}", file=sys.stderr)
    sys.exit(1)

# 主脚本版本号(注入 setup.bat / 维护 models.json.latest_version 共用)
m = re.search(r'^VERSION = "([^"]+)"', src.read_text(encoding="utf-8"), re.M)
if not m:
    print("VERSION not found in setup.command", file=sys.stderr)
    sys.exit(1)
version = m.group(1)

dst.parent.mkdir(parents=True, exist_ok=True)
shutil.copy2(src, dst)
print(f"synced {dst.relative_to(REPO)} ({src.stat().st_size} bytes)")

# models.json.latest_version:旧安装器据此提示升级(notify_upgrade_available)。
# 手工维护曾在 2.5.0/2.6.0 连续漏更,这里改为随 sync 自动对齐主脚本版本,
# 先改内容再算哈希,保证"改了目录忘刷哈希"不可能发生。
catalog_text = catalog.read_text(encoding="utf-8")
new_catalog = re.sub(
    r'("latest_version"\s*:\s*")[^"]+',
    rf'\g<1>{version}',
    catalog_text,
    count=1,
)
if new_catalog != catalog_text:
    catalog.write_text(new_catalog, encoding="utf-8")
    print(f"models.json latest_version -> {version}")

# models.json.sha256:与 models.json 字节严格对应(refresh_remote_catalog 会校验)
if catalog.exists():
    digest = hashlib.sha256(catalog.read_bytes()).hexdigest()
    expected = f"{digest}  models.json\n"
    if not catalog_sha.exists() or catalog_sha.read_text(encoding="utf-8") != expected:
        catalog_sha.write_text(expected, encoding="utf-8")
        print(f"models.json.sha256 regenerated: {digest[:16]}…")
    else:
        print("models.json.sha256 already current")
else:
    print("models.json missing; skip sha256 regeneration", file=sys.stderr)
    sys.exit(1)

# setup.bat:注入版本号与主脚本 SHA256(固定版本下载 + 完整性校验)
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
