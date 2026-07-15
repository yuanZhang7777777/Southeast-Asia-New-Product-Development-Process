import os
import sys
from io import BytesIO
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(__file__).with_name('test_workflow.db')}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import models  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402


def setup_function() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_sync_role_mapping_user_ids_updates_only_unique_enabled_people() -> None:
    from app.dingtalk_user_sync import sync_role_mapping_user_ids

    with SessionLocal() as db:
        db.add_all(
            [
                models.RoleMapping(name="销售A", role="operator", enabled=True),
                models.RoleMapping(name="主管A", role="manager", enabled=True),
                models.RoleMapping(name="重复名", role="operator", enabled=True),
                models.RoleMapping(name="停用人", role="operator", enabled=False),
            ]
        )
        db.commit()

        report = sync_role_mapping_user_ids(
            db,
            [
                {"name": "销售A", "userid": "dt-a"},
                {"name": "主管A", "userId": "dt-m"},
                {"name": "重复名", "userid": "dt-x1"},
                {"name": "重复名", "userid": "dt-x2"},
                {"name": "停用人", "userid": "dt-disabled"},
            ],
            write=True,
        )
        db.commit()

        mappings = {item.name: item for item in db.query(models.RoleMapping).all()}

    assert mappings["销售A"].dingtalk_user_id == "dt-a"
    assert mappings["主管A"].dingtalk_user_id == "dt-m"
    assert mappings["重复名"].dingtalk_user_id is None
    assert mappings["停用人"].dingtalk_user_id is None
    assert [item["name"] for item in report["matched"]] == ["主管A", "销售A"]
    assert report["ambiguous"] == [{"name": "重复名", "role": "operator", "count": 2}]


def test_post_topapi_retries_temporary_rate_limit(monkeypatch) -> None:
    import app.dingtalk_user_sync as user_sync

    responses = iter(
        [
            b'{"errcode":88,"errmsg":"temporarily limited"}',
            b'{"errcode":0,"result":{"list":[]}}',
        ]
    )
    sleeps: list[float] = []

    class Response(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    monkeypatch.setattr(user_sync, "urlopen", lambda *_args, **_kwargs: Response(next(responses)))
    monkeypatch.setattr(user_sync.time, "sleep", sleeps.append)

    result = user_sync.post_topapi("token", "https://example.test", {})

    assert result["errcode"] == 0
    assert sleeps == [1]
