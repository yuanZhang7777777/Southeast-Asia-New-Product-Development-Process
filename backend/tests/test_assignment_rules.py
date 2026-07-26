import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_assignment_rules_filter_site_then_report_category_match() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="站点匹配",
            key_site="PH",
            key_category1="汽摩配",
            key_category2="家居厨卫",
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="低负载品类匹配",
            key_site="TH",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        ),
    ]
    opportunities = [
        opportunity("MAIN-SITE", "SUB-1", "PH", "家居厨卫"),
        opportunity("MAIN-SITE", "SUB-2", "PH", "家居厨卫"),
        opportunity("MAIN-CATEGORY", "SUB-3", "MY", "汽摩配"),
    ]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)

    by_main_sku = {item.main_sku: item for item in suggestions}
    assert by_main_sku["MAIN-SITE"].suggested_assignee == "站点匹配"
    assert by_main_sku["MAIN-SITE"].match_reason == "重点站点匹配；重点类目匹配"
    assert by_main_sku["MAIN-CATEGORY"].suggested_assignee is None
    assert by_main_sku["MAIN-CATEGORY"].match_reason == "无站点匹配"


def test_assignment_rules_site_filter_beats_off_site_category_match() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="站点命中但品类不命中",
            key_site="TH",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="品类1命中",
            key_site="PH",
            key_category1="家居厨卫",
            key_category2="商办工业",
            enabled=True,
        ),
    ]
    opportunities = [opportunity("MAIN-HOME", "SUB-1", "TH", "家居厨卫")]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)

    assert suggestions[0].suggested_assignee == "站点命中但品类不命中"
    assert suggestions[0].match_reason == "重点站点匹配；品类未匹配；负载均衡"


def test_assignment_rules_normalize_common_category_aliases() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="汽摩配运营",
            key_site="TH",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        )
    ]
    opportunities = [opportunity("MAIN-AUTO", "SUB-1", "TH", "汽配与摩配")]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)

    assert suggestions[0].suggested_assignee == "汽摩配运营"
    assert suggestions[0].match_reason == "重点站点匹配；重点类目匹配"


def test_assignment_rules_normalize_chinese_and_custom_site_codes() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="泰国运营",
            key_site="TH",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="自定义站点运营",
            key_site="SG",
            key_category1="玩具",
            key_category2="家居厨卫",
            enabled=True,
        ),
    ]
    opportunities = [
        opportunity("MAIN-TH", "SUB-1", "泰国", "汽摩配"),
        opportunity("MAIN-SG", "SUB-2", "sg", "玩具"),
    ]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)

    by_main_sku = {item.main_sku: item for item in suggestions}
    assert by_main_sku["MAIN-TH"].suggested_assignee == "泰国运营"
    assert by_main_sku["MAIN-SG"].suggested_assignee == "自定义站点运营"


def test_assignment_rules_balance_load_after_site_filter() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="同站点A",
            key_site="PH",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="同站点B",
            key_site="PH",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        ),
    ]
    opportunities = [
        opportunity("MAIN-A", "SUB-1", "PH", "家居厨卫"),
        opportunity("MAIN-B", "SUB-2", "PH", "家居厨卫"),
    ]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)

    by_main_sku = {item.main_sku: item for item in suggestions}
    assert by_main_sku["MAIN-A"].suggested_assignee == "同站点A"
    assert by_main_sku["MAIN-A"].match_reason == "重点站点匹配；品类未匹配；负载均衡"
    assert by_main_sku["MAIN-B"].suggested_assignee == "同站点B"
    assert by_main_sku["MAIN-B"].match_reason == "重点站点匹配；品类未匹配；负载均衡"


def test_assignment_rules_split_same_main_sku_by_site() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="泰国运营",
            key_site="TH",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="越南运营",
            key_site="VN",
            key_category1="汽摩配",
            key_category2="户外运动",
            enabled=True,
        ),
    ]
    opportunities = [
        opportunity("MAIN-MIXED", "SUB-TH", "TH", "家居厨卫"),
        opportunity("MAIN-MIXED", "SUB-VN", "VN", "家居厨卫"),
    ]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)

    by_ids = {tuple(item.opportunity_ids): item for item in suggestions}
    assert by_ids[("SUB-TH",)].suggested_assignee == "泰国运营"
    assert by_ids[("SUB-VN",)].suggested_assignee == "越南运营"


