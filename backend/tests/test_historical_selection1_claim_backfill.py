import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection1_claims.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_selection1_claim_backfill import (  # noqa: E402
    AUDIT_ACTION,
    CLAIM_SOURCE_COLUMN,
    REVERT_AUDIT_ACTION,
    backfill_selection1_claims,
    revert_selection1_claims,
)
from app.historical_selection1_import import SOURCE_TYPE  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def _cells(start_column_pairs: list[tuple[str, str, object]], group: str | None = "认领情况") -> dict:
    return {
        column: {"header": header, "group": group, "value": value}
        for column, header, value in start_column_pairs
    }


def _add_opportunity(db, *, sheet: str, sub_sku: str, source_row: int, cells: dict) -> None:
    db.add(
        models.NewProductOpportunity(
            source_type=SOURCE_TYPE,
            source_sheet=sheet,
            source_row=source_row,
            batch=sheet,
            main_sku=f"M-{sub_sku}",
            sub_sku=sub_sku,
            current_status="historical_archive",
            snapshot={
                "archive_type": "historical_selection1",
                "business_period": sheet,
                "fields_by_cell": {
                    "A": {"header": "站点", "group": None, "value": "菲律宾"},
                    **cells,
                },
            },
        )
    )


def seed_archive_rows() -> None:
    """两种列位变体（0428~0519 的 BT~BX 风格与 0526+ 的 BW~BZ 风格）各四种认领事实。"""
    with SessionLocal() as db:
        # 变体一：开发0428期，认领区 BT(分界)~BX：BU=不认领理由 BV=主销售员 BW=是否认领 BX=认领单销
        _add_opportunity(db, sheet="开发0428期", sub_sku="A428-CLAIM", source_row=3, cells=_cells([
            ("BV", "主销售员", "销售甲"), ("BW", "是否认领", "是"), ("BX", "认领单销", 0.5),
        ]))
        _add_opportunity(db, sheet="开发0428期", sub_sku="A428-REJECT", source_row=4, cells=_cells([
            ("BU", "不认领理由", "价格偏高，利润不足"), ("BV", "主销售员", "销售乙"), ("BW", "是否认领", "否"),
        ]))
        _add_opportunity(db, sheet="开发0428期", sub_sku="A428-NOSALES", source_row=5, cells=_cells([
            ("BW", "是否认领", "是"), ("BX", "认领单销", 1),
        ]))
        _add_opportunity(db, sheet="开发0428期", sub_sku="A428-FLAGLESS", source_row=6, cells=_cells([
            ("BV", "主销售员", "销售丙"), ("BX", "认领单销", 1.2),
        ]))
        # 主销售员有值但无是否认领/单销/理由 → ambiguous，不造数
        _add_opportunity(db, sheet="开发0428期", sub_sku="A428-AMBI", source_row=7, cells=_cells([
            ("BV", "主销售员", "销售丁"),
        ]))
        # 变体二：开发0526期，认领区 BW=不认领理由 BX=主销售员 BY=是否认领 BZ=认领单销
        _add_opportunity(db, sheet="开发0526期", sub_sku="B526-CLAIM", source_row=3, cells=_cells([
            ("BX", "主销售员", "销售甲"), ("BY", "是否认领", "是"), ("BZ", "认领单销", 0.5),
        ]))
        _add_opportunity(db, sheet="开发0526期", sub_sku="B526-REJECT", source_row=4, cells=_cells([
            ("BW", "不认领理由", "市场需求量过小"), ("BX", "主销售员", "销售戊"), ("BY", "是否认领", "不认领"),
        ]))
        _add_opportunity(db, sheet="开发0526期", sub_sku="B526-NOSALES", source_row=5, cells=_cells([
            ("BY", "是否认领", "否"),
        ]))
        _add_opportunity(db, sheet="开发0526期", sub_sku="B526-FLAGLESS", source_row=6, cells=_cells([
            ("BX", "主销售员", "销售己"), ("BZ", "认领单销", 2),
        ]))
        db.commit()


def seed_platform_flow_row() -> None:
    """现行流程机会 + platform 认领行：回填必须完全无视、revert 必须不删。"""
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_sheet="开发0721期",
            batch="开发0721期",
            main_sku="CUR-1",
            sub_sku="CUR-1A",
            current_status="assigned",
            snapshot={"fields_by_cell": {"BV": {"header": "主销售员", "group": None, "value": "现行销售"}}},
        )
        db.add(opportunity)
        db.flush()
        db.add(
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name="现行销售",
                claim_result="claim",
                claim_daily_sales=3.0,
                source_column="platform",
            )
        )
        db.commit()


EXPECTED_COUNTS = {"total": 9, "claim": 4, "reject": 2, "ambiguous": 1, "no_claim_info": 2, "skipped_existing": 0}


