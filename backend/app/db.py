from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    from app import models

    Base.metadata.create_all(bind=engine)
    ensure_runtime_columns()


def ensure_runtime_columns() -> None:
    inspector = inspect(engine)
    if "new_product_opportunity" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("new_product_opportunity")}
    if "category_level2" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE new_product_opportunity ADD COLUMN category_level2 VARCHAR(128)"))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
