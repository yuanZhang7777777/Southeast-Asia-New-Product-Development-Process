import os
import sys
import json
import zipfile
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_historical_selection1_claims.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app import historical_central_import  # noqa: E402
from app import historical_selection1_claim_backfill as claim_backfill  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.historical_selection1_claim_backfill import (  # noqa: E402
    AUDIT_ACTION,
    CLAIM_SOURCE_COLUMN,
    REVERT_AUDIT_ACTION,
    backfill_selection1_claims,
    normalize_selection1_claims,
    revert_selection1_claims,
)
from app.historical_selection1_import import SOURCE_TYPE  # noqa: E402
from app.selection1_importer import SOURCE_TYPE as CURRENT_SELECTION1_SOURCE_TYPE  # noqa: E402


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
            ("BY", "销售反馈总结", "市场反馈已保留"),
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
        _add_opportunity(db, sheet="开发0526期", sub_sku="B526-ZERO", source_row=7, cells=_cells([
            ("BX", "主销售员", "销售庚"), ("BY", "是否认领", "是"), ("BZ", "认领单销", 0),
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


EXPECTED_COUNTS = {
    "total": 10,
    "claim": 4,
    "reject": 2,
    "zero_daily_sales": 1,
    "unclaimed": 1,
    "no_claim_info": 2,
    "skipped_existing": 0,
}


def test_dry_run_reports_and_writes_nothing() -> None:
    seed_archive_rows()
    seed_platform_flow_row()
    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=False)
        db.commit()
    assert report["would_create"] == 6
    assert {key: report[key] for key in EXPECTED_COUNTS} == EXPECTED_COUNTS
    assert report["by_period"]["开发0428期"] == {
        "rows": 5,
        "claim": 2,
        "reject": 1,
        "zero_daily_sales": 0,
        "unclaimed": 1,
        "invalid_value": 0,
        "no_claim_info": 1,
        "layout_mismatch": 0,
        "skipped_existing": 0,
    }
    assert report["by_period"]["开发0526期"] == {
        "rows": 5,
        "claim": 2,
        "reject": 1,
        "zero_daily_sales": 1,
        "unclaimed": 0,
        "invalid_value": 0,
        "no_claim_info": 1,
        "layout_mismatch": 0,
        "skipped_existing": 0,
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
        assert by_sub["A428-CLAIM"].feedback_summary == "市场反馈已保留"
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


def test_period_layout_uses_the_designated_claim_columns_not_an_earlier_duplicate_header() -> None:
    """开发0526期必须读取 BX/BY/BZ，不能误取前面同名的历史字段。"""
    with SessionLocal() as db:
        _add_opportunity(
            db,
            sheet="开发0526期",
            sub_sku="B526-LAYOUT",
            source_row=20,
            cells=_cells(
                [
                    ("B", "主销售员", "干扰销售"),
                    ("BX", "主销售员", "正确销售"),
                    ("BY", "是否认领", "是"),
                    ("BZ", "认领单销", 1),
                ]
            ),
        )
        db.commit()

    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()

    assert report["created"] == 1
    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).one()
        assert claim.salesperson_name == "正确销售"


def test_text_in_claim_daily_sales_is_preserved_as_a_historical_rejection_reason() -> None:
    with SessionLocal() as db:
        _add_opportunity(
            db,
            sheet="开发0526期",
            sub_sku="B526-TEXT-REJECT",
            source_row=21,
            cells=_cells(
                [
                    ("BX", "主销售员", "销售说明"),
                    ("BY", "是否认领", "否"),
                    ("BZ", "认领单销", "市场需求不足，暂不认领"),
                ]
            ),
        )
        db.commit()

    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()

    assert report["reject"] == 1
    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).one()
        assert claim.claim_result == "reject"
        assert claim.reject_reason == "市场需求不足，暂不认领"


def test_text_with_digits_in_daily_sales_is_rejection_not_claim() -> None:
    with SessionLocal() as db:
        _add_opportunity(
            db,
            sheet="开发0526期",
            sub_sku="B526-TEXT-DIGITS",
            source_row=22,
            cells=_cells(
                [
                    ("BX", "主销售员", "销售数字"),
                    ("BZ", "认领单销", "暂不认领，竞品100"),
                ]
            ),
        )
        db.commit()

    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()

    assert report["claim"] == 0
    assert report["reject"] == 1
    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).one()
        assert claim.claim_result == "reject"
        assert claim.claim_daily_sales is None
        assert claim.reject_reason == "暂不认领，竞品100"


