from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.models import RoleMapping


def settings(**values: object) -> Settings:
    defaults = {
        "app_env": "development",
        "database_url": "postgresql://test:pass@localhost/test",
        "auth_secret_key": "test-only-secret",
        "dingtalk_arrival_card_template_id": "pilot-template",
        "plm_base_url": "http://plm.example",
        "plm_username": "user",
        "plm_password": "password",
    }
    return Settings(**(defaults | values))

def preview_item(child: str, *, country: str = "菲律宾", arrival_type: str = "new_arrival", warehouse: str = "马尼拉仓") -> dict:
    return {
        "arrival_type": arrival_type,
        "country": country,
        "sub_sku": child,
        "main_sku": f"MAIN-{child}",
        "salesperson_name": "当前销售",
        "warehouse": warehouse,
        "product_name": "商品",
    }


def pilot_test_path(name: str) -> Path:
    path = Path('.codex_tmp') / name
    path.mkdir(parents=True, exist_ok=True)
    for file_name in ('watchlist.json', 'state.json'):
        (path / file_name).unlink(missing_ok=True)
    return path


def watch_record(child: str, country: str = "PH") -> dict:
    return {"country": country, "child_sku": child, "historical_claimants": ["历史认领人"]}


def test_build_matches_intersects_only_new_arrivals_and_normalizes() -> None:
    from app.historical_arrival_watch import build_matches

    matches = build_matches(
        "2026-07-21",
        {"items": [preview_item(" sku-1 ", country=" 菲律宾 ")]},
        {"records": [watch_record("SKU-1")]},
    )

    assert matches == [
        {
            "date": "2026-07-21",
            "country": "PH",
            "child_sku": "SKU-1",
            "main_sku": "MAIN- SKU-1",
            "salesperson_name": "当前销售",
            "warehouses": ["马尼拉仓"],
            "historical_claimants": ["历史认领人"],
        }
    ]


def test_build_matches_excludes_restock_unknown_and_unmatched() -> None:
    from app.historical_arrival_watch import build_matches

    matches = build_matches(
        "2026-07-21",
        {"items": [preview_item("YES"), preview_item("YES", arrival_type="restock"), preview_item("YES", arrival_type="unknown"), preview_item("NO")]},
        {"records": [watch_record("YES")]},
    )

    assert [match["child_sku"] for match in matches] == ["YES"]


def test_build_matches_merges_warehouses_and_is_deterministic() -> None:
    from app.historical_arrival_watch import build_matches

    matches = build_matches(
        "2026-07-21",
        {"items": [preview_item("SKU", warehouse="B仓"), preview_item("SKU", warehouse="A仓"), preview_item("SKU", warehouse="A仓")]},
        {"records": [watch_record("SKU")]},
    )

    assert matches[0]["warehouses"] == ["A仓", "B仓"]


def test_chunk_matches_splits_twenty_one_rows_into_two_cards() -> None:
    from app.historical_arrival_watch import chunk_matches

    chunks = chunk_matches([{"child_sku": str(index)} for index in range(21)])

    assert [len(chunk) for chunk in chunks] == [20, 1]


@pytest.mark.parametrize(
    ("mappings", "message"),
    [([], "no eligible"), ([RoleMapping(name="刘学城", role="super_admin", enabled=True, dingtalk_user_id="account:placeholder")], "no eligible"), ([RoleMapping(name="刘学城", role="super_admin", enabled=True, dingtalk_user_id="user-one"), RoleMapping(name="刘学城", role="super_admin", enabled=True, dingtalk_user_id="user-two")], "ambiguous")],
)
def test_resolve_receiver_rejects_missing_account_and_distinct_duplicates(mappings: list[RoleMapping], message: str) -> None:
    from app.historical_arrival_watch import resolve_receiver_from_mappings

    with pytest.raises(ValueError, match=message):
        resolve_receiver_from_mappings(mappings)


def test_resolve_receiver_accepts_duplicate_rows_with_same_id() -> None:
    from app.historical_arrival_watch import resolve_receiver_from_mappings

    receiver = resolve_receiver_from_mappings(
        [
            RoleMapping(name="刘学城", role="super_admin", enabled=True, dingtalk_user_id="user-private-id"),
            RoleMapping(name="刘学城", role="super_admin", enabled=True, dingtalk_user_id="user-private-id"),
        ]
    )

    assert receiver == "user-private-id"


@pytest.mark.parametrize("response", [{}, {"deliverResults": []}, {"deliverResults": [{"success": True}, {"success": False}]}])
def test_validate_delivery_response_requires_nonempty_all_success(response: dict) -> None:
    from app.historical_arrival_watch import validate_delivery_response

    with pytest.raises(RuntimeError, match="delivery"):
        validate_delivery_response(response)


def test_validate_delivery_response_accepts_all_success() -> None:
    from app.historical_arrival_watch import validate_delivery_response

    validate_delivery_response({"deliverResults": [{"success": True}]})


class FakeSender:
    def __init__(self, results: list[dict]) -> None:
        self.results = iter(results)
        self.cards = []

    def send_arrival_card(self, card):
        self.cards.append(card)
        return next(self.results)


