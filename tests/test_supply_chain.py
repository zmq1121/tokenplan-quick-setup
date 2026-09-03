"""Offline tests for the npm pin/integrity verification gate."""
import importlib.util
import sys
from pathlib import Path
from typing import Dict

import pytest

CHECKER = Path(__file__).resolve().parents[1] / "scripts" / "check_tool_versions.py"
SPEC = importlib.util.spec_from_file_location("check_tool_versions", CHECKER)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = checker
SPEC.loader.exec_module(checker)

PINNED = {
    "version": "1.2.3",
    "dist_tag": "latest",
    "stability": "stable",
    "integrity": "sha512-expected==",
}


def packument(
    versions: Dict[str, object],
    latest: str = "1.2.3",
) -> Dict[str, object]:
    """Build a minimal abbreviated packument response."""
    return {"versions": versions, "dist-tags": {"latest": latest}}


def _stub(monkeypatch: pytest.MonkeyPatch, payload: Dict[str, object]) -> None:
    monkeypatch.setattr(checker, "fetch_packument", lambda _package: payload)


def test_matching_integrity_reports_no_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, packument(
        {"1.2.3": {"dist": {"integrity": "sha512-expected=="}}}
    ))

    row, failures, notices = checker.check_package("demo", PINNED)

    assert failures == []
    assert notices == []
    assert row["integrity_matches"] is True


def test_republished_tarball_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same version, different integrity: the exact threat version pinning misses."""
    _stub(monkeypatch, packument(
        {"1.2.3": {"dist": {"integrity": "sha512-tampered=="}}}
    ))

    row, failures, notices = checker.check_package("demo", PINNED)

    assert row["integrity_matches"] is False
    assert len(failures) == 1
    assert "integrity 不匹配" in failures[0]
    assert "sha512-tampered==" in failures[0]


def test_missing_pinned_version_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, packument(
        {"9.9.9": {"dist": {"integrity": "sha512-other=="}}}, latest="9.9.9"
    ))

    _row, failures, _notices = checker.check_package("demo", PINNED)

    assert any("在 registry 上不存在" in problem for problem in failures)


def test_absent_integrity_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub(monkeypatch, packument({"1.2.3": {"dist": {}}}))

    _row, failures, _notices = checker.check_package("demo", PINNED)

    assert any("未提供 integrity" in problem for problem in failures)


def test_newer_registry_latest_is_only_a_notice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deliberate pins must not fail merely because upstream moved on."""
    _stub(monkeypatch, packument(
        {
            "1.2.3": {"dist": {"integrity": "sha512-expected=="}},
            "1.3.0": {"dist": {"integrity": "sha512-newer=="}},
        },
        latest="1.3.0",
    ))

    _row, failures, notices = checker.check_package("demo", PINNED)

    assert failures == []
    assert any("registry latest 为 1.3.0" in note for note in notices)


def test_stable_release_for_prerelease_pin_is_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pinned = dict(PINNED, version="0.1.1-rc.2", stability="prerelease-only")
    _stub(monkeypatch, packument(
        {
            "0.1.1-rc.2": {"dist": {"integrity": "sha512-expected=="}},
            "0.2.0": {"dist": {"integrity": "sha512-stable=="}},
        },
        latest="0.1.1-rc.2",
    ))

    _row, failures, notices = checker.check_package("demo", pinned)

    assert failures == []
    assert any("已出现非预发布版本 0.2.0" in note for note in notices)


def test_malformed_registry_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub(monkeypatch, {"versions": "not-a-dict"})

    with pytest.raises(ValueError, match="versions/dist-tags"):
        checker.check_package("demo", PINNED)


def test_every_pinned_package_declares_verifiable_fields() -> None:
    """The gate is only meaningful if each entry carries an exact pin + digest."""
    from tokenplan_setup.domain import VERIFIED_TOOL_VERSIONS

    for package, pinned in VERIFIED_TOOL_VERSIONS.items():
        assert pinned["version"], package
        assert not pinned["version"].endswith("latest"), package
        assert pinned["integrity"].startswith("sha512-"), package
        assert pinned["stability"] in {"stable", "prerelease-only"}, package