def test_caigen_period_preserves_each_salesperson_claim_or_rejection() -> None:
    with SessionLocal() as db:
        _add_opportunity(
            db,
            sheet="开发0727期-财根",
            sub_sku="CAIGEN-MULTI",
            source_row=30,
            cells=_cells(
                [
                    ("CM", "销售员1", "销售甲"),
                    ("CN", "预估单销/拒绝理由", 1),
                    ("CO", "销售员2", "销售乙"),
                    ("CP", "预估单销/拒绝理由", "不认领，已有同类产品"),
                ]
            ),
        )
        db.commit()

    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()

    assert report["created"] == 2
    with SessionLocal() as db:
        claims = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).all()
        by_owner = {claim.salesperson_name: claim for claim in claims}
        assert by_owner["销售甲"].claim_daily_sales == 1
        assert by_owner["销售乙"].claim_result == "reject"
        assert by_owner["销售乙"].reject_reason == "不认领，已有同类产品"


def test_nested_historical_snapshot_backfills_without_changing_platform_claim() -> None:
    with SessionLocal() as db:
        db.add(
            models.NewProductOpportunity(
                source_type=CURRENT_SELECTION1_SOURCE_TYPE,
                source_sheet="开发0526期",
                source_row=50,
                batch="开发0526期",
                country="PH",
                site="PH",
                main_sku="CURRENT-MAIN",
                sub_sku="CURRENT-SUB",
                current_status="claim_submitted",
                snapshot={
                    "historical_selection1": {
                        "business_period": "开发0526期",
                        "source_reference": {"source_sheet": "开发0526期", "source_row": 50},
                        "fields_by_cell": _cells(
                            [("BX", "主销售员", "历史销售"), ("BY", "是否认领", "是"), ("BZ", "认领单销", 1)]
                        ),
                    }
                },
            )
        )
        db.flush()
        opportunity = db.query(models.NewProductOpportunity).one()
        db.add(
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name="现行销售",
                claim_result="claim",
                claim_daily_sales=2,
                source_column="platform",
            )
        )
        db.commit()

    with SessionLocal() as db:
        report = backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()

    assert report["created"] == 1
    with SessionLocal() as db:
        claims = db.query(models.SalesClaimForecast).all()
        assert {(claim.source_column, claim.salesperson_name) for claim in claims} == {
            ("platform", "现行销售"),
            (CLAIM_SOURCE_COLUMN, "历史销售"),
        }


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
    # 未落行的未认领事实每次重算，不属于 skipped_existing
    assert second["no_claim_info"] == 2
    assert second["zero_daily_sales"] == 1
    assert second["unclaimed"] == 1
    with SessionLocal() as db:
        assert db.query(models.SalesClaimForecast).count() == 6


def test_normalize_replaces_unreferenced_wrong_history_and_removes_stale_fact() -> None:
    seed_archive_rows()
    with SessionLocal() as db:
        reject_opportunity = db.query(models.NewProductOpportunity).filter_by(sub_sku="A428-REJECT").one()
        no_claim_opportunity = db.query(models.NewProductOpportunity).filter_by(sub_sku="A428-NOSALES").one()
        wrong = models.SalesClaimForecast(
            opportunity_id=reject_opportunity.id,
            salesperson_name="销售乙",
            claim_result="claim",
            claim_daily_sales=1,
            source_column=CLAIM_SOURCE_COLUMN,
        )
        stale = models.SalesClaimForecast(
            opportunity_id=no_claim_opportunity.id,
            salesperson_name="历史错误销售",
            claim_result="claim",
            claim_daily_sales=1,
            source_column=CLAIM_SOURCE_COLUMN,
        )
        db.add_all([wrong, stale])
        db.flush()
        wrong_id = wrong.id
        db.commit()

    with SessionLocal() as db:
        report = normalize_selection1_claims(db, apply=True, actor="test")
        db.commit()

    assert report == {"updated": 1, "deleted_extra": 1, "skipped_referenced": 0}
    with SessionLocal() as db:
        claims = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).all()
        assert [claim.id for claim in claims] == [wrong_id]
        assert claims[0].claim_result == "reject"
        assert claims[0].claim_daily_sales is None
        assert claims[0].reject_reason == "价格偏高，利润不足"
        assert db.query(models.FlowTask).count() == 0
        assert db.query(models.NotificationLog).count() == 0


def test_normalize_leaves_referenced_wrong_history_untouched() -> None:
    seed_archive_rows()
    with SessionLocal() as db:
        opportunity = db.query(models.NewProductOpportunity).filter_by(sub_sku="A428-REJECT").one()
        wrong = models.SalesClaimForecast(
            opportunity_id=opportunity.id,
            salesperson_name="销售乙",
            claim_result="claim",
            claim_daily_sales=1,
            source_column=CLAIM_SOURCE_COLUMN,
        )
        db.add(wrong)
        db.flush()
        db.add(
            models.ArrivalRecord(
                opportunity_id=opportunity.id,
                claim_record_id=wrong.id,
                salesperson_name="销售乙",
            )
        )
        db.commit()

    with SessionLocal() as db:
        report = normalize_selection1_claims(db, apply=True, actor="test")
        db.commit()

    assert report == {"updated": 0, "deleted_extra": 0, "skipped_referenced": 1}
    with SessionLocal() as db:
        claim = db.query(models.SalesClaimForecast).filter_by(source_column=CLAIM_SOURCE_COLUMN).one()
        assert claim.claim_result == "claim"
        assert claim.claim_daily_sales == 1


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


