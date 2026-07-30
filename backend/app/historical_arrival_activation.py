"""Bridge verified historical Selection1 claims into current secondary-research branches."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, services
from app.site_codes import normalize_site_code
from app.workflow_status import CLAIM_RESULT_CLAIM, CLAIM_WAITING_ARRIVAL, OPPORTUNITY_CLAIM_SUBMITTED


HISTORICAL_CLAIM_COLUMNS = ("history_selection1",)
ACTIVATION_CLAIM_SOURCE = "historical_arrival_activation"
BLOCKED_POSITIONINGS = {"淘汰款", "清仓款", "淘汰", "清仓"}


def activate_historical_arrival(
    db: Session,
    item: models.PlmArrivalItem,
    *,
    apply: bool,
) -> dict[str, Any]:
    """Return a safe activation decision for one PLM-confirmed new-arrival row."""
    if item.arrival_type != "new_arrival":
        return {"status": "not_new_arrival", "historical_claim_ids": []}
    if not normalize_site_code(item.country) or not _sku_key(item.sub_sku):
        return {"status": "missing_site_or_sub_sku", "historical_claim_ids": []}

    evidence = _historical_evidence(db, item)
    if not evidence:
        return {"status": "no_historical_claim", "historical_claim_ids": []}
    evidence, main_status = _resolve_main_sku_evidence(evidence, item)
    if not evidence:
        return {"status": main_status or "main_sku_ambiguous", "historical_claim_ids": []}
    historical_claim_ids = [claim.id for claim, _ in evidence]

    if _has_historical_secondary_research(db, item, evidence):
        return {"status": "historical_secondary_research", "historical_claim_ids": historical_claim_ids}

    listing_status = listing_status_for_sku(
        db,
        country=item.country,
        main_sku=item.main_sku,
        sub_sku=item.sub_sku,
    )
    if listing_status:
        return {"status": listing_status, "historical_claim_ids": historical_claim_ids}

    activations: list[dict[str, Any]] = []
    runtime_claim_ids: list[str] = []
    owner_gaps: list[dict[str, str]] = []
    for opportunity_id, owner_name, claims, opportunity in _claimant_groups(evidence):
        mapping_status, _ = _enabled_operator_mapping(db, owner_name)
        claim_ids = [claim.id for claim in claims]
        activation = {
            "opportunity_id": opportunity_id,
            "owner_name": owner_name,
            "historical_claim_ids": claim_ids,
        }
        if mapping_status != "owner_mapped":
            activation["status"] = mapping_status
            activations.append(activation)
            owner_gaps.append({"owner_name": owner_name, "status": mapping_status})
            continue

        current_claim = _current_platform_claim(db, opportunity_id, owner_name)
        if current_claim is not None:
            if apply and not _claim_arrival_exists(db, current_claim.id):
                _open_and_record(db, item, current_claim, claim_ids)
            activation.update({"status": "already_activated" if _claim_arrival_exists(db, current_claim.id) else "existing_platform_claim", "runtime_claim_id": current_claim.id})
            runtime_claim_ids.append(current_claim.id)
            activations.append(activation)
            continue

        if not apply:
            activation["status"] = "historical_candidate"
            activations.append(activation)
            continue

        runtime_claim = models.SalesClaimForecast(
            opportunity_id=opportunity_id,
            salesperson_name=owner_name,
            claim_result=CLAIM_RESULT_CLAIM,
            claim_daily_sales=claims[0].claim_daily_sales,
            source_column="platform",
            claim_source=ACTIVATION_CLAIM_SOURCE,
            downstream_status=CLAIM_WAITING_ARRIVAL,
            note=json.dumps(
                {
                    "historical_claim_ids": claim_ids,
                    "primary_historical_claim_id": claims[0].id,
                    "owner_source": "historical_claimant",
                    "plm_arrival_salesperson": item.salesperson_name,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
        db.add(runtime_claim)
        db.flush()
        if opportunity.current_status == "historical_archive":
            opportunity.current_status = OPPORTUNITY_CLAIM_SUBMITTED
        _open_and_record(db, item, runtime_claim, claim_ids)
        activation.update({"status": "activated", "runtime_claim_id": runtime_claim.id})
        runtime_claim_ids.append(runtime_claim.id)
        activations.append(activation)

    active = [row for row in activations if row["status"] in {"activated", "existing_platform_claim", "already_activated"}]
    if active:
        status = "activated" if any(row["status"] == "activated" for row in active) else "already_activated"
    elif owner_gaps:
        status = owner_gaps[0]["status"]
    else:
        status = "historical_candidate"
    primary = active[0] if active else next((row for row in activations if row["status"] == "historical_candidate"), None)
    return {
        "status": status,
        "historical_claim_ids": historical_claim_ids,
        "runtime_claim_id": runtime_claim_ids[0] if runtime_claim_ids else None,
        "runtime_claim_ids": runtime_claim_ids,
        "opportunity_id": primary.get("opportunity_id") if primary else None,
        "owner_name": primary.get("owner_name") if primary else None,
        "activations": activations,
        "owner_gaps": owner_gaps,
    }


def _historical_evidence(
    db: Session,
    item: models.PlmArrivalItem,
) -> list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]]:
    site = normalize_site_code(item.country)
    sub_sku = _sku_key(item.sub_sku)
    if not site or not sub_sku:
        return []
    rows = db.execute(
        select(models.SalesClaimForecast, models.NewProductOpportunity)
        .join(models.NewProductOpportunity, models.NewProductOpportunity.id == models.SalesClaimForecast.opportunity_id)
        .where(
            models.SalesClaimForecast.source_column.in_(HISTORICAL_CLAIM_COLUMNS),
            models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
        )
    ).all()
    matches = [
        (claim, opportunity)
        for claim, opportunity in rows
        if (claim.claim_daily_sales or 0) > 0
        and claim.product_positioning not in BLOCKED_POSITIONINGS
        and _sku_key(opportunity.sub_sku) == sub_sku
        and normalize_site_code(opportunity.site or opportunity.country) == site
    ]
    return sorted(matches, key=lambda row: _evidence_sort_key(row, item))


def _resolve_main_sku_evidence(
    evidence: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]],
    item: models.PlmArrivalItem,
) -> tuple[list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]], str | None]:
    item_main_sku = _sku_key(item.main_sku)
    exact = [row for row in evidence if item_main_sku and _sku_key(row[1].main_sku) == item_main_sku]
    if exact:
        return exact, None
    main_skus = {_sku_key(opportunity.main_sku) for _, opportunity in evidence if _sku_key(opportunity.main_sku)}
    return (evidence, None) if len(main_skus) <= 1 else ([], "main_sku_ambiguous")


def _claimant_groups(
    evidence: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]],
) -> list[tuple[str, str, list[models.SalesClaimForecast], models.NewProductOpportunity]]:
    groups: dict[tuple[str, str], tuple[list[models.SalesClaimForecast], models.NewProductOpportunity]] = {}
    for claim, opportunity in evidence:
        owner_name = (claim.salesperson_name or "").strip()
        if not owner_name:
            continue
        claims, representative = groups.setdefault((opportunity.id, owner_name), ([], opportunity))
        claims.append(claim)
    return [
        (opportunity_id, owner_name, claims, opportunity)
        for (opportunity_id, owner_name), (claims, opportunity) in groups.items()
    ]


def _has_historical_secondary_research(
    db: Session,
    item: models.PlmArrivalItem,
    evidence: list[tuple[models.SalesClaimForecast, models.NewProductOpportunity]],
) -> bool:
    if any(claim.secondary_research_submitted_at is not None for claim, _ in evidence):
        return True
    site = normalize_site_code(item.country)
    sub_sku = _sku_key(item.sub_sku)
    for opportunity in db.scalars(select(models.NewProductOpportunity).where(models.NewProductOpportunity.sub_sku.is_not(None))):
        if _sku_key(opportunity.sub_sku) != sub_sku or normalize_site_code(opportunity.site or opportunity.country) != site:
            continue
        snapshot = opportunity.snapshot or {}
        if snapshot.get("has_secondary_research") or snapshot.get("secondary_research_complete"):
            return True
        if (snapshot.get("secondary") or {}).get("secondary_research_at"):
            return True
    return False


def _evidence_sort_key(
    row: tuple[models.SalesClaimForecast, models.NewProductOpportunity],
    item: models.PlmArrivalItem,
) -> tuple[int, int, str, int, str]:
    claim, opportunity = row
    return (
        0 if _sku_key(opportunity.main_sku) == _sku_key(item.main_sku) else 1,
        0 if opportunity.source_type == "selection1_developer_claim_feedback" else 1,
        opportunity.batch or "",
        opportunity.source_row or 0,
        claim.id,
    )


def listing_status_for_sku(
    db: Session,
    *,
    country: str | None,
    main_sku: str | None,
    sub_sku: str | None,
) -> str | None:
    site = normalize_site_code(country)
    sub_sku = _sku_key(sub_sku)
    main_sku = _sku_key(main_sku)
    if not site or not sub_sku:
        return None
    listings = list(db.scalars(select(models.ListingRecord).where(models.ListingRecord.status == "active")))
    bound_listing_ids: set[str] = set()
    bindings = db.execute(
        select(models.ListingSkuBinding, models.ListingRecord)
        .join(models.ListingRecord, models.ListingRecord.id == models.ListingSkuBinding.listing_record_id)
        .where(models.ListingRecord.status == "active")
    ).all()
    for binding, listing in bindings:
        if normalize_site_code(listing.site or listing.country) != site:
            continue
        bound_listing_ids.add(listing.id)
        if _sku_key(binding.sub_sku) == sub_sku:
            return "already_listed"
    for listing in listings:
        if normalize_site_code(listing.site or listing.country) != site:
            continue
        representative_sub_sku = _sku_key(listing.representative_sub_sku)
        if representative_sub_sku:
            if representative_sub_sku == sub_sku:
                return "already_listed"
            continue
        if listing.id in bound_listing_ids:
            continue
        if _sku_key(listing.main_sku) == main_sku:
            return "listing_binding_unresolved"
    return None


def _current_platform_claim(
    db: Session,
    opportunity_id: str,
    salesperson_name: str,
) -> models.SalesClaimForecast | None:
    if not opportunity_id or not salesperson_name:
        return None
    matches = list(
        db.scalars(
            select(models.SalesClaimForecast).where(
                models.SalesClaimForecast.opportunity_id == opportunity_id,
                models.SalesClaimForecast.source_column == "platform",
                models.SalesClaimForecast.claim_result == CLAIM_RESULT_CLAIM,
                models.SalesClaimForecast.downstream_status.in_((CLAIM_WAITING_ARRIVAL, "waiting_secondary_research")),
                models.SalesClaimForecast.salesperson_name == salesperson_name,
            )
        )
    )
    return matches[0] if len(matches) == 1 else None


def _enabled_operator_mapping(
    db: Session,
    salesperson_name: str | None,
) -> tuple[str, models.RoleMapping | None]:
    name = (salesperson_name or "").strip()
    if not name:
        return "owner_unmapped", None
    rows = db.execute(
        select(models.RoleMapping, models.User)
        .outerjoin(models.User, models.User.id == models.RoleMapping.user_id)
        .where(
            models.RoleMapping.name == name,
            models.RoleMapping.role == "operator",
            models.RoleMapping.enabled.is_(True),
        )
        .order_by(models.RoleMapping.updated_at.desc(), models.RoleMapping.created_at.desc())
    ).all()
    valid = [
        mapping
        for mapping, user in rows
        if (mapping.user_id or mapping.dingtalk_user_id)
        and (mapping.user_id is None or (user is not None and user.enabled))
    ]
    if not valid:
        return "owner_unmapped", None
    if len({mapping.dingtalk_user_id for mapping in valid}) > 1:
        return "owner_ambiguous", None
    return "owner_mapped", valid[0]


def _open_and_record(
    db: Session,
    item: models.PlmArrivalItem,
    claim: models.SalesClaimForecast,
    historical_claim_ids: list[str],
) -> None:
    if _arrival_record_exists(db, item.batch_id, claim.id):
        return
    services.open_secondary_research(db, claim.id, item.latest_storage_time)
    db.add(
        models.ArrivalRecord(
            opportunity_id=claim.opportunity_id,
            claim_record_id=claim.id,
            plm_arrival_batch_id=item.batch_id,
            plm_arrival_item_id=item.id,
            salesperson_name=claim.salesperson_name,
            country=item.country,
            warehouse=item.warehouse,
            arrived_quantity=_int_or_none(item.available_quantity),
            arrived_at=item.latest_storage_time,
            note=json.dumps(
                {
                    "source": "plm_historical_claim_activation",
                    "historical_claim_ids": historical_claim_ids,
                    "plm_arrival_salesperson": item.salesperson_name,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        )
    )


def _claim_arrival_exists(db: Session, claim_id: str) -> bool:
    return db.scalar(
        select(models.ArrivalRecord.id).where(models.ArrivalRecord.claim_record_id == claim_id)
    ) is not None


def _arrival_record_exists(db: Session, batch_id: str, claim_id: str) -> bool:
    return db.scalar(
        select(models.ArrivalRecord.id).where(
            models.ArrivalRecord.plm_arrival_batch_id == batch_id,
            models.ArrivalRecord.claim_record_id == claim_id,
        )
    ) is not None


def _sku_key(value: Any) -> str:
    return "".join(str(value or "").split()).upper()


def _int_or_none(value: Any) -> int | None:
    return int(value) if value is not None else None
