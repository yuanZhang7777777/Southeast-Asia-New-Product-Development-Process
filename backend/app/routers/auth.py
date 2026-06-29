from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.db import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/dingtalk/login", response_model=schemas.AuthLoginResponse)
def dingtalk_login(payload: schemas.DingTalkLoginRequest, db: Session = Depends(get_db)) -> schemas.AuthLoginResponse:
    dingtalk_user_id = payload.dingtalk_user_id or f"local-{payload.auth_code}"
    user = db.scalar(select(models.User).where(models.User.dingtalk_user_id == dingtalk_user_id))
    if user is None:
        user = models.User(dingtalk_user_id=dingtalk_user_id, name=payload.name)
        db.add(user)
        db.commit()
        db.refresh(user)
    return schemas.AuthLoginResponse(access_token=f"local-dev:{user.id}", user=user)