def test_sheet_image_anchors_keeps_the_excel_row_and_column(tmp_path: Path) -> None:
    workbook = tmp_path / "evidence.xlsx"
    _write_drawing_workbook(workbook)

    with zipfile.ZipFile(workbook) as archive:
        images = historical_central_import.sheet_image_anchors(archive, "开发0526期")

    assert images == {4: [(80, b"evidence-png", "png")]}


def test_evidence_manifest_can_preview_unwritten_historical_claims(tmp_path: Path) -> None:
    seed_archive_rows()
    workbook = tmp_path / "evidence.xlsx"
    _write_drawing_workbook(workbook)

    with SessionLocal() as db:
        manifest, report = claim_backfill.selection1_claim_evidence_manifest(db, workbook)

    assert report["target_rows"] == 6
    assert manifest == {
        ("开发0526期", 4): [{"column": "CB", "data": b"evidence-png", "ext": "png"}]
    }


def test_claim_evidence_backfill_attaches_only_feedback_or_note_images(monkeypatch) -> None:
    seed_archive_rows()
    with SessionLocal() as db:
        backfill_selection1_claims(db, apply=True, actor="test")
        db.commit()

    monkeypatch.setattr(
        claim_backfill,
        "upload_claim_evidence_image",
        lambda data, ext, opportunity_id, digest: f"https://oss.example/claim-evidence/{opportunity_id}/{digest}.{ext}",
    )
    source_images = {
        ("开发0526期", 4): [
            {"column": "CB", "data": b"feedback-image", "ext": "png"},
            {"column": "F", "data": b"product-image", "ext": "png"},
        ]
    }

    with SessionLocal() as db:
        report = claim_backfill.backfill_selection1_claim_evidence(db, source_images, apply=True, actor="test")
        db.commit()

    assert report["attached"] == 1
    assert report["skipped_non_evidence_column"] == 1
    assert report["failed_uploads"] == []
    with SessionLocal() as db:
        claim = (
            db.query(models.SalesClaimForecast)
            .filter_by(source_column=CLAIM_SOURCE_COLUMN, salesperson_name="销售戊")
            .one()
        )
        metadata = json.loads(claim.note or "{}")
        assert metadata["evidence_images"] == [
            {
                "name": "开发0526期!CB4.png",
                "source_column": "CB",
                "source_row": 4,
                "source_sheet": "开发0526期",
                "type": "image/png",
                "url": metadata["evidence_images"][0]["url"],
            }
        ]
        assert metadata["evidence_images"][0]["url"].startswith("https://oss.example/claim-evidence/")
        assert db.query(models.FlowTask).count() == 0
        assert db.query(models.NotificationLog).count() == 0

    with SessionLocal() as db:
        repeated = claim_backfill.backfill_selection1_claim_evidence(db, source_images, apply=True, actor="test")
        db.commit()
    assert repeated["attached"] == 0
    assert repeated["already_attached"] == 1


def test_claim_evidence_bundle_round_trips_only_traceable_images(tmp_path: Path) -> None:
    bundle = tmp_path / "claim-evidence.zip"
    source_images = {
        ("开发0526期", 4): [{"column": "CB", "data": b"feedback-image", "ext": "png"}],
        ("开发0526期", 5): [{"column": "CA", "data": b"same-image", "ext": "jpg"}],
    }

    report = claim_backfill.write_selection1_claim_evidence_bundle(bundle, source_images)
    restored = claim_backfill.read_selection1_claim_evidence_bundle(bundle)

    assert report == {"images": 2, "source_rows": 2}
    assert restored == source_images


def _write_drawing_workbook(path: Path) -> None:
    """Small OOXML fixture: CB4 anchored image without loading an Excel application."""
    files = {
        "xl/workbook.xml": """<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><sheets><sheet name=\"开发0526期\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>""",
        "xl/_rels/workbook.xml.rels": """<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/></Relationships>""",
        "xl/worksheets/_rels/sheet1.xml.rels": """<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/drawing\" Target=\"../drawings/drawing1.xml\"/></Relationships>""",
        "xl/drawings/_rels/drawing1.xml.rels": """<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" Target=\"../media/image1.png\"/></Relationships>""",
        "xl/drawings/drawing1.xml": """<xdr:wsDr xmlns:xdr=\"http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing\" xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><xdr:oneCellAnchor><xdr:from><xdr:col>79</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>3</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:pic><xdr:blipFill><a:blip r:embed=\"rId1\"/></xdr:blipFill></xdr:pic></xdr:oneCellAnchor></xdr:wsDr>""",
        "xl/media/image1.png": b"evidence-png",
    }
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
