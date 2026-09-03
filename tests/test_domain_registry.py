"""Pure domain and registry contracts."""
from tokenplan_setup import adapters, domain


def test_plan_registry_is_complete_and_unique() -> None:
    plans = tuple(domain.PLAN_CATALOG.values())
    assert len(plans) == 9
    assert len({plan.choice for plan in plans}) == len(plans)
    assert len({plan.key for plan in plans}) == len(plans)
    assert set(domain.PLAN_BY_KEY) == {plan.key for plan in plans}


def test_tool_and_configurator_registries_are_aligned() -> None:
    assert len(domain.TOOLS) == 12
    assert set(domain.TOOL_BY_KEY) == {tool.key for tool in domain.TOOLS}
    assert set(adapters.CONFIGURATOR_REGISTRY) == set(adapters.CONFIG_SIGNATURES)
    assert set(adapters.CONFIGURATOR_REGISTRY) == set(domain.TOOL_BY_KEY)


def test_every_static_plan_has_a_valid_model_catalog() -> None:
    static_plans = {
        plan.key for plan in domain.PLAN_CATALOG.values()
        if plan.key not in {"postpaid", "postpaid-intl"}
    }
    assert static_plans <= set(domain.MODEL_CATALOG)
    for plan_key in static_plans:
        catalog = domain.MODEL_CATALOG[plan_key]
        assert catalog["default"]
        assert catalog["display"]
        assert all(":" in line for line in catalog["display"])


def test_install_specs_are_exactly_pinned() -> None:
    for tool in domain.TOOLS:
        for command in (tool.install_cmd, tool.install_cmd_win):
            if isinstance(command, tuple) and command[:3] == ("npm", "install", "-g"):
                package_spec = command[-1]
                assert package_spec.count("@") >= 1
                assert not package_spec.endswith("@latest")
                assert "--ignore-scripts" in command
