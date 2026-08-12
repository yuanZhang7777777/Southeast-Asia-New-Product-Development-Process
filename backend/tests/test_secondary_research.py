import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_secondary_research.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.auth import AuthContext  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.secondary_research import secondary_research_owner, secondary_research_write_owner  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_secondary_research_read_scope_allows_managers_and_locks_operators() -> None:
    user = models.User(name="测试用户", enabled=True)
    manager = AuthContext(user=user, roles=[schemas.AuthRoleRead(role="manager", name="主管")])
    operator = AuthContext(user=user, roles=[schemas.AuthRoleRead(role="operator", name="运营甲")])

    assert secondary_research_owner(manager, None) is None
    assert secondary_research_owner(manager, "运营乙") == "运营乙"
    assert secondary_research_owner(operator, None) == "运营甲"
    assert secondary_research_owner(operator, "运营乙") == "运营甲"


def test_secondary_research_write_scope_uses_selected_owner_for_super_admin() -> None:
    user = models.User(name="刘学城", enabled=True)
    super_admin = AuthContext(user=user, roles=[schemas.AuthRoleRead(role="super_admin", name="刘学城")])
    operator = AuthContext(user=user, roles=[schemas.AuthRoleRead(role="operator", name="运营甲")])

    assert secondary_research_write_owner(super_admin, "江琴") == "江琴"
    assert secondary_research_write_owner(super_admin, None) == "刘学城"
    assert secondary_research_write_owner(operator, "江琴") == "运营甲"


