from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app import services
from app.auth import require_roles
from app.db import get_db

router = APIRouter(prefix="/market-monitor", tags=["market-monitor"], dependencies=[Depends(require_roles("manager"))])


@router.get("/export")
def export_market_monitor(
    source_sheet: str | None = Query(None),
    business_period: str | None = Query(None),
    import_batch_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> Response:
    rows = services.list_market_monitor_rows(
        db,
        source_sheet=source_sheet,
        business_period=business_period,
        import_batch_id=import_batch_id,
    )
    content = services.build_market_monitor_workbook(rows)
    filename = quote(period_file_name("市场监控导出", business_period or source_sheet, import_batch_id))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


def period_file_name(prefix: str, source_sheet: str | None, import_batch_id: str | None) -> str:
    period = source_sheet or import_batch_id
    return f"{prefix}-{period}.xlsx" if period else f"{prefix}.xlsx"
