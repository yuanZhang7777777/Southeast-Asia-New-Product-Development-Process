import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_dashboard_counts.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models, schemas  # noqa: E402
from app.auth import AuthContext  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.dashboard import dashboard_counts_owner  # noqa: E402


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def make_claim(
    main_sku: str,
    sub_sku: str,
    salesperson_name: str,
    downstream_status: str,
    secondary_research_submitted_at: datetime | None = None,
) -> tuple[models.NewProductOpportunity, models.SalesClaimForecast]:
    opportunity = models.NewProductOpportunity(
        id=models.new_id(),
        source_type="selection1_developer_claim_feedback",
        batch="开发0710期",
        country="PH",
        site="PH",
        main_sku=main_sku,
        sub_sku=sub_sku,
        current_status="ready_for_stocking",
    )
    claim = models.SalesClaimForecast(
        opportunity_id=opportunity.id,
        salesperson_name=salesperson_name,
        claim_result="claim",
        downstream_status=downstream_status,
        secondary_research_submitted_at=secondary_research_submitted_at,
    )
    return opportunity, claim


def make_listing(
    listing_id: str,
    salesperson_name: str,
    *,
    status: str = "active",
    source_type: str = "selection1_developer_claim_feedback",
    period_status: str = "pending_review",
    record_source: str = "platform",
) -> models.ListingRecord:
    listing = models.ListingRecord(
        id=listing_id,
        source_group_key=f"task-{listing_id}",
        source_claim_ids=[],
        source_type=source_type,
        business_period="开发0710期",
        country="PH",
        main_sku=f"MAIN-{listing_id}",
        salesperson_name=salesperson_name,
        shop=f"Shop-{listing_id}",
        item=f"ITEM-{listing_id}",
        listing_strategy="策略",
        first_period_start=date(2026, 7, 2),
        first_period_end=date(2026, 7, 8),
        status=status,
    )
    listing.periods.append(
        models.ItemObservationPeriod(
            week_number=1,
            period_start=date(2026, 7, 2),
            period_end=date(2026, 7, 8),
            status=period_status,
            record_source=record_source,
        )
    )
    return listing


def seed_workspace() -> None:
    submitted = datetime(2026, 7, 12, 10, tzinfo=timezone.utc)
    with SessionLocal() as db:
        research_a = make_claim("MAIN-R1", "SUB-R1", "销售A", "waiting_secondary_research")
        research_b = make_claim("MAIN-R2", "SUB-R2", "销售B", "waiting_secondary_research")
        research_done = make_claim("MAIN-R1", "SUB-R3", "销售A", "waiting_secondary_research", submitted)
        listing_a1 = make_claim("MAIN-L1", "SUB-L1", "销售A", "waiting_listing")
        listing_a2 = make_claim("MAIN-L1", "SUB-L2", "销售A", "waiting_listing")
        listing_b = make_claim("MAIN-L2", "SUB-L3", "销售B", "waiting_listing")
        for opportunity, claim in (research_a, research_b, research_done, listing_a1, listing_a2, listing_b):
            db.add_all([opportunity, claim])
        db.add_all(
            [
                make_listing("obs-a", "销售A"),
                make_listing("obs-b", "销售B"),
                make_listing("obs-completed", "销售A", period_status="completed"),
                make_listing("obs-voided", "销售A", status="voided"),
                make_listing("obs-history", "销售A", source_type="history_finebi", record_source="history_finebi"),
            ]
        )
        db.commit()


def test_dashboard_counts_scope_allows_managers_and_locks_operators() -> None:
    user = models.User(name="测试用户", enabled=True)
    manager = AuthContext(user=user, roles=[schemas.AuthRoleRead(role="manager", name="主管")])
    operator = AuthContext(user=user, roles=[schemas.AuthRoleRead(role="operator", name="运营甲")])

    assert dashboard_counts_owner(manager, None) is None
    assert dashboard_counts_owner(manager, "运营乙") == "运营乙"
    assert dashboard_counts_owner(operator, None) == "运营甲"
    assert dashboard_counts_owner(operator, "运营乙") == "运营甲"


def test_dashboard_counts_split_by_owner_and_exclude_finished_or_voided_rows() -> None:
    seed_workspace()

    manager_counts = client.get("/dashboard/counts").json()
    operator_counts = client.get("/dashboard/counts", params={"salesperson_name": "销售A"}).json()

    # 主管视角=全部；已提交二次调研、已完成复盘、已作废与历史周期不计入。
    assert manager_counts == {"waiting_listing": 2, "waiting_secondary_research": 2, "pending_review_periods": 2}
    # 运营视角=本人。
    assert operator_counts == {"waiting_listing": 1, "waiting_secondary_research": 1, "pending_review_periods": 1}


def test_dashboard_counts_match_target_page_rows() -> None:
    seed_workspace()

    for params, owner_label in (({}, "全部"), ({"salesperson_name": "销售A"}, "销售A")):
        counts = client.get("/dashboard/counts", params=params).json()

        # 待二次调研 = 二次调研工作台“待处理”行数（未提交且 waiting_secondary_research 的认领记录）。
        research_groups = client.get(
            "/secondary-research",
            params={**params, "business_period": "__all__", "downstream_status": "waiting_secondary_research"},
        ).json()
        pending_research_rows = [
            item
            for group in research_groups
            for item in group["items"]
            if not item["secondary_research_submitted_at"]
        ]
        assert counts["waiting_secondary_research"] == len(pending_research_rows), owner_label

        # 待刊登 = 刊登与观察工作台“刊登任务”卡片数（requires_confirmation 的待刊登任务组）。
        workbench = client.get("/listing-workbench", params=params).json()
        waiting_tasks = [task for task in workbench["pending_listing_tasks"] if task["requires_confirmation"]]
        assert counts["waiting_listing"] == len(waiting_tasks), owner_label

        # 待复盘 = 周期观察在 status=pending_review 筛选下可见的行数（仅生效 listing）。
        review_view = client.get("/listing-workbench", params={**params, "view": "pending_review"}).json()
        listing_status = {item["id"]: item["status"] for item in review_view["listing_records"]}
        pending_review_rows = [
            row for row in review_view["period_rows"] if listing_status.get(row["listing_record_id"]) == "active"
        ]
        assert counts["pending_review_periods"] == len(pending_review_rows), owner_label