def test_approved_review_marks_the_specific_claim_waiting_for_stocking_request() -> None:
    opportunity, claim = make_claim("SUB-A", "销售A")
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id
        opportunity_id = opportunity.id

    response = client.post(
        "/reviews",
        json={
            "opportunity_id": opportunity_id,
            "claim_record_id": claim_id,
            "reviewer_name": "练玉君",
            "review_status": "approved",
            "review_comment": "通过",
        },
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        saved_claim = db.get(models.SalesClaimForecast, claim_id)
        review = db.query(models.ReviewRecord).one()
    assert saved_claim.downstream_status == "waiting_stocking_request"
    assert review.claim_record_id == claim_id


def test_arrival_opens_secondary_research_for_the_matched_claim() -> None:
    opportunity, claim = make_claim("SUB-A", "销售A", downstream_status="waiting_arrival")
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id
        opportunity_id = opportunity.id

    arrived_at = "2026-07-12T08:32:00+08:00"
    response = client.post(
        "/arrival/records",
        json={
            "opportunity_id": opportunity_id,
            "claim_record_id": claim_id,
            "warehouse": "PH仓",
            "arrived_quantity": 120,
            "arrived_at": arrived_at,
        },
    )

    assert response.status_code == 200
    assert response.json()["claim_record_id"] == claim_id
    assert response.json()["salesperson_name"] == "销售A"
    with SessionLocal() as db:
        saved_claim = db.get(models.SalesClaimForecast, claim_id)
        saved_opportunity = db.get(models.NewProductOpportunity, opportunity_id)
    assert saved_claim.downstream_status == "waiting_secondary_research"
    assert saved_claim.arrival_detected_at is not None
    assert saved_opportunity.current_status == "waiting_secondary_research"


def test_read_only_historical_selection2_claim_cannot_open_arrival_or_secondary_research() -> None:
    source_type = "history_selection2"
    opportunity = models.NewProductOpportunity(
        id=models.new_id(),
        source_type=source_type,
        source_file="history.xlsx",
        source_sheet="历史期",
        source_row=2,
        batch="历史期",
        country="PH",
        site="PH",
        main_sku="MAIN-HISTORY",
        sub_sku=f"SUB-{source_type}",
        current_status="historical_archive",
        claim_pool_open=False,
        snapshot={},
    )
    claim = models.SalesClaimForecast(
        opportunity_id=opportunity.id,
        salesperson_name="历史运营",
        claim_result="claim",
        claim_daily_sales=1,
        source_column=f"{source_type}:history",
        claim_source=source_type,
    )
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        opportunity_id = opportunity.id
        claim_id = claim.id
        with pytest.raises(PermissionError, match="cannot enter secondary research"):
            services.open_secondary_research(db, claim_id)
        db.rollback()

    response = client.post(
        "/arrival/records",
        json={
            "opportunity_id": opportunity_id,
            "claim_record_id": claim_id,
            "warehouse": "PH仓",
            "arrived_quantity": 1,
            "arrived_at": "2026-07-30T08:00:00+08:00",
        },
    )

    assert response.status_code == 403
    with SessionLocal() as db:
        saved_claim = db.get(models.SalesClaimForecast, claim_id)
        assert saved_claim.downstream_status is None
        assert saved_claim.arrival_detected_at is None
        assert db.query(models.ArrivalRecord).count() == 0


def test_historical_claim_already_waiting_secondary_research_can_be_filled() -> None:
    opportunity = models.NewProductOpportunity(
        id=models.new_id(),
        source_type="history_selection34",
        source_file="history.xlsx",
        source_sheet="销售自选0608期",
        source_row=60,
        batch="销售自选0608期",
        country="VN",
        site="VN",
        main_sku="HYWAC834",
        sub_sku="HYWAC834-A3",
        current_status="historical_archive",
        claim_pool_open=False,
        snapshot={},
    )
    claim = models.SalesClaimForecast(
        opportunity_id=opportunity.id,
        salesperson_name="赵钰婷",
        claim_result="claim",
        claim_daily_sales=1,
        source_column="history_selection34:plm_arrival",
        claim_source="history_selection34",
        downstream_status="waiting_secondary_research",
    )
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id

    draft = client.patch(
        f"/secondary-research/{claim_id}",
        params={"salesperson_name": "赵钰婷"},
        json={
            "secondary_competitor_url": "https://shopee.vn/item/1",
            "secondary_conclusion": "可继续",
            "product_positioning": "利润款",
            "secondary_target_daily_sales": 3,
            "secondary_selling_points": "太阳镜款式明确",
        },
    )
    assert draft.status_code == 200

    submitted = client.post(
        "/secondary-research/submit-group",
        params={"salesperson_name": "赵钰婷"},
        json={"claim_record_ids": [claim_id]},
    )
    assert submitted.status_code == 200
    with SessionLocal() as db:
        saved = db.get(models.SalesClaimForecast, claim_id)
    assert saved.secondary_research_submitted_at is not None
    assert saved.downstream_status == "waiting_listing"


def test_secondary_research_list_groups_my_children_and_shows_peer_records() -> None:
    opportunity_a, claim_a = make_claim("SUB-A", "销售A", downstream_status="waiting_secondary_research")
    opportunity_b, claim_b = make_claim("SUB-B", "销售A", downstream_status="waiting_secondary_research")
    peer = models.SalesClaimForecast(
        opportunity_id=opportunity_a.id,
        salesperson_name="销售B",
        claim_result="claim",
        source_column="platform",
        downstream_status="waiting_listing",
        secondary_research_at=datetime(2026, 7, 12, 9, tzinfo=timezone.utc),
        secondary_conclusion="其他运营结论",
        product_positioning="利润款",
        secondary_research_submitted_at=datetime(2026, 7, 12, 10, tzinfo=timezone.utc),
    )
    with SessionLocal() as db:
        db.add_all([opportunity_a, opportunity_b, claim_a, claim_b, peer])
        db.commit()

    response = client.get("/secondary-research", params={"salesperson_name": "销售A"})

    assert response.status_code == 200
    groups = response.json()
    assert len(groups) == 1
    assert groups[0]["business_period"] == "开发0710期"
    assert groups[0]["main_sku"] == "MAIN-1"
    assert [item["sub_sku"] for item in groups[0]["items"]] == ["SUB-A", "SUB-B"]
    assert groups[0]["items"][0]["peer_records"][0]["salesperson_name"] == "销售B"
    assert groups[0]["items"][0]["peer_records"][0]["secondary_conclusion"] == "其他运营结论"


def test_secondary_research_defaults_all_periods_and_supports_period_filter() -> None:
    old_opportunity, old_claim = make_claim(
        "SUB-OLD",
        "销售A",
        downstream_status="waiting_secondary_research",
        business_period="开发0703期",
    )
    new_opportunity, new_claim = make_claim(
        "SUB-NEW",
        "销售A",
        downstream_status="waiting_secondary_research",
        business_period="开发0710期",
    )
    with SessionLocal() as db:
        db.add_all([old_opportunity, old_claim, new_opportunity, new_claim])
        db.commit()

    default = client.get("/secondary-research", params={"salesperson_name": "销售A"}).json()
    history = client.get(
        "/secondary-research",
        params={"salesperson_name": "销售A", "business_period": "开发0703期"},
    ).json()
    all_periods = client.get(
        "/secondary-research",
        params={"salesperson_name": "销售A", "business_period": "__all__"},
    ).json()

    assert sorted(group["business_period"] for group in default) == ["开发0703期", "开发0710期"]
    assert [group["business_period"] for group in history] == ["开发0703期"]
    assert sorted(group["business_period"] for group in all_periods) == ["开发0703期", "开发0710期"]


def test_secondary_research_lists_visible_selection1_tasks_and_hides_discarded_periods() -> None:
    hcd_opportunity, hcd_claim = make_claim(
        "HCD022PK",
        "陈丽妹",
        downstream_status="waiting_secondary_research",
        business_period="开发0714期",
    )
    hcd_opportunity.main_sku = "HCD022"
    hcd_opportunity.main_sku_name = "广角睫毛夹烫睫毛器"
    hidden_opportunity, hidden_claim = make_claim(
        "HIST-OLD",
        "陈丽妹",
        downstream_status="waiting_secondary_research",
        business_period="历史归档",
    )
    hidden_opportunity.main_sku = "HISTOLD"
    with SessionLocal() as db:
        db.add_all([hcd_opportunity, hcd_claim, hidden_opportunity, hidden_claim])
        db.commit()

    groups = client.get("/secondary-research", params={"salesperson_name": "陈丽妹"}).json()

    assert [(group["business_period"], group["main_sku"]) for group in groups] == [("开发0714期", "HCD022")]


def test_secondary_research_history_can_include_submitted_records_after_workflow_moves_on() -> None:
    pending_opportunity, pending_claim = make_claim(
        "SUB-PENDING",
        "销售A",
        downstream_status="waiting_secondary_research",
    )
    submitted_opportunity, submitted_claim = make_claim(
        "SUB-SUBMITTED",
        "销售A",
        downstream_status="waiting_listing",
    )
    submitted_claim.secondary_research_submitted_at = datetime(2026, 7, 12, 10, tzinfo=timezone.utc)
    submitted_claim.secondary_conclusion = "已提交结论"
    submitted_claim.product_positioning = "利润款"
    with SessionLocal() as db:
        db.add_all([pending_opportunity, pending_claim, submitted_opportunity, submitted_claim])
        db.commit()

    response = client.get(
        "/secondary-research",
        params={
            "salesperson_name": "销售A",
            "business_period": "__all__",
            "downstream_status": "",
        },
    )

    assert response.status_code == 200
    items = [item for group in response.json() for item in group["items"]]
    assert {item["sub_sku"] for item in items} == {"SUB-PENDING", "SUB-SUBMITTED"}
    assert next(item for item in items if item["sub_sku"] == "SUB-SUBMITTED")["secondary_conclusion"] == "已提交结论"


def test_manual_secondary_research_creates_missing_sku_without_tasks_or_notifications() -> None:
    response = client.post(
        "/secondary-research/manual",
        json={
            "country": "菲律宾",
            "main_sku": "MANUAL-MAIN",
            "sub_sku": "MANUAL-SUB",
            "salesperson_name": "销售A",
            "business_period": "手工二调0803期",
            "main_sku_name": "手工新增商品",
            "sub_sku_name": "黑色",
            "secondary_competitor_url": "https://shopee.ph/item/manual",
        },
    )

    assert response.status_code == 200
    item = response.json()
    assert item["salesperson_name"] == "销售A"
    assert item["sub_sku"] == "MANUAL-SUB"
    assert item["downstream_status"] == "waiting_secondary_research"
    assert item["secondary_competitor_url"] == "https://shopee.ph/item/manual"

    listed = client.get(
        "/secondary-research",
        params={"salesperson_name": "销售A", "business_period": "手工二调0803期"},
    )
    assert listed.status_code == 200
    group = listed.json()[0]
    assert group["source_type"] == "manual_secondary"
    assert group["country"] == "菲律宾"
    assert group["main_sku"] == "MANUAL-MAIN"
    assert [row["sub_sku"] for row in group["items"]] == ["MANUAL-SUB"]

    with SessionLocal() as db:
        opportunity = db.get(models.NewProductOpportunity, item["opportunity_id"])
        claim = db.get(models.SalesClaimForecast, item["claim_record_id"])
        snapshot = db.query(models.SourceRecordSnapshot).one()
        assert opportunity.source_type == "manual_secondary"
        assert opportunity.current_status == "waiting_secondary_research"
        assert claim.claim_source == "manual_secondary"
        assert db.query(models.FlowTask).count() == 0
        assert db.query(models.NotificationLog).count() == 0
        assert snapshot.payload["manual_secondary"]["main_sku"] == "MANUAL-MAIN"


def test_manual_secondary_research_reuses_pending_exact_match_and_rejects_later_stage() -> None:
    first = client.post(
        "/secondary-research/manual",
        json={
            "country": "PH",
            "main_sku": "MANUAL-MAIN",
            "sub_sku": "MANUAL-SUB",
            "salesperson_name": "销售A",
        },
    )
    assert first.status_code == 200
    claim_id = first.json()["claim_record_id"]

    repeated = client.post(
        "/secondary-research/manual",
        json={
            "country": "菲律宾",
            "main_sku": "MANUAL-MAIN",
            "sub_sku": "MANUAL-SUB",
            "salesperson_name": "销售A",
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["claim_record_id"] == claim_id

    with SessionLocal() as db:
        claim = db.get(models.SalesClaimForecast, claim_id)
        fill_research(claim, "利润款", "可以刊登")
        db.commit()
    submitted = client.post(
        "/secondary-research/submit-group",
        params={"salesperson_name": "销售A"},
        json={"claim_record_ids": [claim_id]},
    )
    assert submitted.status_code == 200

    blocked = client.post(
        "/secondary-research/manual",
        json={
            "country": "PH",
            "main_sku": "MANUAL-MAIN",
            "sub_sku": "MANUAL-SUB",
            "salesperson_name": "销售A",
        },
    )
    assert blocked.status_code == 409
    assert "已存在于后续阶段" in blocked.json()["detail"]


def test_manager_assigns_plm_arrival_to_selected_operator_before_secondary_research() -> None:
    with SessionLocal() as db:
        add_operator(db, "销售B")
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-07",
            source_file="plm-2026-08-07.xlsx",
            source_hash="hash-plm-assign",
            bloc_name="集团八部",
            row_count=1,
        )
        db.add(batch)
        db.flush()
        item = models.PlmArrivalItem(
            batch_id=batch.id,
            source_sheet="汇总表格",
            source_row=15,
            arrival_type="new_arrival",
            product_name="PLM待分配商品",
            salesperson_name="PLM原销售",
            country="菲律宾",
            warehouse="菲律宾海外仓",
            main_sku="PLM-MAIN",
            sub_sku="PLM-SUB",
            latest_storage_time=datetime(2026, 8, 7, 9, 30, tzinfo=timezone.utc),
            first_listing_time=datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc),
            match_status="pending_assignment",
            raw_payload={"main_sku": "PLM-MAIN"},
        )
        db.add(item)
        db.commit()
        item_id = item.id

    pending = client.get("/secondary-research/plm-arrival-assignments")
    assert pending.status_code == 200
    assert pending.json()[0]["plm_salesperson_name"] == "PLM原销售"
    assert pending.json()[0]["main_sku"] == "PLM-MAIN"

    assigned = client.post(
        f"/secondary-research/plm-arrival-assignments/{item_id}/assign",
        json={"salesperson_name": "销售B"},
    )

    assert assigned.status_code == 200
    assert assigned.json()["assigned_salesperson_name"] == "销售B"
    with SessionLocal() as db:
        saved_item = db.get(models.PlmArrivalItem, item_id)
        opportunity = db.query(models.NewProductOpportunity).filter_by(source_type="plm_arrival_discovery").one()
        claim = db.query(models.SalesClaimForecast).one()
        arrival = db.query(models.ArrivalRecord).one()
        plm_original_owner_count = db.query(models.SalesClaimForecast).filter_by(salesperson_name="PLM原销售").count()
    assert saved_item.match_status == "assigned"
    assert saved_item.matched_claim_record_id == claim.id
    assert opportunity.batch == "PLM新增到货"
    assert opportunity.main_sku == "PLM-MAIN"
    assert claim.salesperson_name == "销售B"
    assert claim.downstream_status == "waiting_secondary_research"
    assert arrival.salesperson_name == "销售B"
    assert plm_original_owner_count == 0


def test_manager_assigns_plm_arrival_main_sku_group_to_selected_operator() -> None:
    with SessionLocal() as db:
        add_operator(db, "销售B")
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-07",
            source_file="plm-2026-08-07.xlsx",
            source_hash="hash-plm-assign-main-group",
            bloc_name="集团八部",
            row_count=2,
        )
        db.add(batch)
        db.flush()
        items = [
            models.PlmArrivalItem(
                batch_id=batch.id,
                source_sheet="汇总表格",
                source_row=20 + index,
                arrival_type="new_arrival",
                product_name=f"主SKU组商品{index}",
                salesperson_name="PLM原销售",
                country="菲律宾",
                warehouse="菲律宾海外仓",
                main_sku="PLM-GROUP",
                sub_sku=f"PLM-GROUP-A{index}",
                latest_storage_time=datetime(2026, 8, 7, 9, 30, tzinfo=timezone.utc),
                first_listing_time=datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc),
                match_status="pending_assignment",
                raw_payload={},
            )
            for index in (1, 2)
        ]
        db.add_all(items)
        db.commit()
        item_ids = [item.id for item in items]

    assigned = client.post(
        "/secondary-research/plm-arrival-assignments/assign-group",
        json={"plm_arrival_item_ids": item_ids, "salesperson_name": "销售B"},
    )

    assert assigned.status_code == 200
    body = assigned.json()
    assert [row["sub_sku"] for row in body] == ["PLM-GROUP-A1", "PLM-GROUP-A2"]
    assert {row["assigned_salesperson_name"] for row in body} == {"销售B"}
    with SessionLocal() as db:
        saved_items = db.query(models.PlmArrivalItem).order_by(models.PlmArrivalItem.source_row).all()
        claims = db.query(models.SalesClaimForecast).order_by(models.SalesClaimForecast.id).all()
        arrivals = db.query(models.ArrivalRecord).order_by(models.ArrivalRecord.id).all()
        opportunities = db.query(models.NewProductOpportunity).order_by(models.NewProductOpportunity.sub_sku).all()
    assert [item.match_status for item in saved_items] == ["assigned", "assigned"]
    assert [opportunity.sub_sku for opportunity in opportunities] == ["PLM-GROUP-A1", "PLM-GROUP-A2"]
    assert {claim.salesperson_name for claim in claims} == {"销售B"}
    assert {claim.downstream_status for claim in claims} == {"waiting_secondary_research"}
    assert len(arrivals) == 2


