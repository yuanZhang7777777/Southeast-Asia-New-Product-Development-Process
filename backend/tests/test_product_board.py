import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.auth import default_password_for_name  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_product_board_keeps_one_group_with_owner_filtered_responsibilities() -> None:
    owner_a_claim, owner_b_claim = prepare_approved_group()
    set_claim_status(owner_a_claim, "waiting_secondary_research")
    set_claim_status(owner_b_claim, "waiting_listing")

    owner_a = client.get("/product-board?owner=Owner A")
    owner_b = client.get("/product-board?owner=Owner B")
    manager = client.get("/product-board")

    assert owner_a.status_code == 200
    assert owner_b.status_code == 200
    assert manager.status_code == 200
    assert [(g["main_sku"], len(g["responsibilities"])) for g in manager.json()] == [("MAIN-BOARD", 2)]
    assert manager.json()[0]["image_url"] == "/uploaded-sources/product-images/board.png"
    assert [(r["salesperson_name"], r["visible_status"]) for r in owner_a.json()[0]["responsibilities"]] == [
        ("Owner A", "waiting_secondary_research")
    ]
    assert [(r["salesperson_name"], r["visible_status"]) for r in owner_b.json()[0]["responsibilities"]] == [
        ("Owner B", "waiting_listing")
    ]
    assert "multi_owner" in manager.json()[0]["summary_tags"]


def test_product_board_owner_filter_includes_pending_assignment_tasks() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="selection1.xlsx",
            source_sheet="2026-W30",
            source_row=1,
            batch="2026-W30",
            site="PH",
            main_sku="MAIN-PENDING",
            main_sku_name="待认领主品",
            sub_sku="SUB-PENDING",
            sub_sku_name="待认领子品",
            current_status="assigned",
        )
        db.add(opportunity)
        db.flush()
        flow = models.FlowInstance(opportunity_id=opportunity.id, current_node="sales_claim", current_status="assigned")
        db.add(flow)
        db.flush()
        db.add(
            models.FlowTask(
                flow_instance_id=flow.id,
                node_code="sales_claim",
                task_type="sales_claim",
                assignee_name="Owner A",
            )
        )
        db.commit()

    response = client.get("/product-board?owner=Owner A")

    assert response.status_code == 200
    [group] = response.json()
    assert group["main_sku"] == "MAIN-PENDING"
    assert group["child_skus"][0]["visible_status"] == "assigned"
    assert group["responsibilities"] == [
        {
            "claim_record_id": None,
            "task_id": group["responsibilities"][0]["task_id"],
            "opportunity_id": group["child_skus"][0]["opportunity_id"],
            "salesperson_name": "Owner A",
            "sub_sku": "SUB-PENDING",
            "claim_daily_sales": None,
            "visible_status": "assigned",
            "arrival_detected_at": None,
        }
    ]


def test_product_board_operator_auth_forces_current_owner() -> None:
    prepare_approved_group()
    token = login("Owner A", "operator")

    response = client.get("/product-board?owner=Owner B", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert [r["salesperson_name"] for r in response.json()[0]["responsibilities"]] == ["Owner A"]


def test_product_board_filters_status_arrival_site_query_and_export_moves_claim_status() -> None:
    owner_a_claim, owner_b_claim = prepare_approved_group(site="PH")
    set_claim_status(owner_a_claim, "waiting_secondary_research", datetime(2026, 7, 10, tzinfo=timezone.utc))
    set_claim_status(owner_b_claim, "waiting_export")

    filtered = client.get(
        "/product-board",
        params={
            "visible_status": "waiting_secondary_research",
            "arrival_date_from": "2026-07-09",
            "arrival_date_to": "2026-07-11",
            "site": "PH",
            "query": "SUB-A",
        },
    )
    manager_token = login("Manager", "manager")
    request_ids = [row["request_id"] for row in client.get("/stocking/available-list").json()]
    export = client.post(
        "/stocking/available-list/export",
        headers={"Authorization": f"Bearer {manager_token}"},
        json={"request_ids": request_ids},
    )
    after_export = client.get("/product-board?owner=Owner B")

    assert filtered.status_code == 200
    assert [(r["claim_record_id"], r["visible_status"]) for r in filtered.json()[0]["responsibilities"]] == [
        (owner_a_claim, "waiting_secondary_research")
    ]
    assert export.status_code == 200
    assert after_export.json()[0]["responsibilities"][0]["claim_record_id"] == owner_b_claim
    assert after_export.json()[0]["responsibilities"][0]["visible_status"] == "waiting_arrival"


def test_product_board_isolates_same_sku_by_business_period() -> None:
    prepare_approved_group(period="2026-W29", sub_skus=("SUB-1",), owners=("Owner A",))
    prepare_approved_group(period="2026-W30", sub_skus=("SUB-1",), owners=("Owner A",))

    response = client.get("/product-board")

    assert response.status_code == 200
    assert [(group["business_period"], group["main_sku"]) for group in response.json()] == [
        ("2026-W29", "MAIN-BOARD"),
        ("2026-W30", "MAIN-BOARD"),
    ]


def test_product_board_hides_replaced_selection1_history_records() -> None:
    with SessionLocal() as db:
        db.add_all([
            models.NewProductOpportunity(
                source_type="selection1_developer_claim_feedback",
                source_file="selection1.xlsx",
                source_sheet="开发0623期",
                source_row=1,
                batch="开发0623期",
                site="PH",
                country="PH",
                main_sku="MAIN-REBUILD",
                sub_sku="SUB-1",
                current_status="historical_archive",
            ),
            models.NewProductOpportunity(
                source_type="history_selection1",
                source_file="old.xlsx",
                source_sheet="开发新品0623期",
                source_row=1,
                batch="开发0623期",
                site="PH",
                country="PH",
                main_sku="MAIN-REBUILD",
                sub_sku="SUB-1",
                current_status="replaced_by_normalized_selection1",
            ),
        ])
        db.commit()

    response = client.get("/product-board")

    assert response.status_code == 200
    [group] = response.json()
    assert group["main_sku"] == "MAIN-REBUILD"
    assert len(group["child_skus"]) == 1


def test_product_board_groups_same_sku_across_source_types() -> None:
    prepare_approved_group(
        sub_skus=("SUB-1", "SUB-2"),
        owners=("Owner A", "Owner B"),
        source_types=("selection1_developer_claim_feedback", "selection2_caigen_claim_feedback"),
    )

    response = client.get("/product-board")

    assert response.status_code == 200
    [group] = response.json()
    assert (group["business_period"], group["site"], group["main_sku"]) == ("2026-W29", "PH", "MAIN-BOARD")
    assert [child["sub_sku"] for child in group["child_skus"]] == ["SUB-1", "SUB-2"]
    assert [item["salesperson_name"] for item in group["responsibilities"]] == ["Owner A", "Owner B"]


def test_product_board_shows_historical_claim_relationships() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="history_selection1",
            source_file="selection1.xlsx",
            source_sheet="开发0414期",
            source_row=1,
            batch="开发0414期",
            site="PH",
            country="PH",
            main_sku="MAIN-HISTORY",
            main_sku_name="历史主品",
            sub_sku="SUB-HISTORY",
            sub_sku_name="历史子品",
            current_status="historical_archive",
        )
        db.add(opportunity)
        db.flush()
        db.add_all([
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name="历史运营甲",
                claim_result="claim",
                claim_daily_sales=0.5,
                source_column="history_selection1",
            ),
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name="历史运营乙",
                claim_result="reject",
                reject_reason="来源拒绝理由",
                source_column="history_selection1",
            ),
        ])
        db.commit()

    response = client.get("/product-board?business_period=开发0414期")

    assert response.status_code == 200
    [group] = response.json()
    assert group["main_sku"] == "MAIN-HISTORY"
    assert {
        (item["salesperson_name"], item["claim_daily_sales"], item["visible_status"])
        for item in group["responsibilities"]
    } == {
        ("历史运营甲", 0.5, "historical_archive"),
        ("历史运营乙", None, "historical_archive"),
    }


