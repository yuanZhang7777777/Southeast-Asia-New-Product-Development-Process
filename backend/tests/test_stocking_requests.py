import os
import sys
from datetime import datetime
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.auth import default_password_for_name  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app import workflow_status  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_stocking_calculations_use_ceil_and_exact_totals() -> None:
    assert services.stocking_quantity(2) == 60
    assert services.stocking_quantity(2.01) == 61

    amount, volume = services.stocking_totals(12.5, 0.002, 61)

    assert amount == 762.5
    assert volume == 0.122


def test_stocking_draft_is_unique_per_claim() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection1_developer_claim_feedback",
            source_file="selection1.xlsx",
            source_sheet="period-1",
            source_row=2,
            country="PH",
            main_sku="MAIN-1",
            sub_sku="SUB-1",
            snapshot={"central_fields": {"包装后体积": 0.005}},
        )
        db.add(opportunity)
        db.flush()
        claims = [
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name=name,
                claim_result="claim",
                claim_daily_sales=daily_sales,
                source_column="platform",
            )
            for name, daily_sales in (("Sales A", 2), ("Sales B", 2.01))
        ]
        db.add_all(claims)
        db.flush()

        first = services.create_stocking_draft_for_claim(db, claims[0].id, "Manager A")
        second = services.create_stocking_draft_for_claim(db, claims[1].id, "Manager A")
        repeated = services.create_stocking_draft_for_claim(db, claims[0].id, "Manager A")
        db.commit()

        assert repeated.id == first.id
        assert first.id != second.id
        assert [first.claim_record_id, second.claim_record_id] == [claims[0].id, claims[1].id]
        assert [first.quantity, second.quantity] == [60, 61]
        assert first.application_date == datetime.now(services.EXCEL_TIMEZONE).date()
        assert first.unit_volume is None
        assert first.unit_volume_source is None
        assert first.volume is None
        assert db.query(models.StockingRequest).count() == 2


def test_review_approval_creates_one_draft_for_each_claim() -> None:
    with SessionLocal() as db:
        opportunity = models.NewProductOpportunity(
            source_type="selection2_caigen_claim_feedback",
            source_file="selection2.xlsx",
            source_sheet="period-2",
            source_row=2,
            current_status="claim_submitted",
            country="TH",
            main_sku="MAIN-2",
            sub_sku="SUB-2",
        )
        db.add(opportunity)
        db.flush()
        claims = [
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name=name,
                claim_result="claim",
                claim_daily_sales=daily_sales,
                source_column="platform",
            )
            for name, daily_sales in (("Sales A", 1), ("Sales B", 1.5))
        ]
        db.add_all(claims)
        db.flush()

        services.submit_review(
            db,
            schemas.ReviewCreate(
                opportunity_id=opportunity.id,
                reviewer_name="Manager A",
                review_status="approved",
            ),
        )
        db.commit()

        requests = db.query(models.StockingRequest).order_by(models.StockingRequest.quantity).all()
        assert {request.claim_record_id for request in requests} == {claim.id for claim in claims}
        assert [request.quantity for request in requests] == [30, 45]
        assert {claim.downstream_status for claim in claims} == {workflow_status.CLAIM_WAITING_STOCKING_REQUEST}
        assert services.list_available_stocking_items(db) == []


def test_stocking_request_post_requires_claim_record_id() -> None:
    response = client.post(
        "/stocking/requests",
        json={"opportunity_id": "opportunity-1", "daily_sales": 1},
    )

    assert response.status_code == 422


def test_stocking_request_post_reuses_claim_draft_and_rejects_mismatched_opportunity() -> None:
    with SessionLocal() as db:
        opportunities = [
            models.NewProductOpportunity(
                source_type="manual",
                source_row=index,
                main_sku=f"MAIN-{index}",
                sub_sku=f"SUB-{index}",
            )
            for index in (1, 2)
        ]
        db.add_all(opportunities)
        db.flush()
        claim = models.SalesClaimForecast(
            opportunity_id=opportunities[0].id,
            salesperson_name="Sales A",
            claim_result="claim",
            claim_daily_sales=2,
        )
        db.add(claim)
        db.flush()
        existing = services.create_stocking_draft_for_claim(db, claim.id)
        db.commit()
        ids = (opportunities[0].id, opportunities[1].id, claim.id, existing.id)

    mismatch = client.post(
        "/stocking/requests",
        json={"opportunity_id": ids[1], "claim_record_id": ids[2], "daily_sales": 99},
    )
    valid = client.post(
        "/stocking/requests",
        json={"opportunity_id": ids[0], "claim_record_id": ids[2], "daily_sales": 99},
    )

    assert mismatch.status_code == 400
    assert valid.status_code == 200
    assert valid.json()["id"] == ids[3]
    with SessionLocal() as db:
        assert db.query(models.StockingRequest).count() == 1