def test_manager_can_assign_plm_arrival_main_sku_group_to_operator_from_any_site() -> None:
    with SessionLocal() as db:
        add_operator(db, "泰国承接运营", key_site="TH")
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-07",
            source_file="plm-2026-08-07.xlsx",
            source_hash="hash-plm-assign-main-group-cross-site",
            bloc_name="集团八部",
            row_count=2,
        )
        db.add(batch)
        db.flush()
        items = [
            models.PlmArrivalItem(
                batch_id=batch.id,
                source_sheet="汇总表格",
                source_row=30 + index,
                arrival_type="new_arrival",
                product_name=f"菲律宾PLM待分配{index}",
                salesperson_name="PLM原销售",
                country="菲律宾",
                warehouse="菲律宾海外仓",
                main_sku="PLM-CROSS-SITE",
                sub_sku=f"PLM-CROSS-SITE-A{index}",
                latest_storage_time=datetime(2026, 8, 7, 9, 30, tzinfo=timezone.utc),
                first_listing_time=datetime(2026, 8, 7, 2, 0, tzinfo=timezone.utc),
                match_status="pending_assignment",
                raw_payload={},
            )
            for index in (1, 2)
        ]
        db.add_all(items)
        db.commit()
        item_ids = [item.id for item in items]

    assigned = client.post(
        "/secondary-research/plm-arrival-assignments/assign-group",
        json={"plm_arrival_item_ids": item_ids, "salesperson_name": "泰国承接运营"},
    )

    assert assigned.status_code == 200
    assert {row["assigned_salesperson_name"] for row in assigned.json()} == {"泰国承接运营"}
    with SessionLocal() as db:
        claims = db.query(models.SalesClaimForecast).order_by(models.SalesClaimForecast.id).all()
        arrivals = db.query(models.ArrivalRecord).order_by(models.ArrivalRecord.id).all()
    assert {claim.salesperson_name for claim in claims} == {"泰国承接运营"}
    assert {claim.downstream_status for claim in claims} == {"waiting_secondary_research"}
    assert len(arrivals) == 2


