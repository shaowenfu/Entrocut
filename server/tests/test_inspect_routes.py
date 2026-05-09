from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.auth import new_id
from app.shared.time import now_utc, to_iso
from app.main import app, rate_limit_service, settings, store, token_service


class _DummyGeminiResponse:
    def __init__(self, *, text: str) -> None:
        self.text = text


def _install_fake_inspect_sdk(monkeypatch, *, text: str, error: Exception | None = None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class _Part:
        @staticmethod
        def from_text(*, text: str) -> dict[str, Any]:
            return {"type": "text", "text": text}

        @staticmethod
        def from_bytes(*, data: bytes, mime_type: str) -> dict[str, Any]:
            return {"type": "bytes", "data": data, "mime_type": mime_type}

    class _Content:
        def __init__(self, *, role: str, parts: list[Any]) -> None:
            self.role = role
            self.parts = parts

    class _Config:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    class _Models:
        async def generate_content(self, **kwargs: Any) -> _DummyGeminiResponse:
            calls.append(kwargs)
            if error is not None:
                raise error
            return _DummyGeminiResponse(text=text)

    class _Aio:
        def __init__(self) -> None:
            self.models = _Models()

        async def aclose(self) -> None:
            return None

    class _Client:
        def __init__(self, *, api_key: str) -> None:
            self.api_key = api_key
            self.aio = _Aio()

    class _Genai:
        Client = _Client

    class _Types:
        Part = _Part
        Content = _Content
        GenerateContentConfig = _Config

    monkeypatch.setattr("app.services.inspect.InspectService._load_genai_modules", lambda _self: (_Genai, _Types))
    return calls


def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "google_api_key", "test-google-key")
    monkeypatch.setattr(settings, "gemini_api_key", None)
    monkeypatch.setattr(settings, "inspect_provider_mode", "google_gemini")
    monkeypatch.setattr(settings, "inspect_default_model", "gemini-3.1-flash-lite-preview")
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
        "clip_id": "clip_001",
        "prompt": "Describe the visible subjects, actions, scene, camera movement, and editing value.",
        "image_base64": "QUFBQUFBQUFBQUFBQUFBQQ==",
    }


def _auth_headers() -> dict[str, str]:
    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    return {"Authorization": f"Bearer {bundle['access_token']}"}


def test_inspect_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.post("/v1/tools/inspect", json=_make_request_payload())

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_inspect_rejects_invalid_request(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    client = TestClient(app)
    payload = _make_request_payload()
    del payload["prompt"]

    response = client.post("/v1/tools/inspect", headers=_auth_headers(), json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INSPECT_REQUEST"


def test_inspect_rejects_redundant_legacy_fields(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    client = TestClient(app)
    payload = {
        **_make_request_payload(),
        "mode": "choose",
        "candidates": [],
        "criteria": [],
    }

    response = client.post("/v1/tools/inspect", headers=_auth_headers(), json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_INSPECT_REQUEST"


def test_inspect_rejects_invalid_image_base64(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    client = TestClient(app)
    payload = _make_request_payload()
    payload["image_base64"] = "not-base64"

    response = client.post("/v1/tools/inspect", headers=_auth_headers(), json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INSPECT_EVIDENCE_MISSING"


def test_inspect_reports_provider_unavailable(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    monkeypatch.setattr(settings, "google_api_key", None)
    monkeypatch.setattr(settings, "gemini_api_key", None)
    client = TestClient(app)

    response = client.post("/v1/tools/inspect", headers=_auth_headers(), json=_make_request_payload())

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "INSPECT_PROVIDER_UNAVAILABLE"


def test_inspect_rejects_invalid_provider_response(monkeypatch) -> None:
    _install_fake_inspect_sdk(monkeypatch, text="not a json object")
    _configure_local_runtime(monkeypatch)
    client = TestClient(app)

    response = client.post("/v1/tools/inspect", headers=_auth_headers(), json=_make_request_payload())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INSPECT_PROVIDER_INVALID_RESPONSE"


def test_inspect_returns_single_clip_description(monkeypatch) -> None:
    calls = _install_fake_inspect_sdk(
        monkeypatch,
        text="""
```json
{
  "description": "A person appears to be preparing luggage in an indoor room.",
  "uncertainty": "Only stitched keyframes were provided."
}
```""",
    )
    _configure_local_runtime(monkeypatch)
    client = TestClient(app)

    response = client.post("/v1/tools/inspect", headers=_auth_headers(), json=_make_request_payload())

    assert response.status_code == 200
    assert calls[0]["model"] == "gemini-3.1-flash-lite-preview"
    assert calls[0]["contents"][0].role == "user"
    assert calls[0]["contents"][0].parts[0]["type"] == "text"
    assert calls[0]["contents"][0].parts[1]["type"] == "bytes"
    assert calls[0]["config"].kwargs["response_mime_type"] == "application/json"
    assert "Do not compare, rank, choose" in calls[0]["config"].kwargs["system_instruction"]
    body = response.json()
    assert body["clip_id"] == "clip_001"
    assert body["description"].startswith("A person appears")
    assert body["uncertainty"] == "Only stitched keyframes were provided."
    assert body["model"] == "gemini-3.1-flash-lite-preview"
