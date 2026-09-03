"""User-visible contracts for default and full model verification."""
from typing import List

import pytest

from tokenplan_setup import domain, flows


def test_default_verification_is_labeled_as_a_sample(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: List[str] = []
    monkeypatch.setattr(
        flows,
        "test_model",
        lambda _url, _key, model: (calls.append(model) or True, ""),
    )

    plan = domain.PLAN_BY_KEY["personal-hy"]
    flows.verify_models(plan.base_url, "secret", plan)

    output = capsys.readouterr().out
    hy_ids = flows.get_model_ids(plan.key)
    assert calls == ["hy3"]
    assert "默认模型抽样验证" in output
    # 目录会随官方上新而增减,断言跟随目录规模而不是写死数字
    assert f"仅验证默认模型 1/{len(hy_ids)}" in output
    assert f"其余 {len(hy_ids) - 1} 个模型未逐一验证" in output
    assert "全部 1 个模型验证通过" not in output


def test_all_verification_calls_every_catalog_model(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: List[str] = []
    monkeypatch.setattr(
        flows,
        "test_model",
        lambda _url, _key, model: (calls.append(model) or True, ""),
    )

    plan = domain.PLAN_BY_KEY["personal-hy"]
    expected = flows.get_model_ids(plan.key)
    flows.verify_models(plan.base_url, "secret", plan, mode="all")

    output = capsys.readouterr().out
    assert calls == expected
    assert "全量端到端验证" in output
    assert f"全部 {len(expected)} 个模型验证通过" in output
