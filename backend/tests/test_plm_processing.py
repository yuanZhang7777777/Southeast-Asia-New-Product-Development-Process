import os
import sys
from datetime import date, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_plm_processing.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openpyxl import Workbook  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app import models  # noqa: E402
from app.db import Base  # noqa: E402
from app import plm_processing  # noqa: E402
from app.plm_processing import process_plm_arrival_workbook  # noqa: E402

GROUP_EIGHT = "\u96c6\u56e2\u516b\u90e8"
GROUP_ONE = "\u96c6\u56e2\u4e00\u90e8"
SALES_A = "\u9500\u552eA"
SALES_B = "\u9500\u552eB"
PH = "\u83f2\u5f8b\u5bbe"
TH = "\u6cf0\u56fd"

engine = create_engine(os.environ["DATABASE_URL"])
SessionLocal = sessionmaker(bind=engine)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_plm_processing_persists_all_rows_and_dry_run_does_not_open_secondary_research(tmp_path: Path) -> None:
    workbook_path = tmp_path / "plm.xlsx"
    build_workbook(workbook_path)
    with SessionLocal() as db:
        opportunity, claim = make_claim(" sub-a ", "PH", SALES_A, "waiting_arrival")
        db.add_all([opportunity, claim])
        db.flush()
        add_stocking_export(db, opportunity, claim)

        db.commit()

        result = process_plm_arrival_workbook(
            db,
            workbook_path,
            "2026-07-12",
            source_file="plm.xlsx",
            bloc_name=GROUP_EIGHT,
            workflow_automation_enabled=False,
        )

        assert result["row_count"] == 4
        assert result["new_arrival_count"] == 2
        assert result["restock_count"] == 1
        assert result["unknown_count"] == 1
        assert result["matched_count"] == 1
        assert result["arrival_record_count"] == 0
        assert result["planned_responsibilities"] == [
            {
                "claim_record_id": claim.id,
                "opportunity_id": opportunity.id,
                "business_period": "2026-07-12",
                "salesperson_name": SALES_A,
                "site": "PH",
                "country": "PH",
                "main_sku": "MAIN-1",
                "sub_sku": " sub-a ",
                "product_name": "new",
            }
        ]
        assert db.query(models.PlmArrivalBatch).count() == 1
        items = db.query(models.PlmArrivalItem).order_by(models.PlmArrivalItem.source_row).all()
        assert [item.arrival_type for item in items] == ["new_arrival", "restock", "unknown", "new_arrival"]
        assert [item.match_status for item in items] == ["matched_dry_run", "not_new_arrival", "not_new_arrival", "unmatched"]
        assert items[0].product_name == "new"
        assert items[0].raw_payload["_matched_claim_record_ids"] == [claim.id]
        assert db.get(models.SalesClaimForecast, claim.id).downstream_status == "waiting_arrival"
        assert db.query(models.ArrivalRecord).count() == 0


def test_plm_processing_automation_uses_utc_arrival_time_and_dedupes_source_hash(tmp_path: Path, monkeypatch) -> None:
    workbook_path = tmp_path / "plm.xlsx"
    build_workbook(workbook_path)
    opened_arrivals = []

    original_open_secondary_research = plm_processing.services.open_secondary_research

    def capture_open_secondary_research(db, claim_record_id, arrived_at=None):
        opened_arrivals.append(arrived_at)
        return original_open_secondary_research(db, claim_record_id, arrived_at)

    monkeypatch.setattr(plm_processing.services, "open_secondary_research", capture_open_secondary_research)

    with SessionLocal() as db:
        opportunity, claim = make_claim("SUB-A", "PH", SALES_A, "waiting_arrival")
        db.add_all([opportunity, claim])
        db.flush()
        add_stocking_export(db, opportunity, claim)

        db.commit()

        first = process_plm_arrival_workbook(
            db,
            workbook_path,
            "2026-07-12",
            source_file="plm.xlsx",
            bloc_name=GROUP_EIGHT,
            workflow_automation_enabled=True,
        )
        second = process_plm_arrival_workbook(
            db,
            workbook_path,
            "2026-07-12",
            source_file="plm.xlsx",
            bloc_name=GROUP_EIGHT,
            workflow_automation_enabled=True,
        )

        assert first["arrival_record_count"] == 1
        assert first["matched_count"] == 1
        assert second["status"] == "duplicate"
        assert second["planned_responsibilities"][0]["claim_record_id"] == claim.id
        assert db.query(models.PlmArrivalBatch).count() == 1
        assert db.query(models.PlmArrivalItem).count() == 4
        assert db.query(models.ArrivalRecord).count() == 1
        assert opened_arrivals[0].tzinfo == timezone.utc
        assert opened_arrivals[0].isoformat() == "2026-07-12T02:00:00+00:00"
        # SQLite drops tzinfo on roundtrip; the monkeypatch above asserts the pre-flush value is UTC-aware.
        assert db.query(models.ArrivalRecord).one().arrived_at.isoformat() == "2026-07-12T02:00:00"
        saved_claim = db.get(models.SalesClaimForecast, claim.id)
        assert saved_claim.downstream_status == "waiting_secondary_research"
        assert saved_claim.arrival_detected_at is not None