def test_plm_arrival_assignment_operator_candidates_exclude_admins_and_disabled_profiles() -> None:
    with SessionLocal() as db:
        add_operator(db, "可承接运营", key_site="PH")
        disabled_profile_operator = models.User(name="停用配置运营", enabled=True)
        disabled_notification_operator = add_operator(db, "不通知运营", key_site="VN")
        db.flush()
        mapping = db.query(models.RoleMapping).filter_by(user_id=disabled_notification_operator.id, role="operator").one()
        mapping.notification_enabled = False

        db.add(disabled_profile_operator)
        db.flush()
        db.add_all(
            [
                models.RoleMapping(
                    user_id=disabled_profile_operator.id,
                    name="停用配置运营",
                    role="operator",
                    enabled=True,
                    notification_enabled=True,
                ),
                models.OperatorAssignmentProfile(operator_name="停用配置运营", key_site="TH", enabled=False),
            ]
        )

        manager = models.User(name="主管人员", enabled=True)
        db.add(manager)
        db.flush()
        db.add_all(
            [
                models.RoleMapping(user_id=manager.id, name="主管人员", role="manager", enabled=True),
                models.RoleMapping(user_id=manager.id, name="主管人员", role="operator", enabled=True, notification_enabled=True),
                models.OperatorAssignmentProfile(operator_name="主管人员", key_site="PH", enabled=True),
            ]
        )
        db.commit()

    response = client.get("/secondary-research/plm-arrival-assignments/operators")

    assert response.status_code == 200
    assert [row["operator_name"] for row in response.json()] == ["可承接运营"]


