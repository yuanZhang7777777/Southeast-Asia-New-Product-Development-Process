import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient  # noqa: E402

from app import models, services  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.routers.events import current_event_revision, sse  # noqa: E402

client = TestClient(app)


def setup_function() -> None:
    os.environ["AUTH_REQUIRED"] = "true"
    os.environ["AUTH_SECRET_KEY"] = "test-auth-secret"
    get_settings.cache_clear()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def teardown_function() -> None:
    os.environ["AUTH_REQUIRED"] = "false"
    os.environ.pop("AUTH_SECRET_KEY", None)
    get_settings.cache_clear()


def test_event_revision_increments_when_workflow_writes_audit() -> None:
    with SessionLocal() as db:
        assert current_event_revision(db) == 0
        services.audit(db, "claim.submitted", "sales_claim_forecast", "claim-1", {})
        db.commit()
        assert current_event_revision(db) == 1


def test_event_stream_requires_token_when_auth_is_enabled() -> None:
    response = client.get("/events/stream")

    assert response.status_code == 401


def test_sse_payload_is_eventsource_compatible() -> None:
    assert sse({"revision": 3}) == 'data: {"revision":3}\n\n'