def test_plm_processing_exact_match_ignores_non_platform_claim(tmp_path: Path) -> None:
    workbook_path = tmp_path / "plm.xlsx"
    build_workbook(workbook_path)
    with SessionLocal() as db:
        opportunity, claim = make_claim("SUB-A", "PH", SALES_A, "waiting_arrival", source_column="CC:CH")
        db.add_all([opportunity, claim])
        db.flush()
        add_stocking_export(db, opportunity, claim)

        db.commit()

        result = process_plm_arrival_workbook(
            db,
            workbook_path,
            "2026-07-12",
            source_file="plm.xlsx",
            bloc_name=GROUP_EIGHT,
            workflow_automation_enabled=False,
        )

        assert result["matched_count"] == 0
        assert result["planned_responsibilities"] == []
        assert db.get(models.SalesClaimForecast, claim.id).downstream_status == "waiting_arrival"
        assert db.query(models.PlmArrivalItem).filter_by(matched_claim_record_id=claim.id).count() == 0


def test_plm_processing_automation_processes_same_exact_match_across_periods(tmp_path: Path) -> None:
    workbook_path = tmp_path / "plm.xlsx"
    build_workbook(workbook_path)
    with SessionLocal() as db:
        claims = []
        for period in ["2026-W28", "2026-W29"]:
            opportunity, claim = make_claim("SUB-A", "PH", SALES_A, "waiting_arrival", business_period=period)
            db.add_all([opportunity, claim])
            db.flush()
            add_stocking_export(db, opportunity, claim)

            claims.append(claim)
        db.commit()

        result = process_plm_arrival_workbook(
            db,
            workbook_path,
            "2026-07-12",
            source_file="plm.xlsx",
            bloc_name=GROUP_EIGHT,
            workflow_automation_enabled=True,
        )

        assert result["arrival_record_count"] == 2
        assert result["matched_count"] == 2
        assert sorted(item["business_period"] for item in result["planned_responsibilities"]) == ["2026-W28", "2026-W29"]
        assert db.query(models.ArrivalRecord).count() == 2
        assert {record.claim_record_id for record in db.query(models.ArrivalRecord).all()} == {claim.id for claim in claims}
        assert {db.get(models.SalesClaimForecast, claim.id).downstream_status for claim in claims} == {
            "waiting_secondary_research"
        }


