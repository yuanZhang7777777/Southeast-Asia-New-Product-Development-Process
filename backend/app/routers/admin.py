from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import admin_console, finebi_auto_pull, models, schemas, services
from app.auth import AuthContext, require_roles
from app.company_category_importer import import_company_categories as import_company_category_workbook
from app.config import Settings, get_settings
from app.db import get_db
from app.dingtalk_user_sync import sync_configured_dingtalk_user_ids

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_roles("manager"))])


@router.get("/role-mappings", response_model=list[schemas.RoleMappingRead])
def role_mappings(db: Session = Depends(get_db)) -> list[models.RoleMapping]:
    return list(db.scalars(select(models.RoleMapping).order_by(models.RoleMapping.name)))


@router.post("/role-mappings", response_model=schemas.RoleMappingRead)
def create_role_mapping(
    payload: schemas.RoleMappingCreate,
    db: Session = Depends(get_db),
    _auth: object = Depends(require_roles("super_admin")),
) -> models.RoleMapping:
    item = models.RoleMapping(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/role-mappings/{mapping_id}", response_model=schemas.RoleMappingRead)
def update_role_mapping(
    mapping_id: str,
    payload: schemas.RoleMappingUpdate,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("super_admin")),
) -> models.RoleMapping:
    mapping = db.get(models.RoleMapping, mapping_id)
    if mapping is None:
        raise HTTPException(status_code=404, detail="role mapping not found")
    admin_console.update_role_mapping(
        db,
        mapping,
        payload.model_dump(exclude_unset=True),
        actor_name=auth.user.name if auth else None,
        actor_user_id=auth.user.id if auth else None,
    )
    db.commit()
    db.refresh(mapping)
    return mapping


@router.get("/users", response_model=list[schemas.AdminUserRead])
def list_users(
    db: Session = Depends(get_db),
    _auth: object = Depends(require_roles("super_admin")),
) -> list[schemas.AdminUserRead]:
    return admin_console.list_users(db)


@router.post("/users/{user_id}/reset-password", response_model=schemas.AdminPasswordResetResponse)
def reset_user_password(
    user_id: str,
    payload: schemas.AdminPasswordResetRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("super_admin")),
) -> schemas.AdminPasswordResetResponse:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    result = admin_console.reset_user_password(
        db,
        user,
        payload.new_password,
        actor_name=auth.user.name if auth else None,
        actor_user_id=auth.user.id if auth else None,
    )
    db.commit()
    return result


