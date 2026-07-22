from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal
from app.dingtalk_card_sender import ArrivalCard, DingTalkCardConfig, DingTalkCardSender, masked_dingtalk_user_id
from app.models import RoleMapping
from app.plm_arrivals import parse_plm_arrival_preview
from app.plm_download import download_plm_export, previous_beijing_date
from app.services import dingtalk_action_url
from app.site_codes import normalize_site_code


DEFAULT_WATCHLIST = Path("/data/plm/historical-watchlist.json")
DEFAULT_STATE = Path("/data/plm/historical-arrival-pilot-state.json")
CARD_SIZE = 20
RECEIVER_NAME = "刘学城"


def validate_settings(settings: Settings) -> None:
    if settings.app_env != "development":
        raise ValueError("historical arrival pilot requires development app_env")
    if settings.plm_sync_enabled or settings.workflow_automation_enabled or settings.dingtalk_card_autosend_enabled:
        raise ValueError("historical arrival pilot requires global automation switches disabled")
    if not settings.dingtalk_arrival_card_template_id.strip():
        raise ValueError("historical arrival pilot requires an explicit arrival card template")


def normalize_sku(value: Any) -> str:
    return str(value or "").strip().upper()


def build_matches(date_text: str, preview: dict[str, Any], watchlist: dict[str, Any]) -> list[dict[str, Any]]:
    records = watchlist.get("records")
    if not isinstance(records, list):
        raise ValueError("watchlist records must be a list")
    keys = {
        (normalize_site_code(record.get("country")), normalize_sku(record.get("child_sku"))): record
        for record in records
        if isinstance(record, dict) and normalize_site_code(record.get("country")) and normalize_sku(record.get("child_sku"))
    }
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    items = preview.get("items") if isinstance(preview, dict) else None
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("arrival_type") != "new_arrival":
            continue
        country = normalize_site_code(item.get("country"))
        child_sku = normalize_sku(item.get("sub_sku"))
        salesperson = str(item.get("salesperson_name") or "").strip()
        if not country or not child_sku or not salesperson:
            continue
        historical = keys.get((country, child_sku))
        if historical is None:
            continue
        main_sku = normalize_sku(item.get("main_sku"))
        key = (date_text, country, child_sku, salesperson)
        match = grouped.setdefault(
            key,
            {
                "date": date_text,
                "country": country,
                "child_sku": child_sku,
                "main_sku": main_sku,
                "salesperson_name": salesperson,
                "warehouses": set(),
                "historical_claimants": sorted({str(name).strip() for name in historical.get("historical_claimants", []) if str(name).strip()}),
            },
        )
        if main_sku and (not match["main_sku"] or main_sku < match["main_sku"]):
            match["main_sku"] = main_sku
        warehouse = str(item.get("warehouse") or "").strip()
        if warehouse:
            match["warehouses"].add(warehouse)
    return [
        {**match, "warehouses": sorted(match["warehouses"])}
        for _, match in sorted(grouped.items())
    ]


def chunk_matches(matches: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [matches[index : index + CARD_SIZE] for index in range(0, len(matches), CARD_SIZE)]


def resolve_receiver_from_mappings(mappings: Iterable[RoleMapping]) -> str:
    receiver_ids = {
        value
        for mapping in mappings
        if mapping.enabled
        for value in [str(mapping.dingtalk_user_id or "").strip()]
        if value and not value.lower().startswith("account:")
    }
    if not receiver_ids:
        raise ValueError("no eligible pilot receiver")
    if len(receiver_ids) != 1:
        raise ValueError("ambiguous pilot receiver")
    return next(iter(receiver_ids))


def resolve_receiver(session: Session) -> str:
    mappings = session.execute(
        select(RoleMapping).where(
            RoleMapping.enabled.is_(True), RoleMapping.name == RECEIVER_NAME, RoleMapping.role == "super_admin"
        )
    ).scalars()
    return resolve_receiver_from_mappings(mappings)


def validate_delivery_response(response: Any) -> None:
    results = response.get("deliverResults") if isinstance(response, dict) else None
    if not isinstance(results, list) or not results or any(not isinstance(result, dict) or result.get("success") is not True for result in results):
        raise RuntimeError("DingTalk delivery response was not fully successful")


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RuntimeError("historical arrival pilot state could not be read") from exc
    if not isinstance(value, dict):
        raise RuntimeError("historical arrival pilot state is invalid")
    return value


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f"{path.name}.part")
    try:
        partial.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(partial, path)
    except OSError as exc:
        raise RuntimeError("historical arrival pilot state could not be written") from exc