def test_sales_self_selection_creates_each_child_atomically_and_applies_decisions() -> None:
    token = login_operator("Operator A")
    response = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": " MAIN-SELF ",
            "main_sku_name": "Self selected",
            "country": " PH ",
            "children": [
                {"sub_sku": "SUB-STOCK", "inventory_available": False, "needs_stocking": True},
                {"sub_sku": "SUB-LIST", "inventory_available": True, "needs_stocking": False},
                {"sub_sku": "SUB-PAUSE", "inventory_available": False, "needs_stocking": False},
            ],
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        opportunities = db.query(models.NewProductOpportunity).order_by(models.NewProductOpportunity.source_row).all()
        snapshots = db.query(models.SourceRecordSnapshot).all()
        claims = db.query(models.SalesClaimForecast).order_by(models.SalesClaimForecast.created_at).all()
        requests = db.query(models.StockingRequest).all()
        claim_statuses = {
            db.get(models.NewProductOpportunity, claim.opportunity_id).sub_sku: claim.downstream_status
            for claim in claims
        }
    assert len(opportunities) == len(snapshots) == len(claims) == 3
    assert {item.batch for item in opportunities} == {f"\u9500\u552e\u81ea\u9009{datetime.now(services.EXCEL_TIMEZONE):%Y%m%d}"}
    assert {item.main_sku for item in opportunities} == {"MAIN-SELF"}
    assert {item.country for item in opportunities} == {"PH"}
    assert {item.salesperson_name for item in claims} == {"Operator A"}
    assert {item.claim_result for item in claims} == {"claim"}
    assert {item.source_column for item in claims} == {"platform"}
    assert claim_statuses == {
        "SUB-STOCK": "waiting_stocking_request",
        "SUB-LIST": "waiting_listing",
        "SUB-PAUSE": "stocking_paused",
    }
    assert [item.claim_record_id for item in requests] == [
        next(item.id for item in claims if item.downstream_status == "waiting_stocking_request")
    ]

    token_b = login_operator("Operator B")
    same_sku_other_operator = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "main_sku": "MAIN-SELF",
            "country": "PH",
            "children": [
                {"sub_sku": "SUB-STOCK", "inventory_available": True, "needs_stocking": False},
            ],
        },
    )
    assert same_sku_other_operator.status_code == 200

    duplicate = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": "MAIN-DUPLICATE",
            "country": "PH",
            "children": [
                {"sub_sku": "DUP", "inventory_available": False, "needs_stocking": True},
                {"sub_sku": " DUP ", "inventory_available": True, "needs_stocking": False},
            ],
        },
    )
    assert duplicate.status_code in {400, 409, 422}
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).filter_by(main_sku="MAIN-DUPLICATE").count() == 0


def test_sales_self_rejects_conflicting_inventory_and_stocking_decision() -> None:
    token = login_operator("Operator A")
    invalid_create = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": "MAIN-CONFLICT",
            "country": "PH",
            "children": [
                {"sub_sku": "SUB-CONFLICT", "inventory_available": True, "needs_stocking": True},
            ],
        },
    )

    assert invalid_create.status_code == 422
    with SessionLocal() as db:
        assert db.query(models.NewProductOpportunity).filter_by(main_sku="MAIN-CONFLICT").count() == 0

    paused = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": "MAIN-PAUSED",
            "country": "PH",
            "children": [
                {"sub_sku": "SUB-PAUSED", "inventory_available": False, "needs_stocking": False},
            ],
        },
    )
    claim_id = paused.json()[0]["claim_record_id"]
    invalid_update = client.post(
        f"/stocking/decisions/{claim_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"inventory_available": True, "needs_stocking": True},
    )

    assert invalid_update.status_code == 422
    with SessionLocal() as db:
        claim = db.get(models.SalesClaimForecast, claim_id)
        assert claim.inventory_available is False
        assert claim.needs_stocking is False
        assert claim.downstream_status == "stocking_paused"