def test_manager_closes_plm_arrival_assignment_without_creating_secondary_task() -> None:
    with SessionLocal() as db:
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-07",
            source_file="plm-2026-08-07.xlsx",
            source_hash="hash-plm-close",
            bloc_name="集团八部",
            row_count=1,
        )
        db.add(batch)
        db.flush()
        item = models.PlmArrivalItem(
            batch_id=batch.id,
            source_sheet="汇总表格",
            source_row=16,
            arrival_type="new_arrival",
            product_name="不推进商品",
            salesperson_name="PLM原销售",
            country="菲律宾",
            main_sku="PLM-CLOSE",
            sub_sku="PLM-CLOSE-A1",
            match_status="pending_assignment",
            raw_payload={},
        )
        db.add(item)
        db.commit()
        item_id = item.id

    response = client.post(
        f"/secondary-research/plm-arrival-assignments/{item_id}/close",
        json={"reason": "站点负责人已变更，本次暂不推进"},
    )

    assert response.status_code == 200
    with SessionLocal() as db:
        saved_item = db.get(models.PlmArrivalItem, item_id)
        assert saved_item.match_status == "assignment_closed"
        assert saved_item.raw_payload["_plm_assignment"]["close_reason"] == "站点负责人已变更，本次暂不推进"
        assert db.query(models.SalesClaimForecast).count() == 0
        assert db.query(models.ArrivalRecord).count() == 0


def test_plm_arrival_assignment_lists_multi_product_block_reason() -> None:
    with SessionLocal() as db:
        add_operator(db, "销售B")
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-07",
            source_file="plm-2026-08-07.xlsx",
            source_hash="hash-plm-multi-product",
            bloc_name="集团八部",
            row_count=1,
        )
        db.add(batch)
        db.flush()
        item = models.PlmArrivalItem(
            batch_id=batch.id,
            source_sheet="汇总表格",
            source_row=17,
            arrival_type="new_arrival",
            product_name="多当前商品",
            salesperson_name="PLM原销售",
            country="菲律宾",
            main_sku="PLM-DUP",
            sub_sku="PLM-DUP-A1",
            match_status="pending_assignment",
            raw_payload={},
        )
        db.add(item)
        db.add_all(
            [
                models.NewProductOpportunity(
                    id="op-plm-dup-1",
                    source_type="selection1_developer_claim_feedback",
                    batch="开发0804期",
                    country="菲律宾",
                    site="PH",
                    main_sku="PLM-DUP",
                    sub_sku="PLM-DUP-A1",
                    current_status="waiting_secondary_research",
                ),
                models.NewProductOpportunity(
                    id="op-plm-dup-2",
                    source_type="selection1_developer_claim_feedback",
                    batch="开发0804期",
                    country="菲律宾",
                    site="PH",
                    main_sku="PLM-DUP",
                    sub_sku="PLM-DUP-A1",
                    current_status="claim_submitted",
                ),
            ]
        )
        db.commit()
        item_id = item.id

    pending = client.get("/secondary-research/plm-arrival-assignments")

    assert pending.status_code == 200
    row = pending.json()[0]
    assert row["existing_opportunity_count"] == 2
    assert row["assignment_block_reason"] == "当前系统存在多个同国家+主SKU+子SKU商品，需先处理商品归属"

    assigned = client.post(
        f"/secondary-research/plm-arrival-assignments/{item_id}/assign",
        json={"salesperson_name": "销售B"},
    )

    assert assigned.status_code == 400
    assert "multiple current products" in assigned.json()["detail"]


def test_plm_arrival_assignment_list_batches_current_product_lookup() -> None:
    with SessionLocal() as db:
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-07",
            source_file="plm-2026-08-07.xlsx",
            source_hash="hash-plm-list-batch",
            bloc_name="集团八部",
            row_count=30,
        )
        db.add(batch)
        db.flush()
        db.add_all(
            [
                models.PlmArrivalItem(
                    batch_id=batch.id,
                    source_sheet="汇总表格",
                    source_row=row,
                    arrival_type="new_arrival",
                    product_name=f"待分配商品{row}",
                    salesperson_name="PLM原销售",
                    country="菲律宾",
                    main_sku=f"PLM-BATCH-{row}",
                    sub_sku=f"PLM-BATCH-{row}-A1",
                    match_status="pending_assignment",
                    raw_payload={},
                )
                for row in range(1, 31)
            ]
        )
        db.add(
            models.NewProductOpportunity(
                id="op-plm-batch-1",
                source_type="selection1_developer_claim_feedback",
                batch="开发0804期",
                country="菲律宾",
                site="PH",
                main_sku="PLM-BATCH-1",
                sub_sku="PLM-BATCH-1-A1",
                current_status="waiting_secondary_research",
            )
        )
        db.commit()

        opportunity_selects = 0

        def count_opportunity_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal opportunity_selects
            if statement.lstrip().upper().startswith("SELECT") and "new_product_opportunity" in statement:
                opportunity_selects += 1

        event.listen(engine, "before_cursor_execute", count_opportunity_selects)
        try:
            rows = services.list_plm_arrival_assignments(db)
        finally:
            event.remove(engine, "before_cursor_execute", count_opportunity_selects)

    assert len(rows) == 30
    assert rows[0]["existing_opportunity_count"] == 1
    assert opportunity_selects <= 1


