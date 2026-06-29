from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import init_db
from app.routers import (
    admin,
    arrival,
    assignments,
    auth,
    claims,
    health,
    notifications,
    opportunities,
    reviews,
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


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(opportunities.router)
app.include_router(assignments.router)
app.include_router(tasks.router)
app.include_router(claims.router)
app.include_router(reviews.router)
app.include_router(stocking.router)
app.include_router(arrival.router)
app.include_router(summary.router)
app.include_router(notifications.router)
app.include_router(admin.router)
