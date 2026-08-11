import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import opportunity_field_columns  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_manager_can_edit_current_sku_fields_without_rewriting_source_snapshot() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="selection1.xlsx",
            source_sheet="W27",
            source_row=1,
            batch="W27",
            main_sku="MAIN-OLD",
            sub_sku="SUB-OLD",
            main_sku_name="Old main",
            sub_sku_name="Old sub",
            snapshot={"fields_by_header": {"主SKU": "MAIN-OLD", "子SKU": "SUB-OLD"}},
        )
        db.add(opportunity)
        db.flush()
        db.add(
            models.SourceRecordSnapshot(
                opportunity_id=opportunity.id,
                source_file=opportunity.source_file,
                source_sheet=opportunity.source_sheet,
                source_row=opportunity.source_row,
                column_range="source",
                payload=opportunity.snapshot,
            )
        )
        db.commit()
        opportunity_id = opportunity.id

    response = client.patch(
        f"/opportunities/{opportunity_id}",
        json={
            "main_sku": "MAIN-NEW",
            "sub_sku": "SUB-NEW",
            "main_sku_name": "New main",
            "sub_sku_name": "New sub",
            "edit_reason": "source correction",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["main_sku"] == "MAIN-NEW"
    assert body["sub_sku"] == "SUB-NEW"

    with SessionLocal() as db:
        snapshot = db.query(models.SourceRecordSnapshot).one()
        audit = db.query(models.AuditLog).filter_by(action="opportunity.updated").one()

    assert snapshot.payload["fields_by_header"] == {"主SKU": "MAIN-OLD", "子SKU": "SUB-OLD"}
    assert audit.detail["before"]["main_sku"] == "MAIN-OLD"
    assert audit.detail["after"]["main_sku"] == "MAIN-NEW"
    assert audit.detail["reason"] == "source correction"


def test_sku_edit_requires_reason() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(source_type="test", main_sku="MAIN", sub_sku="SUB")
        db.add(opportunity)
        db.commit()
        opportunity_id = opportunity.id

    response = client.patch(f"/opportunities/{opportunity_id}", json={"main_sku": "MAIN-NEW", "edit_reason": " "})

    assert response.status_code == 400
    assert "reason" in response.json()["detail"]


def test_manager_can_edit_status_and_imported_parameters_without_rewriting_source_snapshot() -> None:
    original_snapshot = {
        "allowed_columns": ["A", "H", "J", "AJ", "AM"],
        "cells": {"A": "PH", "H": "MAIN", "J": "SUB", "AJ": 408, "AM": 0.08},
        "fields_by_column": {"A": "PH", "H": "MAIN", "J": "SUB", "AJ": 408, "AM": 0.08},
        "headers_by_column": {"AJ": ["稳定期定价 （PHP）"], "AM": ["稳定期利润率"]},
        "fields_by_header": {"稳定期定价（PHP）": 408, "稳定期利润率": 0.08},
        "pricing_snapshot": {"稳定期定价": 408, "稳定期利润率": 0.08},
    }
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            main_sku="MAIN",
            sub_sku="SUB",
            developer_department="产品开发一部",
            current_status="pending_assignment",
            snapshot=original_snapshot,
        )
        db.add(opportunity)
        db.flush()
        db.add(models.SourceRecordSnapshot(opportunity_id=opportunity.id, column_range="A:AM", payload=original_snapshot))
        db.commit()
        opportunity_id = opportunity.id

    response = client.patch(
        f"/opportunities/{opportunity_id}",
        json={
            "developer_department": "产品开发八部",
            "current_status": "open_claim_pool",
            "source_cells": {"AJ": 428, "AM": 0.0823262796879019},
            "edit_reason": "修正导入参数",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["developer_department"] == "产品开发八部"
    assert body["current_status"] == "open_claim_pool"
    assert body["snapshot"]["cells"]["AJ"] == 428
    assert body["snapshot"]["fields_by_header"]["稳定期利润率"] == 0.0823262796879019
    assert body["snapshot"]["pricing_snapshot"]["稳定期定价"] == 428

    with SessionLocal() as db:
        source_snapshot = db.query(models.SourceRecordSnapshot).one()
        audit = db.query(models.AuditLog).filter_by(action="opportunity.updated").one()

    assert source_snapshot.payload["cells"]["AJ"] == 408
    assert audit.detail["before"]["current_status"] == "pending_assignment"
    assert audit.detail["after"]["source_cells"]["AJ"] == 428


def test_manager_cannot_edit_unknown_source_column_or_disabled_status() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            main_sku="MAIN",
            sub_sku="SUB",
            snapshot={"allowed_columns": ["AJ"], "cells": {"AJ": 408}},
        )
        db.add(opportunity)
        db.commit()
        opportunity_id = opportunity.id

    unknown_column = client.patch(
        f"/opportunities/{opportunity_id}",
        json={"source_cells": {"ZZ": 1}, "edit_reason": "非法列"},
    )
    disabled_status = client.patch(
        f"/opportunities/{opportunity_id}",
        json={"current_status": "disabled", "edit_reason": "越权停用"},
    )
    unsupported_review_status = client.patch(
        f"/opportunities/{opportunity_id}",
        json={"current_status": "claim_submitted", "edit_reason": "无认领记录"},
    )

    assert unknown_column.status_code == 400
    assert "ZZ" in unknown_column.json()["detail"]
    assert disabled_status.status_code == 400
    assert "status" in disabled_status.json()["detail"]
    assert unsupported_review_status.status_code == 400
    assert "claim submission" in unsupported_review_status.json()["detail"]


def test_selection2_edit_syncs_its_own_spu_sku_and_name_columns() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection2_caigen_claim_feedback",
            main_sku="CG-MAIN",
            sub_sku="CG-SUB",
            main_sku_name="旧商品名",
            snapshot={
                "allowed_columns": ["A", "B", "D", "G"],
                "cells": {"A": "CG-MAIN", "B": "CG-SUB", "D": "旧商品名", "G": 20},
                "fields_by_column": {"A": "CG-MAIN", "B": "CG-SUB", "D": "旧商品名", "G": 20},
                "headers_by_column": {
                    "A": ["SPU"],
                    "B": ["SKU"],
                    "D": ["产品名称"],
                    "G": ["进价"],
                },
            },
        )
        db.add(opportunity)
        db.commit()
        opportunity_id = opportunity.id

    response = client.patch(
        f"/opportunities/{opportunity_id}",
        json={"main_sku_name": "新商品名", "source_cells": {"G": 21}, "edit_reason": "修正选品2参数"},
    )

    assert response.status_code == 200
    assert response.json()["snapshot"]["cells"] == {
        "A": "CG-MAIN",
        "B": "CG-SUB",
        "D": "新商品名",
        "G": 21,
    }


def test_selection1_field_columns_follow_729_standard_header() -> None:
    opportunity = models.NewProductOpportunity(source_type="selection1_developer_claim_feedback")

    assert opportunity_field_columns(opportunity) == {
        "site": "A",
        "developer_department": "B",
        "developer_name": "C",
        "category_level1": "D",
        "category_level2": "E",
        "keyword": "F",
        "image_url": "G",
        "main_sku_name": "H",
        "main_sku": "I",
        "sub_sku_name": "J",
        "sub_sku": "K",
        "product_type": "L",
        "reason": "M",
    }