def test_operator_stocking_response_includes_country_for_branch_without_request() -> None:
    token = login_operator("Operator A")
    created = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": "MAIN-NO-REQUEST",
            "country": "PH",
            "children": [
                {"sub_sku": "SUB-LIST", "inventory_available": True, "needs_stocking": False},
            ],
        },
    )

    response = client.get(
        "/stocking/my-requests",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert created.status_code == 200
    assert response.status_code == 200
    assert response.json() == [
        {
            **response.json()[0],
            "sub_sku": "SUB-LIST",
            "country": "PH",
            "request_id": None,
        }
    ]


def test_operator_can_save_incomplete_draft_submit_complete_values_and_edit_until_exported() -> None:
    token = login_operator("Operator A")
    request_id = create_self_stocking_request(token)

    incomplete = client.put(
        f"/stocking/requests/{request_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"warehouse": ""},
    )
    invalid_submit = client.post(
        f"/stocking/requests/{request_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    complete = client.put(
        f"/stocking/requests/{request_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "application_date": "2026-07-21",
            "request_type": "initial",
            "cost_price": 12.5,
            "unit_volume": 0.002,
            "daily_sales": 2.01,
            "country": " PH ",
            "warehouse": "",
        },
    )
    submitted = client.post(
        f"/stocking/requests/{request_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )
    denied_withdrawal = client.post(
        f"/stocking/decisions/{submitted.json()['claim_record_id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"inventory_available": False, "needs_stocking": False},
    )
    edited = client.put(
        f"/stocking/requests/{request_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"daily_sales": 3},
    )
    denied_after_edit = client.post(
        f"/stocking/decisions/{submitted.json()['claim_record_id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"inventory_available": False, "needs_stocking": False},
    )

    assert incomplete.status_code == 200
    assert invalid_submit.status_code == 400
    assert complete.status_code == 200
    assert submitted.status_code == 200
    assert submitted.json()["quantity"] == 61
    assert submitted.json()["amount"] == 762.5
    assert submitted.json()["volume"] == 0.122
    assert submitted.json()["warehouse"] is None
    assert denied_withdrawal.status_code == 409
    assert edited.status_code == 200
    assert edited.json()["status"] == "draft"
    assert denied_after_edit.status_code == 409
    with SessionLocal() as db:
        request = db.get(models.StockingRequest, request_id)
        claim = db.get(models.SalesClaimForecast, request.claim_record_id)
        claim_status = claim.downstream_status
        assert request.submitted_at is not None
        assert claim.needs_stocking is True
        request.status = "exported"
        audit_details = [item.detail for item in db.query(models.AuditLog).filter_by(action="stocking.request_updated")]
        db.commit()
    assert any(
        detail["after"].get("application_date") == "2026-07-21"
        and detail["after"].get("warehouse") is None
        for detail in audit_details
    )
    denied = client.put(
        f"/stocking/requests/{request_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"daily_sales": 4},
    )
    assert denied.status_code == 409
    assert claim_status == "waiting_stocking_request"


def test_replenishment_requires_reason_and_requests_are_owner_isolated() -> None:
    token_a = login_operator("Operator A")
    token_b = login_operator("Operator B")
    request_id = create_self_stocking_request(token_b)

    denied = client.put(
        f"/stocking/requests/{request_id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={"daily_sales": 2},
    )
    own_list = client.get("/stocking/my-requests", headers={"Authorization": f"Bearer {token_a}"})
    other_list = client.get("/stocking/my-requests", headers={"Authorization": f"Bearer {token_b}"})
    update = client.put(
        f"/stocking/requests/{request_id}",
        headers={"Authorization": f"Bearer {token_b}"},
        json={
            "application_date": "2026-07-21",
            "request_type": "replenishment",
            "cost_price": 1,
            "unit_volume": 0.001,
            "daily_sales": 1,
            "country": "PH",
        },
    )
    invalid = client.post(
        f"/stocking/requests/{request_id}/submit",
        headers={"Authorization": f"Bearer {token_b}"},
    )

    assert denied.status_code == 403
    assert own_list.status_code == 200 and own_list.json() == []
    assert other_list.status_code == 200 and len(other_list.json()) == 1
    assert update.status_code == 200
    assert invalid.status_code == 400
    assert "reason" in invalid.json()["detail"]

    null_type_id = create_self_stocking_request(token_a)
    null_type_update = client.put(
        f"/stocking/requests/{null_type_id}",
        headers={"Authorization": f"Bearer {token_a}"},
        json={
            "application_date": "2026-07-21",
            "request_type": None,
            "cost_price": 1,
            "unit_volume": 0.001,
            "daily_sales": 1,
            "country": "PH",
        },
    )
    assert null_type_update.status_code == 422
    assert "request_type" in null_type_update.text


def test_sales_self_preserved_draft_cannot_submit_after_no_stocking_decision() -> None:
    token = login_operator("Operator A")
    request_id = create_self_stocking_request(token)
    updated = client.put(
        f"/stocking/requests/{request_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "application_date": "2026-07-21",
            "request_type": "initial",
            "cost_price": 1,
            "unit_volume": 0.001,
            "daily_sales": 1,
            "country": "PH",
        },
    )
    claim_id = updated.json()["claim_record_id"]

    decision = client.post(
        f"/stocking/decisions/{claim_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"inventory_available": False, "needs_stocking": False},
    )
    submit = client.post(
        f"/stocking/requests/{request_id}/submit",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert decision.status_code == 200
    assert submit.status_code == 409
    with SessionLocal() as db:
        request = db.get(models.StockingRequest, request_id)
        claim = db.get(models.SalesClaimForecast, claim_id)
        assert request.status == "draft"
        assert request.submitted_at is None
        assert claim.needs_stocking is False
        assert claim.downstream_status == "stocking_paused"


def test_stocking_volume_source_tracks_erp_and_manual_updates() -> None:
    token = login_operator("Operator A")
    request_id = create_self_stocking_request(token)
    headers = {"Authorization": f"Bearer {token}"}

    erp = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"unit_volume": 0.002, "unit_volume_source": "erp"},
    )
    preserved = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"daily_sales": 2},
    )
    manual = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"unit_volume": 0.003},
    )
    cleared = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"unit_volume": None},
    )
    invalid = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"unit_volume": 0.004, "unit_volume_source": "guessed"},
    )

    assert erp.status_code == 200
    assert erp.json()["unit_volume_source"] == "erp"
    assert preserved.status_code == 200
    assert preserved.json()["unit_volume_source"] == "erp"
    assert manual.status_code == 200
    assert manual.json()["unit_volume_source"] == "manual"
    assert cleared.status_code == 200
    assert cleared.json()["unit_volume"] is None
    assert cleared.json()["unit_volume_source"] is None
    assert invalid.status_code == 422