def build_workbook(path: Path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(
        [
            "\u5546\u54c1\u540d\u79f0",
            "\u56fd\u5bb6",
            "\u5b50SKU",
            "\u4e3bSKU",
            "\u9500\u552e\u5458",
            "\u96c6\u56e2",
            "\u6d77\u5916\u4ed3",
            "\u6700\u540e\u4e00\u6b21\u5165\u5e93\u65f6\u95f4",
            "\u9996\u6b21\u4e0a\u67b6\u65f6\u95f4",
            "\u6d77\u5916\u4ed3\u53ef\u53d1",
            "\u771f\u4ed3\u5e93\u5b58",
        ]
    )
    sheet.append(["new", PH, " SUB-A ", "MAIN-1", f" {SALES_A} ", GROUP_EIGHT, "PH\u4ed3", "2026-07-12 10:00:00", "2026-07-12 00:00:00", 12, 30])
    sheet.append(["restock", PH, "SUB-B", "MAIN-2", SALES_A, GROUP_EIGHT, "PH\u4ed3", "2026-07-12 11:00:00", "2026-07-01", 3, 8])
    sheet.append(["unknown", TH, "SUB-C", "MAIN-3", SALES_B, GROUP_EIGHT, "TH\u4ed3", "2026-07-12 12:00:00", None, 4, 9])
    sheet.append(["wrong sales", PH, "SUB-A", "MAIN-1", SALES_B, GROUP_EIGHT, "PH\u4ed3", "2026-07-12 13:00:00", "2026-07-12", 5, 10])
    sheet.append(["other group", PH, "SUB-D", "MAIN-4", SALES_A, GROUP_ONE, "PH\u4ed3", "2026-07-12", "2026-07-12", 1, 1])
    workbook.save(path)


def make_claim(
    sub_sku: str,
    site: str,
    salesperson_name: str,
    downstream_status: str,
    source_column: str = "platform",
    business_period: str = "2026-07-12",
) -> tuple[models.NewProductOpportunity, models.SalesClaimForecast]:
    opportunity = models.NewProductOpportunity(
        id=models.new_id(),
        source_type="selection1_developer_claim_feedback",
        source_file="selection.xlsx",
        source_sheet="sheet",
        source_row=1,
        batch=business_period,
        country=site,
        site=site,
        main_sku="MAIN-1",
        sub_sku=sub_sku,
        current_status="claim_submitted",
        snapshot={},
    )
    claim = models.SalesClaimForecast(
        opportunity_id=opportunity.id,
        salesperson_name=salesperson_name,
        claim_result="claim",
        source_column=source_column,
        downstream_status=downstream_status,
    )
    return opportunity, claim


def add_stocking_export(db, opportunity, claim) -> None:
    request = models.StockingRequest(
        opportunity_id=opportunity.id, claim_record_id=claim.id, application_date=date(2026, 7, 17),
        request_type="initial", salesperson_name=claim.salesperson_name, main_sku=opportunity.main_sku,
        sub_sku=opportunity.sub_sku, daily_sales=1, quantity=30, status="exported",
    )
    db.add(request)
    db.flush()
    batch = models.ExportBatch(file_name="stocking.xlsx", scope="stocking_available", row_count=1)
    db.add(batch)
    db.flush()
    db.add(models.ExportRow(
        export_batch_id=batch.id, opportunity_id=opportunity.id, claim_record_id=claim.id,
        stocking_request_id=request.id, salesperson_name=claim.salesperson_name,
        main_sku=opportunity.main_sku, sub_sku=opportunity.sub_sku,
        claim_daily_sales=1, stocking_quantity=30, country=opportunity.country,
    ))

def test_plm_matches_only_waiting_arrival_with_real_stocking_request_export_and_no_review() -> None:
    row = {"sub_sku": "SUB-A", "country": "PH", "salesperson_name": SALES_A}
    with SessionLocal() as db:
        waiting_export = add_export_candidate(db, "waiting_export", "stocking_available")
        no_export_row = add_export_candidate(db, "waiting_arrival", None)
        traceability_only = add_export_candidate(db, "waiting_arrival", "traceability")
        sales_self = add_export_candidate(db, "waiting_arrival", "stocking_available", source_type="sales_self_selection")
        db.commit()

        matches = plm_processing._exact_claim_matches(db, row)

        assert [claim.id for claim, _ in matches] == [sales_self.id]
        assert waiting_export.id not in {claim.id for claim, _ in matches}
        assert no_export_row.id not in {claim.id for claim, _ in matches}
        assert traceability_only.id not in {claim.id for claim, _ in matches}
        assert db.query(models.ReviewRecord).count() == 0


def add_export_candidate(
    db, downstream_status: str, scope: str | None, *, source_type: str = "selection1_developer_claim_feedback",
) -> models.SalesClaimForecast:
    opportunity, claim = make_claim("SUB-A", "PH", SALES_A, downstream_status)
    opportunity.id = models.new_id()
    opportunity.source_type = source_type
    claim.opportunity_id = opportunity.id
    db.add_all([opportunity, claim])
    db.flush()
    request = models.StockingRequest(
        opportunity_id=opportunity.id, claim_record_id=claim.id, application_date=date(2026, 7, 17),
        request_type="initial", salesperson_name=SALES_A, main_sku=opportunity.main_sku,
        sub_sku=opportunity.sub_sku, daily_sales=1, quantity=30, status="exported",
    )
    db.add(request)
    db.flush()
    if scope:
        batch = models.ExportBatch(file_name=f"{scope}.xlsx", scope=scope, row_count=1)
        db.add(batch)
        db.flush()
        db.add(models.ExportRow(
            export_batch_id=batch.id, opportunity_id=opportunity.id, claim_record_id=claim.id,
            stocking_request_id=request.id, salesperson_name=SALES_A, main_sku=opportunity.main_sku,
            sub_sku=opportunity.sub_sku, claim_daily_sales=1, stocking_quantity=30, country="PH",
        ))
    return claim