def test_plm_arrival_assignment_lists_matching_system_periods() -> None:
    with SessionLocal() as db:
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-11",
            source_file="plm-2026-08-11.xlsx",
            source_hash="hash-plm-system-period",
            bloc_name="集团八部",
            row_count=1,
        )
        db.add(batch)
        db.flush()
        db.add(
            models.PlmArrivalItem(
                batch_id=batch.id,
                source_sheet="汇总表格",
                source_row=33417,
                arrival_type="new_arrival",
                product_name="系统里已有的到货新品",
                salesperson_name="PLM原销售",
                country="泰国",
                main_sku="ZRTOY2962",
                sub_sku="ZRTOY2962-A5",
                match_status="pending_assignment",
                raw_payload={},
            )
        )
        db.add(
            models.NewProductOpportunity(
                source_type="history_selection34",
                source_file="history-selection34.xlsx",
                source_sheet="直发热销转0630期",
                source_row=113,
                batch="直发热销转0630期",
                country="泰国",
                site="TH",
                main_sku="ZRTOY2962",
                sub_sku="ZRTOY2962-A5",
                current_status="historical_archive",
            )
        )
        db.commit()

        rows = services.list_plm_arrival_assignments(db)

    assert len(rows) == 1
    assert rows[0]["existing_opportunity_count"] == 1
    assert rows[0]["system_business_periods"] == ["直发热销转0630期"]
    assert rows[0]["system_matches"][0]["business_period"] == "直发热销转0630期"
    assert rows[0]["system_matches"][0]["source_row"] == 113


def test_plm_arrival_assignment_rejects_manager_even_if_operator_role_exists() -> None:
    with SessionLocal() as db:
        user = models.User(name="管理员兼运营", enabled=True)
        db.add(user)
        db.flush()
        db.add_all(
            [
                models.RoleMapping(user_id=user.id, name="管理员兼运营", role="operator", enabled=True, notification_enabled=True),
                models.RoleMapping(user_id=user.id, name="管理员兼运营", role="manager", enabled=True, notification_enabled=False),
            ]
        )
        batch = models.PlmArrivalBatch(
            arrival_date="2026-08-07",
            source_file="plm-2026-08-07.xlsx",
            source_hash="hash-plm-admin-owner",
            bloc_name="集团八部",
            row_count=1,
        )
        db.add(batch)
        db.flush()
        item = models.PlmArrivalItem(
            batch_id=batch.id,
            source_sheet="汇总表格",
            source_row=18,
            arrival_type="new_arrival",
            product_name="不能指派管理员",
            salesperson_name="PLM原销售",
            country="菲律宾",
            main_sku="PLM-ADMIN",
            sub_sku="PLM-ADMIN-A1",
            match_status="pending_assignment",
            raw_payload={},
        )
        db.add(item)
        db.commit()
        item_id = item.id

    assigned = client.post(
        f"/secondary-research/plm-arrival-assignments/{item_id}/assign",
        json={"salesperson_name": "管理员兼运营"},
    )

    assert assigned.status_code == 400
    assert "enabled operator" in assigned.json()["detail"]


def test_saving_draft_keeps_status_and_rejects_editing_another_operator() -> None:
    opportunity, claim = make_claim("SUB-A", "销售A", downstream_status="waiting_secondary_research")
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id

    response = client.patch(
        f"/secondary-research/{claim_id}",
        params={"salesperson_name": "销售A"},
        json={
            "secondary_research_at": "2026-07-12T14:08:00+08:00",
            "secondary_competitor_url": "https://shopee.ph/item/1",
            "secondary_conclusion": "无变化",
            "product_positioning": "利润款",
            "secondary_target_daily_sales": 12,
            "secondary_selling_points": "可折叠，适合海外仓",
        },
    )

    assert response.status_code == 200
    assert response.json()["downstream_status"] == "waiting_secondary_research"
    with SessionLocal() as db:
        saved = db.get(models.SalesClaimForecast, claim_id)
    assert saved.secondary_conclusion == "无变化"
    assert saved.secondary_research_at is None
    assert saved.secondary_target_daily_sales == 12
    assert saved.secondary_selling_points == "可折叠，适合海外仓"
    assert saved.secondary_research_submitted_at is None

    denied = client.patch(
        f"/secondary-research/{claim_id}",
        params={"salesperson_name": "销售B"},
        json={"secondary_conclusion": "覆盖他人"},
    )
    assert denied.status_code == 403


def test_group_submit_requires_every_child_and_splits_positioning_statuses() -> None:
    opportunity_a, claim_a = make_claim("SUB-A", "销售A", downstream_status="waiting_secondary_research")
    opportunity_b, claim_b = make_claim("SUB-B", "销售A", downstream_status="waiting_secondary_research")
    fill_research(claim_a, "利润款", "仍有利润")
    with SessionLocal() as db:
        db.add_all([opportunity_a, opportunity_b, claim_a, claim_b])
        db.commit()
        claim_ids = [claim_a.id, claim_b.id]

    incomplete = client.post(
        "/secondary-research/submit-group",
        params={"salesperson_name": "销售A"},
        json={"claim_record_ids": claim_ids},
    )
    assert incomplete.status_code == 400
    assert "SUB-B" in incomplete.json()["detail"]

    with SessionLocal() as db:
        second = db.get(models.SalesClaimForecast, claim_ids[1])
        fill_research(second, "淘汰款", "价格无优势")
        db.commit()

    submitted = client.post(
        "/secondary-research/submit-group",
        params={"salesperson_name": "销售A"},
        json={"claim_record_ids": claim_ids},
    )

    assert submitted.status_code == 200
    result = {item["sub_sku"]: item["downstream_status"] for item in submitted.json()}
    assert result == {"SUB-A": "waiting_listing", "SUB-B": "disabled"}
    with SessionLocal() as db:
        saved = [db.get(models.SalesClaimForecast, claim_id) for claim_id in claim_ids]
        audit_actions = [item.action for item in db.query(models.AuditLog).order_by(models.AuditLog.created_at).all()]
    assert all(item.secondary_research_submitted_at is not None for item in saved)
    assert audit_actions[-2:] == ["secondary_research.completed", "secondary_research.completed"]