def test_dry_run_reports_and_writes_nothing() -> None:
    seed_archive_rows()
    seed_platform_flow_row()
    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=False)
        db.commit()
    assert report["would_create"] == 6
    assert {key: report[key] for key in EXPECTED_COUNTS} == EXPECTED_COUNTS
    assert report["by_period"]["开发0428期"] == {
        "rows": 5, "claim": 2, "reject": 1, "ambiguous": 1, "no_claim_info": 1, "skipped_existing": 0,
    }
    assert report["by_period"]["开发0526期"] == {
        "rows": 4, "claim": 2, "reject": 1, "ambiguous": 0, "no_claim_info": 1, "skipped_existing": 0,
    }
    with SessionLocal() as db:
        # 只剩 seed 的 platform 行，dry-run 不落任何库
        assert db.query(models.SalesClaimForecast).count() == 1
        assert db.query(models.AuditLog).count() == 0


def test_apply_creates_claim_rows_without_tasks_or_notifications() -> None:
    seed_archive_rows()
    seed_platform_flow_row()
    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()
    assert report["created"] == 6
    assert {key: report[key] for key in EXPECTED_COUNTS} == EXPECTED_COUNTS
    with SessionLocal() as db:
        claims = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).all()
        assert len(claims) == 6
        assert {claim.claim_source for claim in claims} == {CLAIM_SOURCE_COLUMN}
        by_sub = {
            db.get(models.NewProductOpportunity, claim.opportunity_id).sub_sku: claim for claim in claims
        }
        assert by_sub["A428-CLAIM"].salesperson_name == "销售甲"
        assert by_sub["A428-CLAIM"].claim_result == "claim"
        assert by_sub["A428-CLAIM"].claim_daily_sales == 0.5
        assert by_sub["A428-CLAIM"].reject_reason is None
        assert by_sub["A428-REJECT"].claim_result == "reject"
        assert by_sub["A428-REJECT"].claim_daily_sales is None
        assert by_sub["A428-REJECT"].reject_reason == "价格偏高，利润不足"
        assert by_sub["A428-FLAGLESS"].claim_result == "claim"
        assert by_sub["A428-FLAGLESS"].claim_daily_sales == 1.2
        assert by_sub["B526-REJECT"].claim_result == "reject"
        assert by_sub["B526-REJECT"].reject_reason == "市场需求量过小"
        assert by_sub["B526-FLAGLESS"].claim_result == "claim"
        assert by_sub["B526-FLAGLESS"].claim_daily_sales == 2.0
        # 红线：0 任务 0 流程 0 通知，档案状态不动，既有 platform 认领行不动
        assert db.query(models.FlowTask).count() == 0
        assert db.query(models.FlowInstance).count() == 0
        assert db.query(models.NotificationLog).count() == 0
        archive_rows = db.query(models.NewProductOpportunity).filter_by(source_type=SOURCE_TYPE).all()
        assert {row.current_status for row in archive_rows} == {"historical_archive"}
        platform = db.query(models.SalesClaimForecast).filter_by(source_column="platform").one()
        assert platform.salesperson_name == "现行销售"
        assert platform.claim_daily_sales == 3.0
        audit_entry = db.query(models.AuditLog).filter_by(action=AUDIT_ACTION).one()
        assert audit_entry.detail["created"] == 6


def test_rerun_is_idempotent() -> None:
    seed_archive_rows()
    with SessionLocal() as db:
        backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()
    with SessionLocal() as db:
        second = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()
    assert second["created"] == 0
    assert second["skipped_existing"] == 6
    # 未落行的 no_claim_info / ambiguous 每次重算，不属于 skipped_existing
    assert second["no_claim_info"] == 2
    assert second["ambiguous"] == 1
    with SessionLocal() as db:
        assert db.query(models.SalesClaimForecast).count() == 6


def test_revert_removes_only_unreferenced_backfill_rows() -> None:
    seed_archive_rows()
    seed_platform_flow_row()
    with SessionLocal() as db:
        backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()
    with SessionLocal() as db:
        report = revert_selection1_claims(db, actor="test")
        db.commit()
    assert report == {"reverted_claims": 6, "skipped_referenced": 0}
    with SessionLocal() as db:
        # platform 行保留，本模块行清零
        assert db.query(models.SalesClaimForecast).count() == 1
        assert db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).count() == 0
        assert db.query(models.AuditLog).filter_by(action=REVERT_AUDIT_ACTION).count() == 1
    # revert 后可重新回填
    with SessionLocal() as db:
        again = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()
    assert again["created"] == 6


def test_revert_skips_rows_referenced_by_arrival_record() -> None:
    seed_archive_rows()
    with SessionLocal() as db:
        backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()
    with SessionLocal() as db:
        claim = (
            db.query(models.SalesClaimForecast)
            .filter_by(source_column=CLAIM_SOURCE_COLUMN, salesperson_name="销售丙")
            .one()
        )
        db.add(
            models.ArrivalRecord(
                opportunity_id=claim.opportunity_id,
                claim_record_id=claim.id,
                salesperson_name=claim.salesperson_name,
            )
        )
        db.commit()
        referenced_claim_id = claim.id
    with SessionLocal() as db:
        report = revert_selection1_claims(db, actor="test")
        db.commit()
    assert report == {"reverted_claims": 5, "skipped_referenced": 1}
    with SessionLocal() as db:
        remaining = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).all()
        assert [claim.id for claim in remaining] == [referenced_claim_id]