@router.patch("/users/{user_id}", response_model=schemas.UserRead)
def update_user(
    user_id: str,
    payload: schemas.AdminUserUpdateRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("super_admin")),
) -> models.User:
    user = db.get(models.User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if auth and auth.user.id == user.id and not payload.enabled:
        raise HTTPException(status_code=400, detail="cannot disable your own account")
    admin_console.set_user_enabled(
        db,
        user,
        payload.enabled,
        actor_name=auth.user.name if auth else None,
        actor_user_id=auth.user.id if auth else None,
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/import-batches", response_model=schemas.ImportBatchPage)
def list_import_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    source_type: str | None = Query(None),
    business_period: str | None = Query(None),
    batch_status: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
) -> schemas.ImportBatchPage:
    return admin_console.list_import_batches_page(
        db,
        page,
        page_size,
        source_type=source_type,
        business_period=business_period,
        batch_status=batch_status,
    )


@router.post("/import-batches/{batch_id}/disable", response_model=schemas.MessageResponse)
def disable_import_batch(
    batch_id: str,
    payload: schemas.DisableRequest,
    db: Session = Depends(get_db),
    auth: AuthContext | None = Depends(require_roles("super_admin")),
) -> schemas.MessageResponse:
    batch = db.get(models.ImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="import batch not found")
    count = services.set_import_batch_disabled(
        db,
        batch,
        payload.disabled,
        payload.reason,
        actor_name=auth.user.name if auth else None,
        actor_user_id=auth.user.id if auth else None,
    )
    db.commit()
    return schemas.MessageResponse(message="disabled" if payload.disabled else "restored", id=str(count))


@router.get("/feature-switches", response_model=list[schemas.FeatureSwitchRead])
def feature_switches(
    settings: Settings = Depends(get_settings),
    _auth: object = Depends(require_roles("super_admin")),
) -> list[schemas.FeatureSwitchRead]:
    return admin_console.feature_switches(settings)


@router.get("/company-categories", response_model=list[schemas.CompanyCategoryRead])
def company_categories(db: Session = Depends(get_db)) -> list[models.CompanyCategory]:
    return list(
        db.scalars(
            select(models.CompanyCategory)
            .where(models.CompanyCategory.enabled.is_(True))
            .order_by(models.CompanyCategory.level1, models.CompanyCategory.level2)
        )
    )


@router.post("/company-categories/import", response_model=schemas.CompanyCategoryImportResponse)
def import_company_categories(
    payload: schemas.CompanyCategoryImportRequest,
    db: Session = Depends(get_db),
    _auth: object = Depends(require_roles("super_admin")),
) -> dict[str, int]:
    report = import_company_category_workbook(db, payload.source_file, payload.source_sheet)
    db.commit()
    return report


@router.get("/operator-profiles", response_model=list[schemas.OperatorAssignmentProfileRead])
def operator_profiles(db: Session = Depends(get_db)) -> list[models.OperatorAssignmentProfile]:
    return list(
        db.scalars(
            select(models.OperatorAssignmentProfile).order_by(
                models.OperatorAssignmentProfile.display_order,
                models.OperatorAssignmentProfile.created_at,
                models.OperatorAssignmentProfile.operator_name,
            )
        )
    )


@router.post("/operator-profiles", response_model=schemas.OperatorAssignmentProfileRead)
def upsert_operator_profile(
    payload: schemas.OperatorAssignmentProfileCreate, db: Session = Depends(get_db)
) -> models.OperatorAssignmentProfile:
    values = payload.model_dump()
    item = db.scalar(
        select(models.OperatorAssignmentProfile).where(
            models.OperatorAssignmentProfile.operator_name == payload.operator_name
        )
    )
    if item is None:
        item = models.OperatorAssignmentProfile(
            operator_name=payload.operator_name,
            display_order=values.pop("display_order") or _next_profile_order(db),
        )
        db.add(item)
    elif values.get("display_order") is None:
        values.pop("display_order")
    _apply_operator_profile(item, values)
    _upsert_operator_role_mapping(db, item.operator_name)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/operator-profiles/{profile_id}", response_model=schemas.OperatorAssignmentProfileRead)
def update_operator_profile(
    profile_id: str, payload: schemas.OperatorAssignmentProfileUpdate, db: Session = Depends(get_db)
) -> models.OperatorAssignmentProfile:
    item = db.get(models.OperatorAssignmentProfile, profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail="operator profile not found")
    _apply_operator_profile(item, payload.model_dump(exclude_unset=True))
    db.commit()
    db.refresh(item)
    return item


@router.delete("/operator-profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_operator_profile(profile_id: str, db: Session = Depends(get_db)) -> Response:
    item = db.get(models.OperatorAssignmentProfile, profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail="operator profile not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/finebi/pull")
def finebi_pull(
    payload: schemas.FineBIPullRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    auth: AuthContext | None = Depends(require_roles("super_admin")),
) -> dict[str, object]:
    if not settings.finebi_auto_pull_enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="FineBI 自动拉取未开启：请在部署环境设置 FINEBI_AUTO_PULL_ENABLED=true 后重启服务",
        )
    try:
        report = finebi_auto_pull.pull_and_import(
            db,
            payload.week_label,
            imported_by=auth.user.name if auth else None,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except finebi_auto_pull.FineBIPullError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    db.commit()
    return report


@router.post("/dingtalk-user-ids/sync")
def sync_dingtalk_user_ids(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> dict[str, object]:
    report = sync_configured_dingtalk_user_ids(db, settings, write=True)
    db.commit()
    return {key: len(value) if isinstance(value, list) else value for key, value in report.items()}


def _apply_operator_profile(item: models.OperatorAssignmentProfile, values: dict[str, object]) -> None:
    for field in ("operator_name", "key_site", "key_category1", "key_category2", "key_categories", "assignment_priority", "display_order", "enabled"):
        if field in values:
            setattr(item, field, values[field])


def _next_profile_order(db: Session) -> int:
    return int(db.scalar(select(func.max(models.OperatorAssignmentProfile.display_order))) or 0) + 1


def _upsert_operator_role_mapping(db: Session, operator_name: str) -> None:
    mapping = db.scalar(
        select(models.RoleMapping).where(
            models.RoleMapping.name == operator_name,
            models.RoleMapping.role.in_(("operator", "sales")),
        )
    )
    if mapping is None:
        db.add(models.RoleMapping(name=operator_name, role="operator", enabled=True))
        return
    mapping.role = "operator"
    mapping.enabled = True
