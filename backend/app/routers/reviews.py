from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas, services
from app.db import get_db

router = APIRouter(prefix="/reviews", tags=["reviews"])


@router.post("", response_model=schemas.MessageResponse)
def submit_review(payload: schemas.ReviewCreate, db: Session = Depends(get_db)) -> schemas.MessageResponse:
    record = services.submit_review(db, payload)
    db.commit()
    return schemas.MessageResponse(message="review submitted", id=record.id)
