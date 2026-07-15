import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.auth import auth_required, read_token, role_mappings_for_user, roles_from_mappings
from app.config import Settings, get_settings
from app.db import SessionLocal

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
def stream_events(
    request: Request,
    token: str | None = Query(None),
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    with SessionLocal() as db:
        require_event_token(token, db, settings)

    async def event_stream():
        last_revision = load_event_revision()
        yield sse({"revision": last_revision})
        while not await request.is_disconnected():
            await asyncio.sleep(2)
            revision = load_event_revision()
            if revision != last_revision:
                last_revision = revision
                yield sse({"revision": revision})
            else:
                yield ": keepalive\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def load_event_revision() -> int:
    with SessionLocal() as db:
        return current_event_revision(db)


def current_event_revision(db: Session) -> int:
    return int(db.scalar(select(func.count(models.AuditLog.id))) or 0)


def require_event_token(token: str | None, db: Session, settings: Settings) -> None:
    if not token:
        if auth_required(settings):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization")
        return
    payload = read_token(settings, token)
    user = db.get(models.User, payload.get("sub"))
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user disabled or missing")
    if not roles_from_mappings(role_mappings_for_user(db, user, settings)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="no enabled role")


def sse(payload: dict[str, int]) -> str:
    return f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