def test_group_submit_accepts_stable_and_disables_clearance_positioning() -> None:
    opportunity_a, claim_a = make_claim("SUB-A", "销售A", downstream_status="waiting_secondary_research")
    opportunity_b, claim_b = make_claim("SUB-B", "销售A", downstream_status="waiting_secondary_research")
    with SessionLocal() as db:
        db.add_all([opportunity_a, opportunity_b, claim_a, claim_b])
        db.commit()
        claim_ids = [claim_a.id, claim_b.id]

    for claim_id, positioning in zip(claim_ids, ["稳定款", "清仓款"], strict=True):
        saved = client.patch(
            f"/secondary-research/{claim_id}",
            params={"salesperson_name": "销售A"},
            json={
                "secondary_conclusion": "已完成复盘",
                "product_positioning": positioning,
                "secondary_target_daily_sales": 10,
                "secondary_selling_points": "卖点清晰",
            },
        )
        assert saved.status_code == 200

    submitted = client.post(
        "/secondary-research/submit-group",
        params={"salesperson_name": "销售A"},
        json={"claim_record_ids": claim_ids},
    )

    assert submitted.status_code == 200
    assert {item["sub_sku"]: item["downstream_status"] for item in submitted.json()} == {
        "SUB-A": "waiting_listing",
        "SUB-B": "disabled",
    }


def test_group_submit_allows_blank_anchor_url_and_overwrites_al_with_submit_time() -> None:
    opportunity_a, claim_a = make_claim("SUB-A", "销售A", downstream_status="waiting_secondary_research")
    opportunity_b, claim_b = make_claim("SUB-B", "销售A", downstream_status="waiting_secondary_research")
    user_time = datetime(2026, 7, 12, 14, 8, tzinfo=timezone.utc)
    claim_a.secondary_conclusion = "仍有利润"
    claim_a.product_positioning = "利润款"
    claim_a.secondary_target_daily_sales = 11
    claim_a.secondary_selling_points = "利润稳定"
    claim_b.secondary_research_at = user_time
    claim_b.secondary_conclusion = "价格无优势"
    claim_b.product_positioning = "淘汰款"
    claim_b.secondary_target_daily_sales = 9
    claim_b.secondary_selling_points = "低价切入"
    with SessionLocal() as db:
        db.add_all([opportunity_a, opportunity_b, claim_a, claim_b])
        db.commit()
        claim_ids = [claim_a.id, claim_b.id]

    before = datetime.now(timezone.utc)
    response = client.post(
        "/secondary-research/submit-group",
        params={"salesperson_name": "销售A"},
        json={"claim_record_ids": claim_ids},
    )
    after = datetime.now(timezone.utc)

    assert response.status_code == 200
    with SessionLocal() as db:
        saved_a = db.get(models.SalesClaimForecast, claim_ids[0])
        saved_b = db.get(models.SalesClaimForecast, claim_ids[1])
    saved_a_time = ensure_utc(saved_a.secondary_research_at)
    saved_b_time = ensure_utc(saved_b.secondary_research_at)
    assert saved_a.secondary_competitor_url is None
    assert before <= saved_a_time <= after
    assert before <= saved_b_time <= after


def test_submitted_secondary_research_correction_preserves_submit_time_and_audits_changes() -> None:
    opportunity, claim = make_claim("SUB-A", "销售A", downstream_status="waiting_listing")
    fill_research(claim, "利润款", "原结论")
    submitted_at = datetime(2026, 7, 12, 15, tzinfo=timezone.utc)
    claim.secondary_research_submitted_at = submitted_at
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id

        result = services.correct_secondary_research(
            db,
            claim_id,
            schemas.SecondaryResearchDraftUpdate(
                secondary_conclusion="纠错后结论",
                product_positioning="稳定款",
            ),
            actor_name="销售A",
            actor_user_id="user-a",
            manager_access=False,
            operator_name="销售A",
        )
        db.commit()

        saved = db.get(models.SalesClaimForecast, claim_id)
        audit = db.query(models.AuditLog).filter_by(action="secondary_research.corrected").one()

    assert result["secondary_conclusion"] == "纠错后结论"
    assert ensure_utc(saved.secondary_research_submitted_at) == submitted_at
    assert saved.downstream_status == "waiting_listing"
    assert audit.actor_name == "销售A"
    assert audit.actor_user_id == "user-a"
    assert audit.detail["before"]["secondary_conclusion"] == "原结论"
    assert audit.detail["after"]["product_positioning"] == "稳定款"


