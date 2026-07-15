import os
import sys
from datetime import datetime, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_secondary_research.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas, services  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_approved_review_marks_the_specific_claim_waiting_for_export() -> None:
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
    assert saved_claim.downstream_status == "waiting_export"
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
    assert saved_claim.downstream_status == "waiting_secondary_research"
    assert saved_claim.arrival_detected_at is not None


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


def test_secondary_research_defaults_latest_period_and_supports_history_and_all_periods() -> None:
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

    latest = client.get("/secondary-research", params={"salesperson_name": "销售A"}).json()
    history = client.get(
        "/secondary-research",
        params={"salesperson_name": "销售A", "business_period": "开发0703期"},
    ).json()
    all_periods = client.get(
        "/secondary-research",
        params={"salesperson_name": "销售A", "business_period": "__all__"},
    ).json()

    assert [group["business_period"] for group in latest] == ["开发0710期"]
    assert [group["business_period"] for group in history] == ["开发0703期"]
    assert sorted(group["business_period"] for group in all_periods) == ["开发0703期", "开发0710期"]


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
        },
    )

    assert response.status_code == 200
    assert response.json()["downstream_status"] == "waiting_secondary_research"
    with SessionLocal() as db:
        saved = db.get(models.SalesClaimForecast, claim_id)
    assert saved.secondary_conclusion == "无变化"
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


def test_group_submit_allows_blank_competitor_url_defaults_al_and_preserves_user_al() -> None:
    opportunity_a, claim_a = make_claim("SUB-A", "销售A", downstream_status="waiting_secondary_research")
    opportunity_b, claim_b = make_claim("SUB-B", "销售A", downstream_status="waiting_secondary_research")
    user_time = datetime(2026, 7, 12, 14, 8, tzinfo=timezone.utc)
    claim_a.secondary_conclusion = "仍有利润"
    claim_a.product_positioning = "利润款"
    claim_b.secondary_research_at = user_time
    claim_b.secondary_conclusion = "价格无优势"
    claim_b.product_positioning = "淘汰款"
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
    assert saved_b_time == user_time


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


def fill_research(claim: models.SalesClaimForecast, positioning: str, conclusion: str) -> None:
    claim.secondary_research_at = datetime(2026, 7, 12, 14, 8, tzinfo=timezone.utc)
    claim.secondary_competitor_url = "https://shopee.ph/item/recheck"
    claim.secondary_conclusion = conclusion
    claim.product_positioning = positioning


def ensure_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
