from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.db import get_db

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("", response_model=schemas.MessageResponse)
def submit_claim(payload: schemas.ClaimCreate, db: Session = Depends(get_db)) -> schemas.MessageResponse:
    try:
        claim = services.submit_claim(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return schemas.MessageResponse(message="claim submitted", id=claim.id)
