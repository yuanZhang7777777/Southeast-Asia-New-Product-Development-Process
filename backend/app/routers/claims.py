import hashlib
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app import models, schemas, services
from app.auth import AuthContext, auth_required, read_token, require_roles, role_mappings_for_user, roles_from_mappings
from app.config import get_settings
from app.db import get_db
from app.excel_images import PUBLIC_UPLOAD_PREFIX, UPLOADED_SOURCES_ROOT
from app.oss_storage import read_oss_object_by_public_url, upload_claim_evidence_image

router = APIRouter(prefix="/claims", tags=["claims"])


@router.post("/pool/join", response_model=list[schemas.TaskRead])
def join_claim_pool(
    payload: schemas.ClaimPoolJoinRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator")),
) -> list[models.FlowTask]:
    assignee_name = auth.operator_name if auth else payload.assignee_name
    if not assignee_name:
        raise HTTPException(status_code=400, detail="assignee_name is required")
    try:
        tasks = services.join_selection2_claim_pool(
            db,
            payload.opportunity_ids,
            assignee_name=assignee_name,
            assignee_user_id=auth.user.id if auth else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return tasks


@router.post("", response_model=schemas.MessageResponse)
def submit_claim(
    payload: schemas.ClaimCreate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("operator")),
) -> schemas.MessageResponse:
    acting_as_admin = bool(auth and "super_admin" in auth.role_keys)
    if auth and not acting_as_admin and auth.operator_name and payload.salesperson_name != auth.operator_name:
        raise HTTPException(status_code=403, detail="salesperson_name does not match current operator")
    try:
        claim = services.submit_claim(
            db,
            payload,
            assignee_name=payload.salesperson_name if acting_as_admin else (auth.operator_name if auth else None),
            assignee_user_id=None if acting_as_admin else (auth.user.id if auth else None),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    return schemas.MessageResponse(message="claim submitted", id=claim.id)


@router.post("/evidence-images")
async def upload_evidence_image(
    opportunity_id: str = Form("unknown"),
    file: UploadFile = File(...),
    auth: AuthContext | None = Depends(require_roles("operator", "manager")),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    manager_access = bool(auth and auth.role_keys.intersection({"manager", "super_admin"}))
    if (
        auth
        and not manager_access
        and not services.can_upload_claim_evidence(db, opportunity_id, auth.operator_name, auth.user.id)
    ):
        raise HTTPException(status_code=403, detail="claim evidence does not belong to current operator")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="image must be 8MB or smaller")
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="only image files are allowed")

    ext = _safe_ext(Path(file.filename or "").suffix or content_type.rsplit("/", 1)[-1])
    digest = hashlib.sha1(data).hexdigest()[:16]
    try:
        url = upload_claim_evidence_image(data, ext, opportunity_id, digest)
    except Exception:
        # ponytail: OSS is primary, local file keeps v1 usable when credentials/network fail.
        url = None
    if not url:
        url = _save_local_evidence(data, ext, opportunity_id, digest)
    return {
        "name": file.filename or f"evidence.{ext}",
        "type": content_type,
        "size": len(data),
        "url": url,
    }


@router.get("/evidence-images/proxy")
def proxy_evidence_image(
    request: Request,
    url: str,
    token: str | None = None,
    db: Session = Depends(get_db),
) -> Response:
    _require_proxy_image_auth(request, token, db)
    if url.startswith(f"{PUBLIC_UPLOAD_PREFIX}/"):
        data, content_type = _read_local_evidence_url(url)
        return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})
    try:
        data, content_type = read_oss_object_by_public_url(url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail="failed to read OSS image") from exc
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "private, max-age=300"})


def _require_proxy_image_auth(request: Request, token: str | None, db: Session) -> None:
    settings = get_settings()
    header = request.headers.get("Authorization", "") if request else ""
    scheme, _, header_token = header.partition(" ")
    supplied_token = header_token if scheme.lower() == "bearer" else token
    if not supplied_token:
        if auth_required(settings):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization")
        return
    payload = read_token(settings, supplied_token)
    user = db.get(models.User, payload.get("sub"))
    if user is None or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user disabled or missing")
    roles = roles_from_mappings(role_mappings_for_user(db, user, settings))
    role_keys = {role.role for role in roles}
    if "super_admin" not in role_keys and role_keys.isdisjoint({"operator", "manager"}):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient role")


def _read_local_evidence_url(url: str) -> tuple[bytes, str]:
    relative = url.removeprefix(f"{PUBLIC_UPLOAD_PREFIX}/").lstrip("/")
    if not relative.startswith("claim-evidence/"):
        raise HTTPException(status_code=400, detail="unsupported local evidence URL")
    root = UPLOADED_SOURCES_ROOT.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="evidence image not found")
    return path.read_bytes(), f"image/{path.suffix.lower().strip('.') or 'png'}"


def _save_local_evidence(data: bytes, ext: str, opportunity_id: str, digest: str) -> str:
    segment = _safe_segment(opportunity_id)
    directory = UPLOADED_SOURCES_ROOT / "claim-evidence" / segment
    directory.mkdir(parents=True, exist_ok=True)
    filename = f"{digest}.{ext}"
    target = directory / filename
    if not target.exists():
        target.write_bytes(data)
    return f"{PUBLIC_UPLOAD_PREFIX}/claim-evidence/{segment}/{filename}"


def _safe_segment(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip(".-") or "unknown"


def _safe_ext(value: str) -> str:
    ext = value.lower().strip(".")
    return ext if re.fullmatch(r"[a-z0-9]{1,8}", ext) else "png"