def test_assignment_rules_prefer_lower_load_before_equal_category_matches() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="A-category2-heavy",
            key_site="PH",
            key_category1="Auto",
            key_category2="Home",
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="B-category1-light",
            key_site="PH",
            key_category1="Home",
            key_category2="Office",
            enabled=True,
        ),
    ]
    opportunities = [opportunity("MAIN-HOME", "SUB-1", "PH", "Home")]

    suggestions = preview_main_sku_assignment_groups(
        opportunities,
        profiles,
        initial_loads={"A-category2-heavy": 3},
    )

    assert suggestions[0].suggested_assignee == "B-category1-light"
    assert "重点类目" in suggestions[0].match_reason


def test_assignment_rules_balance_by_main_sku_group_not_sub_sku_count() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(operator_name="A", key_site="PH", key_category1="Home", key_category2="", enabled=True),
        SimpleNamespace(operator_name="B", key_site="PH", key_category1="Home", key_category2="", enabled=True),
    ]
    opportunities = [
        opportunity("MAIN-BIG", "BIG-1", "PH", "Home"),
        opportunity("MAIN-BIG", "BIG-2", "PH", "Home"),
        opportunity("MAIN-BIG", "BIG-3", "PH", "Home"),
        opportunity("MAIN-SMALL-1", "SMALL-1", "PH", "Home"),
        opportunity("MAIN-SMALL-2", "SMALL-2", "PH", "Home"),
    ]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)

    by_main_sku = {item.main_sku: item for item in suggestions}
    assert by_main_sku["MAIN-BIG"].suggested_assignee == "A"
    assert by_main_sku["MAIN-SMALL-1"].suggested_assignee == "B"
    assert by_main_sku["MAIN-SMALL-2"].suggested_assignee == "A"


def test_assignment_rules_use_priority_then_config_order_when_everything_else_ties() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="A-low-priority",
            key_site="PH",
            key_category1="Home",
            key_category2="",
            assignment_priority=0,
            display_order=1,
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="B-high-priority",
            key_site="PH",
            key_category1="Home",
            key_category2="",
            assignment_priority=10,
            display_order=2,
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="C-same-priority-later",
            key_site="PH",
            key_category1="Home",
            key_category2="",
            assignment_priority=10,
            display_order=3,
            enabled=True,
        ),
    ]

    suggestions = preview_main_sku_assignment_groups([opportunity("MAIN-PRIORITY", "SUB-1", "PH", "Home")], profiles)

    assert suggestions[0].suggested_assignee == "B-high-priority"


def test_assignment_rules_keep_category_and_priority_within_one_group_of_fair_load() -> None:
    from app.assignment_rules import preview_main_sku_assignment_groups

    profiles = [
        SimpleNamespace(
            operator_name="A-specialist-high-priority",
            key_site="PH",
            key_category1="Auto",
            key_category2="",
            assignment_priority=100,
            display_order=1,
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="B-generalist",
            key_site="PH",
            key_category1="Home",
            key_category2="",
            assignment_priority=0,
            display_order=2,
            enabled=True,
        ),
        SimpleNamespace(
            operator_name="C-generalist",
            key_site="PH",
            key_category1="Office",
            key_category2="",
            assignment_priority=0,
            display_order=3,
            enabled=True,
        ),
    ]
    opportunities = [opportunity(f"MAIN-{index}", f"SUB-{index}", "PH", "Auto") for index in range(7)]

    suggestions = preview_main_sku_assignment_groups(opportunities, profiles)
    loads = {profile.operator_name: 0 for profile in profiles}
    for item in suggestions:
        loads[item.suggested_assignee] += 1

    assert loads == {
        "A-specialist-high-priority": 3,
        "B-generalist": 2,
        "C-generalist": 2,
    }


def opportunity(main_sku: str, sub_sku: str, site: str, category: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=sub_sku,
        source_type="selection1_developer_claim_feedback",
        batch="2026W27",
        main_sku=main_sku,
        sub_sku=sub_sku,
        site=site,
        category_level1=category,
    )