def prepare_approved_group(
    period: str = "2026-W29",
    site: str = "PH",
    sub_skus: tuple[str, ...] = ("SUB-A", "SUB-B"),
    owners: tuple[str, ...] = ("Owner A", "Owner B"),
    source_types: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    claim_ids: list[str] = []
    source_types = source_types or ("selection1_developer_claim_feedback",) * len(sub_skus)
    with SessionLocal() as db:
        for index, (sub_sku, owner, source_type) in enumerate(zip(sub_skus, owners, source_types), start=1):
            opportunity = models.NewProductOpportunity(
                source_type=source_type,
                source_file="selection1.xlsx",
                source_sheet=period,
                source_row=index,
                batch=period,
                country=site,
                site=site,
                keyword=f"{sub_sku} keyword",
                main_sku="MAIN-BOARD",
                main_sku_name="Board Main",
                image_url="/uploaded-sources/product-images/board.png" if index == 1 else None,
                sub_sku=sub_sku,
                sub_sku_name=f"{sub_sku} name",
            )
            db.add(opportunity)
            db.flush()
            claim = services.submit_claim(
                db,
                schemas.ClaimCreate(
                    opportunity_id=opportunity.id,
                    salesperson_name=owner,
                    claim_result="claim",
                    claim_daily_sales=index,
                ),
            )
            services.submit_review(
                db,
                schemas.ReviewCreate(
                    opportunity_id=opportunity.id,
                    claim_record_id=claim.id,
                    reviewer_name="Manager",
                    review_status="approved",
                ),
            )
            claim_ids.append(claim.id)
        db.commit()
    return tuple(claim_ids)


def set_claim_status(claim_id: str, status: str, arrived_at: datetime | None = None) -> None:
    with SessionLocal() as db:
        claim = db.get(models.SalesClaimForecast, claim_id)
        claim.downstream_status = status
        claim.arrival_detected_at = arrived_at
        if status == "waiting_export":
            request = db.query(models.StockingRequest).filter_by(claim_record_id=claim.id).one()
            request.status = "submitted"
        db.commit()


def login(name: str, role: str) -> str:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name=name, role=role, enabled=True))
        db.commit()
    response = client.post("/auth/login", json={"name": name, "password": default_password_for_name(name)})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_product_board_shows_sales_self_paused_and_listing_states() -> None:
    token = login("Owner A", "operator")
    created = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": "MAIN-SELF-BOARD",
            "country": "PH",
            "children": [
                {"sub_sku": "SUB-LIST", "inventory_available": True, "needs_stocking": False},
                {"sub_sku": "SUB-PAUSE", "inventory_available": False, "needs_stocking": False},
            ],
        },
    )

    response = client.get("/product-board", headers={"Authorization": f"Bearer {token}"})

    assert created.status_code == 200
    assert response.status_code == 200
    [group] = response.json()
    assert {item["visible_status"] for item in group["child_skus"]} == {"waiting_listing", "stocking_paused"}
    assert {item["visible_status"] for item in group["responsibilities"]} == {"waiting_listing", "stocking_paused"}