def card_markdown(matches: list[dict[str, Any]]) -> str:
    return "\n".join(
        f"{index}. {item['country']}｜{item['main_sku']}｜{item['child_sku']}｜当前销售：{item['salesperson_name']}｜仓库：{'、'.join(item['warehouses'])}"
        for index, item in enumerate(matches, start=1)
    )


def pilot_sender(settings: Settings) -> DingTalkCardSender:
    return DingTalkCardSender(
        DingTalkCardConfig(
            client_id=settings.dingtalk_client_id,
            client_secret=settings.dingtalk_client_secret,
            robot_code=settings.dingtalk_robot_code or settings.dingtalk_client_id,
            arrival_card_template_id=settings.dingtalk_arrival_card_template_id.strip(),
        )
    )


def run_pilot(
    date_text: str,
    *,
    settings: Settings,
    watchlist_path: Path = DEFAULT_WATCHLIST,
    state_path: Path = DEFAULT_STATE,
    download_only: bool = False,
    preview_only: bool = False,
    force_download: bool = False,
    session: Session | None = None,
    sender: DingTalkCardSender | Any | None = None,
) -> dict[str, Any]:
    validate_settings(settings)
    workbook = download_plm_export(
        date_text,
        base_url=settings.plm_base_url,
        username=settings.plm_username,
        password=settings.plm_password,
        bloc_name=settings.plm_bloc_name,
        cache_dir=settings.plm_cache_dir,
        force=force_download,
    )
    if download_only:
        return {"date": date_text, "downloaded": True}
    watchlist = load_json(watchlist_path, {})
    matches = build_matches(date_text, parse_plm_arrival_preview(workbook, date_text, settings.plm_bloc_name), watchlist)
    if preview_only:
        return {"date": date_text, "matched_rows": len(matches), "preview_only": True}
    state = load_json(state_path, {"dates": {}})
    dates = state.setdefault("dates", {})
    if not isinstance(dates, dict):
        raise RuntimeError("historical arrival pilot state is invalid")
    day_state = dates.setdefault(date_text, {"sent_cards": [], "completed": False})
    if not isinstance(day_state, dict) or not isinstance(day_state.get("sent_cards"), list):
        raise RuntimeError("historical arrival pilot state is invalid")
    if day_state.get("completed"):
        return {"date": date_text, "matched_rows": len(matches), "sent_cards": 0, "completed": True}
    chunks = chunk_matches(matches)
    if not chunks:
        day_state["completed"] = True
        save_state(state_path, state)
        return {"date": date_text, "matched_rows": 0, "sent_cards": 0, "completed": True}
    if session is None:
        raise ValueError("historical arrival pilot requires a read-only database session")
    receiver = resolve_receiver(session)
    active_sender = sender or pilot_sender(settings)
    sent_cards = 0
    sent_indexes = {int(index) for index in day_state["sent_cards"] if isinstance(index, int)}
    for card_index, rows in enumerate(chunks):
        if card_index in sent_indexes:
            continue
        response = active_sender.send_arrival_card(
            ArrivalCard(
                receiver_dingtalk_user_id=receiver,
                arrival_date=date_text,
                salesperson_name="历史关注试运行",
                new_items=[],
                old_items=[],
                action_url=dingtalk_action_url(settings, "supervisor"),
                out_track_id=f"historical-arrival-pilot-{date_text}-{card_index}",
                card_title="历史关注 SKU 到货试运行",
                summary_text=f"{date_text} 历史关注 SKU 到货，共 {len(rows)} 条",
                left_label="本卡条数",
                left_count=len(rows),
                action_text="进入主管处理",
                sku_markdown=card_markdown(rows),
            )
        )
        validate_delivery_response(response)
        day_state["sent_cards"].append(card_index)
        day_state["sent_cards"] = sorted(set(day_state["sent_cards"]))
        save_state(state_path, state)
        sent_cards += 1
    day_state["completed"] = True
    save_state(state_path, state)
    return {"date": date_text, "matched_rows": len(matches), "sent_cards": sent_cards, "completed": True, "receiver": masked_dingtalk_user_id(receiver)}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Development-only historical arrival card pilot.")
    parser.add_argument("--date", default=previous_beijing_date())
    parser.add_argument("--watchlist", type=Path, default=DEFAULT_WATCHLIST)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--preview-only", action="store_true")
    parser.add_argument("--force-download", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = get_settings()
        parameters = {
            "settings": settings,
            "watchlist_path": args.watchlist,
            "state_path": args.state,
            "download_only": args.download_only,
            "preview_only": args.preview_only,
            "force_download": args.force_download,
        }
        if args.download_only or args.preview_only:
            summary = run_pilot(args.date, **parameters)
        else:
            with SessionLocal() as session:
                summary = run_pilot(args.date, session=session, **parameters)
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception:
        print("historical arrival pilot failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


