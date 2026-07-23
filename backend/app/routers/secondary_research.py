from fastapi import APIRouter, Depends, HTTPException, Query
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


@router.patch("/{claim_record_id}", response_model=schemas.SecondaryResearchItemRead)
def save_secondary_research_draft(
    claim_record_id: str,
    payload: schemas.SecondaryResearchDraftUpdate,
    salesperson_name: str | None = Query(default=None),
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator")),
) -> dict:
    owner = auth.operator_name if auth and auth.operator_name else salesperson_name
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
    owner = auth.operator_name if auth and auth.operator_name else salesperson_name
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
