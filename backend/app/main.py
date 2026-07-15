from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.excel_images import UPLOADED_SOURCES_ROOT
from app.routers import (
    admin,
    arrival,
    assignments,
    auth,
    claims,
    events,
    health,
    market_monitor,
    notifications,
    opportunities,
    product_board,
    reviews,
    secondary_research,
    stocking,
    summary,
    tasks,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

product_image_root = UPLOADED_SOURCES_ROOT / "product-images"
product_image_root.mkdir(parents=True, exist_ok=True)
app.mount("/uploaded-sources/product-images", StaticFiles(directory=product_image_root), name="product_images")


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(opportunities.router)
app.include_router(product_board.router)
app.include_router(assignments.router)
app.include_router(tasks.router)
app.include_router(claims.router)
app.include_router(events.router)
app.include_router(reviews.router)
app.include_router(secondary_research.router)
app.include_router(stocking.router)
app.include_router(market_monitor.router)
app.include_router(arrival.router)
app.include_router(summary.router)
app.include_router(notifications.router)
app.include_router(admin.router)