def test_manual_dimensions_are_persisted_and_compute_unit_volume() -> None:
    token = login_operator("Operator A")
    request_id = create_self_stocking_request(token)
    headers = {"Authorization": f"Bearer {token}"}

    saved = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"length_cm": 20, "width_cm": 10, "height_cm": 5},
    )
    partial = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"length_cm": 25, "width_cm": None, "height_cm": 5},
    )
    invalid = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={"length_cm": -1},
    )

    assert saved.status_code == 200
    assert saved.json()["length_cm"] == 20
    assert saved.json()["width_cm"] == 10
    assert saved.json()["height_cm"] == 5
    assert saved.json()["unit_volume"] == 0.001
    assert saved.json()["unit_volume_source"] == "manual"
    assert partial.status_code == 200
    assert partial.json()["unit_volume"] is None
    assert invalid.status_code == 422


def test_operator_stocking_list_order_does_not_follow_updated_at() -> None:
    with SessionLocal() as db:
        opportunities = [
            models.NewProductOpportunity(
                source_type="sales_self_selection",
                source_file="平台销售自选",
                source_sheet="销售自选20260722",
                source_row=index,
                main_sku="MAIN-STABLE",
                sub_sku=sub_sku,
            )
            for index, sub_sku in enumerate(("SUB-B", "SUB-A"), start=2)
        ]
        db.add_all(opportunities)
        db.flush()
        db.add_all([
            models.SalesClaimForecast(
                opportunity_id=opportunity.id,
                salesperson_name="Operator A",
                source_column="platform",
                downstream_status="stocking_paused",
                inventory_available=False,
                needs_stocking=False,
                updated_at=datetime(2026, 7, 22, 12, 0, index),
            )
            for index, opportunity in enumerate(opportunities)
        ])
        db.commit()

        rows = services.list_operator_stocking_items(db, "Operator A")

    assert [row.sub_sku for row in rows] == ["SUB-A", "SUB-B"]


