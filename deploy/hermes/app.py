import json
import os
import urllib.request

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Hermes DingTalk Adapter")


class TestMessage(BaseModel):
    title: str
    text: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "hermes-adapter"}


@app.post("/dingtalk/test")
def dingtalk_test(payload: TestMessage) -> dict[str, str]:
    webhook = os.getenv("DINGTALK_WEBHOOK_URL", "")
    if not webhook:
        return {"status": "skipped", "reason": "DINGTALK_WEBHOOK_URL not set"}

    body = json.dumps({"msgtype": "text", "text": {"content": f"{payload.title}\n{payload.text}"}}).encode("utf-8")
    request = urllib.request.Request(webhook, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=10) as response:
        response.read()
    return {"status": "sent"}
