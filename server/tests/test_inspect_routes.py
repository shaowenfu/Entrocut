from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth_service import new_id
from app.auth_store import now_utc, to_iso
from app.main import app, rate_limit_service, settings, store, token_service


class _DummyResponse:
    def __init__(self, *, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "google_api_key", "test-google-key")
    monkeypatch.setattr(settings, "inspect_provider_mode", "google_gemini")
    monkeypatch.setattr(settings, "inspect_default_model", "gemini-2.5-flash")
    rate_limit_service._memory_counters.clear()
    rate_limit_service._redis = None
    rate_limit_service._redis_ready = None


def _create_user() -> dict[str, Any]:
    current_time = now_utc()
    user = {
        "_id": new_id("user"),
        "email": f"{new_id('mail')}@inspect.local",
        "display_name": "Inspect Test User",
        "avatar_url": None,
        "status": "active",
        "primary_provider": "google",
        "plan": "free",
        "quota_total": 10000,
        "quota_status": "healthy",
        "remaining_quota": 10000,
        "created_at": to_iso(current_time),
        "updated_at": to_iso(current_time),
        "last_login_at": to_iso(current_time),
    }
    store.mongo.create_user(user)
    return user


def _make_request_payload() -> dict[str, Any]:
    return {
        "mode": "choose",
        "task_summary": "为旅行视频开头选择更有出发感的镜头。",
        "hypothesis_summary": "优先找明显处于旅程开始状态的镜头。",
        "question": "这几个候选里哪个最适合作为旅行视频开头？",
        "criteria": [
            {"name": "departure_feel", "description": "是否有明显的出发前或旅程刚开始的感觉。"}
        ],
        "candidates": [
            {
                "clip_id": "clip_001",
                "asset_id": "asset_001",
                "clip_duration_ms": 5000,
                "summary": "人在卧室整理行李。",
                "frames": [
                    {
                        "frame_index": 0,
                        "timestamp_ms": 0,
                        "timestamp_label": "00:00",
                        "image_base64": "QUFBQUFBQUFBQUFBQUFBQQ==",
                    },
                    {
                        "frame_index": 1,
                        "timestamp_ms": 2000,
                        "timestamp_label": "00:02",
                        "image_base64": "QkJCQkJCQkJCQkJCQkJCQg==",
                    },
                ],
            },
            {
                "clip_id": "clip_002",
                "asset_id": "asset_002",
                "clip_duration_ms": 4200,
                "summary": "人在站台拖着行李前进。",
                "frames": [
                    {
                        "frame_index": 0,
                        "timestamp_ms": 300,
                        "timestamp_label": "00:00",
                        "image_base64": "Q0NDQ0NDQ0NDQ0NDQ0NDQw==",
                    }
                ],
            },
            {
                "clip_id": "clip_003",
                "asset_id": "asset_003",
                "clip_duration_ms": 4800,
                "summary": "旅途中窗外移动风景。",
                "frames": [
                    {
                        "frame_index": 0,
                        "timestamp_ms": 1000,
                        "timestamp_label": "00:01",
                        "image_base64": "RERERERERERERERERERERA==",
                    }
                ],
            },
        ],
    }


def test_inspect_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.post("/v1/tools/inspect", json=_make_request_payload())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_inspect_rejects_invalid_request(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    payload = _make_request_payload()
    del payload["question"]

    response = client.post(
        "/v1/tools/inspect",
        headers={"Authorization": f"Bearer {bundle['access_token']}"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INSPECT_REQUEST"


def test_inspect_rejects_missing_evidence(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    payload = _make_request_payload()
    payload["candidates"][0]["frames"] = []

    response = client.post(
        "/v1/tools/inspect",
        headers={"Authorization": f"Bearer {bundle['access_token']}"},
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSPECT_EVIDENCE_MISSING"


def test_inspect_reports_provider_unavailable(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    monkeypatch.setattr(settings, "google_api_key", None)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/tools/inspect",
        headers={"Authorization": f"Bearer {bundle['access_token']}"},
        json=_make_request_payload(),
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INSPECT_PROVIDER_UNAVAILABLE"


def test_inspect_rejects_invalid_provider_response(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        return _DummyResponse(
            status_code=200,
            body={
                "choices": [
                    {
                        "message": {
                            "content": "not a json object",
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/tools/inspect",
        headers={"Authorization": f"Bearer {bundle['access_token']}"},
        json=_make_request_payload(),
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INSPECT_PROVIDER_INVALID_RESPONSE"


def test_inspect_successfully_normalizes_selected_clip_from_ranking(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert json["model"] == "gemini-2.5-flash"
        assert json["messages"][1]["content"][0]["type"] == "text"
        return _DummyResponse(
            status_code=200,
            body={
                "choices": [
                    {
                        "message": {
                            "content": """
```json
{
  "question_type": "choose",
  "ranking": ["clip_002", "clip_001", "clip_003"],
  "candidate_judgments": [
    {"clip_id": "clip_001", "verdict": "partial_match", "confidence": 0.61, "short_reason": "有出发前准备感，但场景更静。"},
    {"clip_id": "clip_002", "verdict": "match", "confidence": 0.88, "short_reason": "站台与行李共同强化出发感。"},
    {"clip_id": "clip_003", "verdict": "mismatch", "confidence": 0.52, "short_reason": "更像旅途中的过渡镜头。"}
  ]
}
```""",
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/tools/inspect",
        headers={"Authorization": f"Bearer {bundle['access_token']}"},
        json=_make_request_payload(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["question_type"] == "choose"
    assert body["selected_clip_id"] == "clip_002"
    assert body["ranking"] == ["clip_002", "clip_001", "clip_003"]
    assert body["candidate_judgments"][1]["clip_id"] == "clip_002"
