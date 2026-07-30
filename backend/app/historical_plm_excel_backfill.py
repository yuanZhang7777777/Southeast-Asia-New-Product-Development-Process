from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.config import Settings
from app.plm_arrivals import DEFAULT_BLOC_NAME, parse_plm_arrival_preview
from app.plm_download import download_plm_export


def build_plm_excel_history(
    workbooks: list[tuple[str, Path]],
    *,
    bloc_name: str = DEFAULT_BLOC_NAME,
    failed_dates: list[str] | None = None,
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    item_count = 0
    for date_text, workbook in workbooks:
        preview = parse_plm_arrival_preview(workbook, date_text, bloc_name=bloc_name)
        for item in preview["items"]:
            country = _norm(item.get("country"))
            sub_sku = _norm(item.get("sub_sku"))
            if not country or not sub_sku:
                continue
            row = {**item, "arrival_date": date_text, "source_file": str(workbook)}
            grouped[(country, sub_sku)].append(row)
            item_count += 1

    matches: list[dict[str, Any]] = []
    new_arrival_matches: list[dict[str, Any]] = []
    hard_conflicts: list[dict[str, Any]] = []
    for (country, sub_sku), rows in sorted(grouped.items()):
        rows.sort(key=lambda row: (str(row.get("latest_storage_time") or ""), str(row.get("arrival_date") or "")))
        latest = rows[-1]
        salespeople = sorted({str(row.get("salesperson_name") or "").strip() for row in rows if row.get("salesperson_name")})
        match = {
            "country": country,
            "sub_sku": sub_sku,
            "main_sku": _norm(latest.get("main_sku")),
            "salesperson_name": latest.get("salesperson_name"),
            "arrival_date": latest.get("arrival_date"),
            "latest_storage_time": latest.get("latest_storage_time"),
            "first_listing_time": latest.get("first_listing_time"),
            "arrival_type": latest.get("arrival_type"),
            "warehouse": latest.get("warehouse"),
            "available_quantity": latest.get("available_quantity"),
            "real_stock_quantity": latest.get("real_stock_quantity"),
            "daily_sales": latest.get("daily_sales"),
            "source_file": latest.get("source_file"),
            "source_row": latest.get("source_row"),
            "salespeople": salespeople,
        }
        matches.append(match)
        new_arrival = next((row for row in reversed(rows) if row.get("arrival_type") == "new_arrival"), None)
        if new_arrival:
            new_arrival_matches.append({
                **match,
                "main_sku": _norm(new_arrival.get("main_sku")),
                "salesperson_name": new_arrival.get("salesperson_name"),
                "arrival_date": new_arrival.get("arrival_date"),
                "latest_storage_time": new_arrival.get("latest_storage_time"),
                "first_listing_time": new_arrival.get("first_listing_time"),
                "arrival_type": new_arrival.get("arrival_type"),
                "warehouse": new_arrival.get("warehouse"),
                "available_quantity": new_arrival.get("available_quantity"),
                "real_stock_quantity": new_arrival.get("real_stock_quantity"),
                "daily_sales": new_arrival.get("daily_sales"),
                "source_file": new_arrival.get("source_file"),
                "source_row": new_arrival.get("source_row"),
            })
        if len(salespeople) > 1:
            hard_conflicts.append(match)

    return {
        "summary": {
            "date_count": len(workbooks) + len(failed_dates or []),
            "downloaded_workbook_count": len(workbooks),
            "item_count": item_count,
            "unique_key_count": len(matches),
            "new_arrival_key_count": len(new_arrival_matches),
            "multi_salesperson_key_count": len(hard_conflicts),
            "failed_date_count": len(failed_dates or []),
        },
        "matches": matches,
        "new_arrival_matches": new_arrival_matches,
        "hard_conflicts": hard_conflicts,
        "failed_dates": failed_dates or [],
    }


def download_plm_excel_history(
    start_date: date,
    end_date: date,
    *,
    settings: Settings,
    cache_dir: str | Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    workbooks: list[tuple[str, Path]] = []
    failed_dates: list[str] = []
    for date_text in _date_texts(start_date, end_date):
        try:
            workbook = download_plm_export(
                date_text,
                base_url=settings.plm_base_url,
                username=settings.plm_username,
                password=settings.plm_password,
                bloc_name=settings.plm_bloc_name,
                cache_dir=cache_dir or settings.plm_cache_dir,
                force=force,
            )
        except Exception:
            failed_dates.append(date_text)
            continue
        workbooks.append((date_text, workbook))
    return build_plm_excel_history(workbooks, bloc_name=settings.plm_bloc_name, failed_dates=failed_dates)


def _date_texts(start_date: date, end_date: date) -> list[str]:
    days: list[str] = []
    current = start_date
    while current <= end_date:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _norm(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)

    result = download_plm_excel_history(
        date.fromisoformat(args.start_date),
        date.fromisoformat(args.end_date),
        settings=Settings(),
        cache_dir=args.cache_dir,
        force=args.force,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