def test_stocking_update_rejects_non_finite_numbers_without_persisting() -> None:
    token = login_operator("Operator A")
    request_id = create_self_stocking_request(token)

    for value in (float("nan"), float("inf"), float("-inf")):
        try:
            schemas.StockingRequestUpdate(cost_price=value)
        except ValueError:
            pass
        else:
            raise AssertionError("non-finite stocking value was accepted")

    responses = [
        client.put(
            f"/stocking/requests/{request_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            content=f'{{"cost_price": {literal}}}',
        )
        for literal in ("NaN", "Infinity", "-Infinity")
    ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    with SessionLocal() as db:
        request = db.get(models.StockingRequest, request_id)
        assert request.cost_price is None
        assert request.amount is None


def test_stocking_decision_queries_request_before_claim_for_lock_order() -> None:
    token = login_operator("Operator A")
    request_id = create_self_stocking_request(token)
    with SessionLocal() as db:
        request = db.get(models.StockingRequest, request_id)
        claim_id = request.claim_record_id

    statements: list[str] = []

    def record_statement(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        statements.append(statement.lower())

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        with SessionLocal() as db:
            services.update_stocking_decision(
                db,
                claim_id,
                "Operator A",
                schemas.StockingDecisionUpdate(inventory_available=False, needs_stocking=True),
            )
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)

    request_query = next(index for index, statement in enumerate(statements) if "from stocking_request" in statement)
    claim_query = next(index for index, statement in enumerate(statements) if "from sales_claim_forecast" in statement)
    assert request_query < claim_query

def test_decision_can_resume_paused_claim_and_volume_preview_uses_erp_resolver(monkeypatch) -> None:
    token = login_operator("Operator A")
    response = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": "MAIN-DECISION",
            "country": "PH",
            "children": [{"sub_sku": "SUB-A", "inventory_available": False, "needs_stocking": False}],
        },
    )
    claim_id = response.json()[0]["claim_record_id"]

    resumed = client.post(
        f"/stocking/decisions/{claim_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"inventory_available": False, "needs_stocking": True},
    )
    monkeypatch.setattr(
        "app.routers.stocking.erp_product_list.fetch_product_volumes",
        lambda skus, settings: {skus[0]: 0.000132916, skus[1]: None},
    )
    preview = client.post(
        "/stocking/volume-preview",
        headers={"Authorization": f"Bearer {token}"},
        json={"skus": ["GSHWAC225ND", "MISSING"]},
    )

    assert resumed.status_code == 200
    assert resumed.json()["downstream_status"] == "waiting_stocking_request"
    assert [item["status"] for item in preview.json()] == ["resolved", "manual_required"]
    assert preview.json()[0]["unit_volume"] == 0.000132916


def test_unchanged_submitted_request_update_is_a_noop() -> None:
    token = login_operator("Operator A")
    request_id = create_self_stocking_request(token)
    headers = {"Authorization": f"Bearer {token}"}
    updated = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={
            "application_date": "2026-07-22",
            "request_type": "initial",
            "cost_price": 12.5,
            "length_cm": 20,
            "width_cm": 10,
            "height_cm": 5,
            "unit_volume": 0.001,
            "unit_volume_source": "manual",
            "daily_sales": 2,
            "country": "PH",
            "warehouse": None,
            "reason": None,
        },
    )
    submitted = client.post(
        f"/stocking/requests/{request_id}/submit",
        headers=headers,
    )
    with SessionLocal() as db:
        audit_count = db.query(models.AuditLog).filter_by(action="stocking.request_updated").count()

    unchanged = client.put(
        f"/stocking/requests/{request_id}",
        headers=headers,
        json={
            "application_date": "2026-07-22",
            "request_type": "initial",
            "cost_price": 12.5,
            "length_cm": 20,
            "width_cm": 10,
            "height_cm": 5,
            "unit_volume": 0.001,
            "unit_volume_source": "manual",
            "daily_sales": 2,
            "country": "PH",
            "warehouse": None,
            "reason": None,
        },
    )

    assert updated.status_code == submitted.status_code == unchanged.status_code == 200
    assert unchanged.json()["status"] == "submitted"
    with SessionLocal() as db:
        request = db.get(models.StockingRequest, request_id)
        claim = db.get(models.SalesClaimForecast, request.claim_record_id)
        assert claim.downstream_status == "waiting_export"
        assert db.query(models.AuditLog).filter_by(action="stocking.request_updated").count() == audit_count


def create_self_stocking_request(token: str) -> str:
    response = client.post(
        "/stocking/self-selections",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "main_sku": f"MAIN-{models.new_id()}",
            "country": "PH",
            "children": [{"sub_sku": f"SUB-{models.new_id()}", "inventory_available": False, "needs_stocking": True}],
        },
    )
    assert response.status_code == 200
    return response.json()[0]["request_id"]


def login_operator(name: str) -> str:
    with SessionLocal() as db:
        db.add(models.RoleMapping(name=name, role="operator", enabled=True))
        db.commit()
    response = client.post("/auth/login", json={"name": name, "password": default_password_for_name(name)})
    assert response.status_code == 200
    return response.json()["access_token"]
