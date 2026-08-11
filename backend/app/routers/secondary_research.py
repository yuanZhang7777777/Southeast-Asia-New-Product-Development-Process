from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app import schemas, services
from app.auth import AuthContext, require_roles
from app.db import get_db
from app.workflow_status import CLAIM_WAITING_SECONDARY_RESEARCH

router = APIRouter(prefix="/secondary-research", tags=["secondary-research"])


def secondary_research_owner(auth: AuthContext | None, requested_owner: str | None) -> str | None:
    if auth is None or auth.role_keys.intersection({"manager", "super_admin"}):
        return requested_owner
    return auth.operator_name


def secondary_research_write_owner(auth: AuthContext | None, requested_owner: str | None) -> str | None:
    if auth is None:
        return requested_owner
    if auth.role_keys.intersection({"manager", "super_admin"}) and requested_owner:
        return requested_owner
    return auth.operator_name


@router.get("", response_model=list[schemas.SecondaryResearchGroupRead])
def list_secondary_research(
    salesperson_name: str | None = None,
    business_period: str | None = None,
    downstream_status: str | None = Query(default=CLAIM_WAITING_SECONDARY_RESEARCH),
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> list[dict]:
    owner = secondary_research_owner(auth, salesperson_name)
    return services.list_secondary_research_groups(db, owner, business_period, downstream_status)


@router.get("/export")
def export_secondary_research(
    scenario: str = Query(default="pending"),
    salesperson_name: str | None = None,
    business_period: str | None = None,
    country: str | None = None,
    query: str | None = None,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> Response:
    owner = secondary_research_owner(auth, salesperson_name)
    try:
        rows = services.list_secondary_research_export_rows(db, owner, business_period, scenario, country, query)
        content = services.build_secondary_research_export_workbook(rows)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = quote("二次调研导出.xlsx")
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/manual", response_model=schemas.SecondaryResearchItemRead)
def create_manual_secondary_research(
    payload: schemas.ManualSecondaryResearchCreate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> dict:
    owner = secondary_research_write_owner(auth, payload.salesperson_name)
    if not owner:
        raise HTTPException(status_code=400, detail="salesperson_name is required")
    try:
        item = services.create_manual_secondary_research(
            db,
            payload,
            owner,
            actor_name=auth.user.name if auth else owner,
            actor_user_id=auth.user.id if auth else None,
        )
    except ValueError as exc:
        status_code = 409 if "已存在于后续阶段" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    db.commit()
    return item


@router.get("/plm-arrival-assignments", response_model=list[schemas.PlmArrivalAssignmentRead])
def list_plm_arrival_assignments(
    db: Session = Depends(get_db),
    _auth: AuthContext | None = Depends(require_roles("manager")),
) -> list[dict]:
    return services.list_plm_arrival_assignments(db)


@router.post("/plm-arrival-assignments/assign-group", response_model=list[schemas.PlmArrivalAssignmentRead])
def assign_plm_arrival_assignment_group(
    payload: schemas.PlmArrivalAssignmentGroupRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> list[dict]:
    try:
        result = services.assign_plm_arrival_group_to_secondary_research(
            db,
            payload.plm_arrival_item_ids,
            payload.salesperson_name,
            actor_name=auth.user.name if auth else "local",
            actor_user_id=auth.user.id if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/plm-arrival-assignments/close-group", response_model=list[schemas.PlmArrivalAssignmentRead])
def close_plm_arrival_assignment_group(
    payload: schemas.PlmArrivalAssignmentGroupCloseRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> list[dict]:
    try:
        result = services.close_plm_arrival_assignment_group(
            db,
            payload.plm_arrival_item_ids,
            payload.reason,
            actor_name=auth.user.name if auth else "local",
            actor_user_id=auth.user.id if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/plm-arrival-assignments/{plm_arrival_item_id}/assign", response_model=schemas.PlmArrivalAssignmentRead)
def assign_plm_arrival_assignment(
    plm_arrival_item_id: str,
    payload: schemas.PlmArrivalAssignmentRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> dict:
    try:
        result = services.assign_plm_arrival_to_secondary_research(
            db,
            plm_arrival_item_id,
            payload.salesperson_name,
            actor_name=auth.user.name if auth else "local",
            actor_user_id=auth.user.id if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.post("/plm-arrival-assignments/{plm_arrival_item_id}/close", response_model=schemas.PlmArrivalAssignmentRead)
def close_plm_arrival_assignment(
    plm_arrival_item_id: str,
    payload: schemas.PlmArrivalAssignmentCloseRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("manager")),
) -> dict:
    try:
        result = services.close_plm_arrival_assignment(
            db,
            plm_arrival_item_id,
            payload.reason,
            actor_name=auth.user.name if auth else "local",
            actor_user_id=auth.user.id if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return result


@router.patch("/{claim_record_id}", response_model=schemas.SecondaryResearchItemRead)
def save_secondary_research_draft(
    claim_record_id: str,
    payload: schemas.SecondaryResearchDraftUpdate,
    salesperson_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator")),
) -> dict:
    owner = secondary_research_write_owner(auth, salesperson_name)
    if not owner:
        raise HTTPException(status_code=400, detail="salesperson_name is required")
    try:
        item = services.update_secondary_research_draft(db, claim_record_id, payload, owner)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return item


@router.patch("/{claim_record_id}/correction", response_model=schemas.SecondaryResearchItemRead)
def correct_secondary_research(
    claim_record_id: str,
    payload: schemas.SecondaryResearchDraftUpdate,
    salesperson_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
) -> dict:
    operator_name = auth.operator_name if auth else salesperson_name
    manager_access = bool(auth and auth.role_keys.intersection({"manager", "super_admin"}))
    actor_name = auth.user.name if auth else (salesperson_name or "local")
    actor_user_id = auth.user.id if auth else None
    if not manager_access and not operator_name:
        raise HTTPException(status_code=400, detail="salesperson_name is required")
    try:
        item = services.correct_secondary_research(
            db,
            claim_record_id,
            payload,
            actor_name=actor_name,
            actor_user_id=actor_user_id,
            manager_access=manager_access,
            operator_name=operator_name,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return item

@router.post("/submit-group", response_model=list[schemas.SecondaryResearchItemRead])
def submit_secondary_research_group(
    payload: schemas.SecondaryResearchSubmitGroupRequest,
    salesperson_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator")),
) -> list[dict]:
    owner = secondary_research_write_owner(auth, salesperson_name)
    if not owner:
        raise HTTPException(status_code=400, detail="salesperson_name is required")
    try:
        items = services.submit_secondary_research_group(db, payload.claim_record_ids, owner)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return items
