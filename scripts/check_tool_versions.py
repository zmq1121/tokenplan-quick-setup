#!/usr/bin/env python3
"""对照 npm registry 校验 VERIFIED_TOOL_VERSIONS 的版本与 integrity。

用法:
    python3 scripts/check_tool_versions.py          # 实时核对
    python3 scripts/check_tool_versions.py --json   # 机器可读输出

为什么需要它:安装路径只 pin 精确版本,能防住"跟随 @latest 漂移",但防不住
同一版本号下 tarball 被重新发布。清单里留档的 integrity 只有和 registry 实时
比对才有防护意义,这个脚本就是把那份留档变成可执行门禁。

退出码:
    0 = 全部一致(可能有"有新版本可升"这类提示,不算失败)
    1 = 出现完整性/版本不一致,需要人工介入
    2 = 网络或 registry 异常,本次无法证明一致性(区别于确定的不一致)
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# 必须先把仓库根加入 sys.path,本脚本才能在未安装包的情况下直接运行。
from tokenplan_setup.domain import VERIFIED_TOOL_VERSIONS  # noqa: E402

REGISTRY = "https://registry.npmjs.org"
# 精简 packument:体积远小于完整元数据,但仍带 dist.integrity 与 dist-tags。
ACCEPT = "application/vnd.npm.install-v1+json"
UA = "tokenplan-quick-setup-version-checker/1.0"
TIMEOUT = 20


def fetch_packument(package: str) -> Dict[str, object]:
    """Fetch the abbreviated registry metadata for one package."""
    url = f"{REGISTRY}/{urllib.parse.quote(package, safe='@')}"
    request = urllib.request.Request(
        url, headers={"Accept": ACCEPT, "User-Agent": UA}
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{package}: registry 返回了非对象响应")
    return payload


def is_prerelease(version: str) -> bool:
    """True for SemVer versions carrying a prerelease suffix."""
    return "-" in version


def check_package(
    package: str, pinned: Dict[str, str]
) -> Tuple[Dict[str, object], List[str], List[str]]:
    """Compare one pinned package against the registry.

    Returns the report row plus (failures, notices); failures mean the pin can
    no longer be trusted, notices are non-blocking drift worth a human look.
    """
    packument = fetch_packument(package)
    versions = packument.get("versions")
    tags = packument.get("dist-tags")
    if not isinstance(versions, dict) or not isinstance(tags, dict):
        raise ValueError(f"{package}: registry 响应缺少 versions/dist-tags")

    expected_version = pinned["version"]
    expected_integrity = pinned["integrity"]
    registry_latest = str(tags.get("latest", ""))

    failures: List[str] = []
    notices: List[str] = []
    actual_integrity = ""

    entry = versions.get(expected_version)
    if not isinstance(entry, dict):
        failures.append(
            f"{package}: 清单 pin 的版本 {expected_version} 在 registry 上不存在"
            "(已撤回或版本号有误,安装会直接失败)"
        )
    else:
        dist = entry.get("dist")
        actual_integrity = (
            str(dist.get("integrity", "")) if isinstance(dist, dict) else ""
        )
        if not actual_integrity:
            failures.append(f"{package}@{expected_version}: registry 未提供 integrity")
        elif actual_integrity != expected_integrity:
            failures.append(
                f"{package}@{expected_version}: integrity 不匹配"
                f"(同一版本号下 tarball 已变化,疑似重新发布)\n"
                f"      清单: {expected_integrity}\n"
                f"      实时: {actual_integrity}"
            )

    if registry_latest and registry_latest != expected_version:
        notices.append(
            f"{package}: registry latest 为 {registry_latest},清单仍 pin "
            f"{expected_version}"
        )
    if pinned.get("stability") == "prerelease-only":
        stable = [v for v in versions if not is_prerelease(v)]
        if stable:
            notices.append(
                f"{package}: 已出现非预发布版本 {sorted(stable)[-1]},"
                "可考虑改 pin 稳定版"
            )

    row: Dict[str, object] = {
        "pinned_version": expected_version,
        "registry_latest": registry_latest,
        "expected_integrity": expected_integrity,
        "actual_integrity": actual_integrity,
        "integrity_matches": bool(actual_integrity)
        and actual_integrity == expected_integrity,
    }
    return row, failures, notices


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass

    report: Dict[str, Dict[str, object]] = {}
    failures: List[str] = []
    notices: List[str] = []
    unreachable: List[str] = []

    for package, pinned in VERIFIED_TOOL_VERSIONS.items():
        try:
            row, package_failures, package_notices = check_package(package, pinned)
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            # 网络问题不能算"清单错误",否则会把不可用误报成不一致。
            unreachable.append(f"{package}: {exc}")
            continue
        except (ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{package}: registry 响应异常 {exc}")
            continue
        report[package] = row
        failures.extend(package_failures)
        notices.extend(package_notices)

    if args.json:
        print(json.dumps(
            {
                "packages": report,
                "failures": failures,
                "notices": notices,
                "unreachable": unreachable,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        for package, row in report.items():
            mark = "✓" if row["integrity_matches"] else "✗"
            print(f"  {mark} {package}@{row['pinned_version']}")
        for note in notices:
            print(f"\n  ℹ {note}")
        for problem in unreachable:
            print(f"\n  ⚠ 无法核对 {problem}")
        for problem in failures:
            print(f"\n  ✗ {problem}")
        print()
        if failures:
            print("结论: 供应链清单与 registry 不一致,需人工确认后更新")
            print("      tokenplan_setup/domain.py 的 VERIFIED_TOOL_VERSIONS。")
        elif unreachable:
            print("结论: 本次未能完成核对(网络/registry 不可用),一致性未获证明。")
        else:
            print(f"结论: {len(report)} 个包的版本与 integrity 均与 registry 一致。")

    if failures:
        return 1
    if unreachable:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