class FakeSession:
    def __init__(self, mappings: list[RoleMapping]) -> None:
        self.mappings = mappings
        self.executed = False

    def execute(self, _statement):
        self.executed = True
        return type("Rows", (), {"scalars": lambda this: self.mappings})()


def test_run_pilot_retries_only_failed_card_and_keeps_stable_state(monkeypatch) -> None:
    tmp_path = pilot_test_path("pilot-retry")
    import app.historical_arrival_watch as pilot

    watchlist = tmp_path / "watchlist.json"
    state = tmp_path / "state.json"
    watchlist.write_text(json.dumps({"records": [watch_record(f"SKU-{index}") for index in range(21)]}), encoding="utf-8")
    monkeypatch.setattr(pilot, "download_plm_export", lambda *_args, **_kwargs: tmp_path / "plm.xlsx")
    monkeypatch.setattr(pilot, "parse_plm_arrival_preview", lambda *_args, **_kwargs: {"items": [preview_item(f"SKU-{index}") for index in range(21)]})
    session = FakeSession([RoleMapping(name="刘学城", role="super_admin", enabled=True, dingtalk_user_id="receiver-private-id")])
    first = FakeSender([{"deliverResults": [{"success": True}]}, {"deliverResults": [{"success": False}]}])

    with pytest.raises(RuntimeError, match="delivery"):
        pilot.run_pilot("2026-07-21", settings=settings(), watchlist_path=watchlist, state_path=state, session=session, sender=first)
    assert json.loads(state.read_text(encoding="utf-8"))["dates"]["2026-07-21"]["sent_cards"] == [0]

    retry = FakeSender([{"deliverResults": [{"success": True}]}])
    result = pilot.run_pilot("2026-07-21", settings=settings(), watchlist_path=watchlist, state_path=state, session=session, sender=retry)

    assert result["sent_cards"] == 1
    assert len(retry.cards) == 1
    assert retry.cards[0].out_track_id == "historical-arrival-pilot-2026-07-21-1"
    assert json.loads(state.read_text(encoding="utf-8"))["dates"]["2026-07-21"]["completed"] is True


def test_run_pilot_is_idempotent_and_zero_matches_complete(monkeypatch) -> None:
    tmp_path = pilot_test_path("pilot-idempotent")
    import app.historical_arrival_watch as pilot

    watchlist = tmp_path / "watchlist.json"
    state = tmp_path / "state.json"
    watchlist.write_text(json.dumps({"records": [watch_record("SKU")]}), encoding="utf-8")
    monkeypatch.setattr(pilot, "download_plm_export", lambda *_args, **_kwargs: tmp_path / "plm.xlsx")
    monkeypatch.setattr(pilot, "parse_plm_arrival_preview", lambda *_args, **_kwargs: {"items": [preview_item("SKU")]})
    session = FakeSession([RoleMapping(name="刘学城", role="super_admin", enabled=True, dingtalk_user_id="receiver-private-id")])
    sender = FakeSender([{"deliverResults": [{"success": True}]}])

    pilot.run_pilot("2026-07-21", settings=settings(), watchlist_path=watchlist, state_path=state, session=session, sender=sender)
    result = pilot.run_pilot("2026-07-21", settings=settings(), watchlist_path=watchlist, state_path=state, session=session, sender=sender)
    assert result["sent_cards"] == 0
    assert len(sender.cards) == 1

    monkeypatch.setattr(pilot, "parse_plm_arrival_preview", lambda *_args, **_kwargs: {"items": []})
    zero = pilot.run_pilot("2026-07-22", settings=settings(), watchlist_path=watchlist, state_path=state, session=session, sender=sender)
    assert zero == {"date": "2026-07-22", "matched_rows": 0, "sent_cards": 0, "completed": True}
    assert json.loads(state.read_text(encoding="utf-8"))["dates"]["2026-07-22"]["completed"] is True


def test_preview_only_neither_sends_nor_mutates_state(monkeypatch) -> None:
    tmp_path = pilot_test_path("pilot-preview")
    import app.historical_arrival_watch as pilot

    watchlist = tmp_path / "watchlist.json"
    state = tmp_path / "state.json"
    watchlist.write_text(json.dumps({"records": [watch_record("SKU")]}), encoding="utf-8")
    monkeypatch.setattr(pilot, "download_plm_export", lambda *_args, **_kwargs: tmp_path / "plm.xlsx")
    monkeypatch.setattr(pilot, "parse_plm_arrival_preview", lambda *_args, **_kwargs: {"items": [preview_item("SKU")]})
    sender = FakeSender([])

    result = pilot.run_pilot("2026-07-21", settings=settings(), watchlist_path=watchlist, state_path=state, preview_only=True, sender=sender)

    assert result["matched_rows"] == 1
    assert sender.cards == []
    assert not state.exists()


@pytest.mark.parametrize(
    "values",
    [
        {"app_env": "local"},
        {"plm_sync_enabled": True},
        {"workflow_automation_enabled": True},
        {"dingtalk_card_autosend_enabled": True},
        {"dingtalk_arrival_card_template_id": " "},
    ],
)
def test_validate_settings_requires_development_disabled_global_switches_and_template(values: dict) -> None:
    from app.historical_arrival_watch import validate_settings

    with pytest.raises(ValueError):
        validate_settings(settings(**values))