def test_historical_secondary_correction_allows_partial_fact_edit_without_rerouting() -> None:
    opportunity, claim = make_claim("SUB-HIST", "销售A", downstream_status="historical_secondary_submitted")
    claim.secondary_research_submitted_at = datetime(2026, 7, 31, 10, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id

        result = services.correct_secondary_research(
            db,
            claim_id,
            schemas.SecondaryResearchDraftUpdate(product_positioning="利润款"),
            actor_name="销售A",
            actor_user_id="user-a",
            manager_access=False,
            operator_name="销售A",
        )
        db.commit()

        saved = db.get(models.SalesClaimForecast, claim_id)

    assert result["product_positioning"] == "利润款"
    assert saved.downstream_status == "historical_secondary_submitted"
    assert saved.secondary_conclusion is None
    assert saved.secondary_target_daily_sales is None


def test_secondary_research_correction_locks_claim_before_rerouting(monkeypatch) -> None:
    opportunity, claim = make_claim("SUB-LOCK", "销售A", downstream_status="waiting_listing")
    fill_research(claim, "利润款", "原结论")
    claim.secondary_research_submitted_at = datetime(2026, 7, 12, 15, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id

        lock_requests: list[bool] = []
        original = services.secondary_research_claim

        def capture_lock(session, record_id, lock=False):
            lock_requests.append(lock)
            return original(session, record_id)

        monkeypatch.setattr(services, "secondary_research_claim", capture_lock)
        services.correct_secondary_research(
            db,
            claim_id,
            schemas.SecondaryResearchDraftUpdate(product_positioning="淘汰款"),
            actor_name="销售A",
            actor_user_id="user-a",
            manager_access=False,
            operator_name="销售A",
        )

    assert lock_requests == [True]


def test_secondary_research_correction_permissions_and_existing_listing_never_rewinds() -> None:
    opportunity, claim = make_claim("SUB-A", "销售A", downstream_status="listing_observation")
    fill_research(claim, "利润款", "已进入刊登")
    claim.secondary_research_submitted_at = datetime(2026, 7, 12, 15, tzinfo=timezone.utc)
    listing = models.ListingRecord(
        source_group_key="source|period|PH|MAIN-1|销售A",
        source_claim_ids=[claim.id],
        source_type=opportunity.source_type,
        business_period=opportunity.batch,
        country="PH",
        site="PH",
        main_sku="MAIN-1",
        main_sku_name="洗衣机罩",
        salesperson_name="销售A",
        shop="UAT店铺",
        item="UAT-ITEM-1",
        listing_strategy="测试",
        first_period_start=date(2026, 7, 16),
        first_period_end=date(2026, 7, 22),
    )
    with SessionLocal() as db:
        db.add_all([opportunity, claim, listing])
        db.commit()
        claim_id = claim.id

        try:
            services.correct_secondary_research(
                db,
                claim_id,
                schemas.SecondaryResearchDraftUpdate(product_positioning="淘汰款"),
                actor_name="销售B",
                actor_user_id="user-b",
                manager_access=False,
                operator_name="销售B",
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("another operator must not correct this record")

        result = services.correct_secondary_research(
            db,
            claim_id,
            schemas.SecondaryResearchDraftUpdate(product_positioning="淘汰款"),
            actor_name="主管A",
            actor_user_id="manager-a",
            manager_access=True,
            operator_name=None,
        )
        db.commit()

    assert result["product_positioning"] == "淘汰款"
    assert result["downstream_status"] == "listing_observation"


def test_secondary_research_correction_reroutes_only_before_listing_exists() -> None:
    opportunity, claim = make_claim("SUB-A", "销售A", downstream_status="disabled")
    fill_research(claim, "淘汰款", "原判断淘汰")
    claim.secondary_research_submitted_at = datetime(2026, 7, 12, 15, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()

        result = services.correct_secondary_research(
            db,
            claim.id,
            schemas.SecondaryResearchDraftUpdate(
                secondary_conclusion="纠错为可刊登",
                product_positioning="利润款",
            ),
            actor_name="主管A",
            actor_user_id="manager-a",
            manager_access=True,
            operator_name=None,
        )
        db.commit()

    assert result["downstream_status"] == "waiting_listing"


def test_operator_can_correct_own_submitted_record_through_http() -> None:
    opportunity, claim = make_claim("SUB-HTTP", "销售A", downstream_status="waiting_listing")
    fill_research(claim, "利润款", "原结论")
    claim.secondary_research_submitted_at = datetime(2026, 7, 12, 15, tzinfo=timezone.utc)
    with SessionLocal() as db:
        db.add_all([opportunity, claim])
        db.commit()
        claim_id = claim.id

    response = client.patch(
        f"/secondary-research/{claim_id}/correction",
        params={"salesperson_name": "销售A"},
        json={"secondary_conclusion": "接口纠错", "product_positioning": "稳定款"},
    )

    assert response.status_code == 200
    assert response.json()["secondary_conclusion"] == "接口纠错"
    with SessionLocal() as db:
        saved = db.get(models.SalesClaimForecast, claim_id)
    assert saved.downstream_status == "waiting_listing"
    assert saved.secondary_research_submitted_at is not None


def make_claim(
    sub_sku: str,
    salesperson_name: str,
    downstream_status: str | None = None,
    business_period: str = "开发0710期",
) -> tuple[models.NewProductOpportunity, models.SalesClaimForecast]:
    opportunity = models.NewProductOpportunity(
        id=models.new_id(),
        source_type="selection1_developer_claim_feedback",
        source_file="选品1.xlsx",
        source_sheet="开发0710数据",
        source_row=1 if sub_sku == "SUB-A" else 2,
        batch=business_period,
        country="PH",
        site="PH",
        developer_department="产品开发八部",
        developer_name="张政",
        category_level1="家居厨卫",
        keyword="Washing Machine Cover",
        main_sku_name="洗衣机罩",
        main_sku="MAIN-1",
        sub_sku_name="黑色" if sub_sku == "SUB-A" else "灰色",
        sub_sku=sub_sku,
        reason="市场有销量",
        current_status="claim_submitted",
        snapshot={"Z": "https://shopee.ph/item/source", "AA": "365"},
    )
    claim = models.SalesClaimForecast(
        opportunity_id=opportunity.id,
        salesperson_name=salesperson_name,
        claim_result="claim",
        claim_daily_sales=3,
        source_column="platform",
        downstream_status=downstream_status,
    )
    return opportunity, claim


def add_operator(db, name: str, key_site: str = "PH") -> models.User:
    user = models.User(name=name, enabled=True)
    db.add(user)
    db.flush()
    db.add_all(
        [
            models.RoleMapping(
                user_id=user.id,
                name=name,
                role="operator",
                enabled=True,
                notification_enabled=True,
            ),
            models.OperatorAssignmentProfile(operator_name=name, key_site=key_site, enabled=True),
        ]
    )
    return user


def fill_research(claim: models.SalesClaimForecast, positioning: str, conclusion: str) -> None:
    claim.secondary_research_at = datetime(2026, 7, 12, 14, 8, tzinfo=timezone.utc)
    claim.secondary_competitor_url = "https://shopee.ph/item/recheck"
    claim.secondary_conclusion = conclusion
    claim.product_positioning = positioning
    claim.secondary_target_daily_sales = 12
    claim.secondary_selling_points = "卖点明确"


def ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
