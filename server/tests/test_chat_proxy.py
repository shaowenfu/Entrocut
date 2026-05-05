from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.auth import new_id
from app.shared.time import now_utc, to_iso
from app.main import app, rate_limit_service, settings, store, token_service


class _DummyResponse:
    def __init__(self, *, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> Any:
        return self._body


def _create_user() -> dict[str, Any]:
    current_time = now_utc()
    user = {
        "_id": new_id("user"),
        "email": f"{new_id('mail')}@entrocut.local",
        "display_name": "Chat Proxy Test",
        "avatar_url": None,
        "status": "active",
        "primary_provider": "google",
        "quota_total": 4321,
        "remaining_quota": 4321,
        "quota_status": "healthy",
        "credits_balance": 4321,
        "created_at": to_iso(current_time),
        "updated_at": to_iso(current_time),
        "last_login_at": to_iso(current_time),
    }
    store.mongo.create_user(user)
    return user


def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "deepseek_api_key", "test-deepseek-key")
    monkeypatch.setattr(settings, "google_api_key", "test-google-key")
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "quota_free_total_tokens", 4321)
    monkeypatch.setattr(settings, "quota_low_watermark_tokens", 50)
    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 20)
    monkeypatch.setattr(settings, "rate_limit_tokens_per_minute", 40000)
    rate_limit_service._memory_counters.clear()
    rate_limit_service._redis = None
    rate_limit_service._redis_ready = None


def _auth_headers(user: dict[str, Any]) -> dict[str, str]:
    bundle = token_service.issue_session_bundle(user)
    return {
        "Authorization": f"Bearer {bundle['access_token']}",
        "Content-Type": "application/json",
    }


def test_chat_completions_requires_bearer_token() -> None:
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_deepseek_chat_uses_openai_compatible_adapter(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        assert url == "https://api.deepseek.com/chat/completions"
        assert json["model"] == "deepseek-chat"
        assert "provider" not in json
        assert "custom_model" not in json
        assert headers["Authorization"] == "Bearer test-deepseek-key"
        return _DummyResponse(
            status_code=200,
            body={
                "id": "deepseek_resp_001",
                "object": "chat.completion",
                "created": 1773036475,
                "model": "deepseek-chat",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 19, "completion_tokens": 5, "total_tokens": 24},
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "stream": False,
            "messages": [{"role": "user", "content": "Make a fast travel opener."}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "deepseek-chat"
    assert body["choices"][0]["message"]["content"] == "ok"
    assert body["usage"] == {"prompt_tokens": 19, "completion_tokens": 5, "total_tokens": 24}
    assert body["entro_metadata"]["remaining_quota"] == 4297


def test_deepseek_custom_model_is_forwarded_to_upstream(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        assert json["model"] == "deepseek-chat-2026"
        return _DummyResponse(
            status_code=200,
            body={
                "choices": [{"message": {"role": "assistant", "content": "custom ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={
            "provider": "deepseek",
            "model": "deepseek-chat",
            "custom_model": "deepseek-chat-2026",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["model"] == "deepseek-chat-2026"


def test_gemini_adapter_normalizes_native_response(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=test-google-key"
        assert json["systemInstruction"]["parts"][0]["text"] == "You are concise."
        assert json["contents"][0]["role"] == "user"
        assert headers["x-goog-api-client"] == "entrocut-server/0.1"
        return _DummyResponse(
            status_code=200,
            body={
                "candidates": [
                    {"content": {"parts": [{"text": "Open with the highest-speed carve."}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 19,
                    "candidatesTokenCount": 5,
                    "totalTokenCount": 135,
                },
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={
            "provider": "google_gemini",
            "model": "gemini-2.5-flash",
            "temperature": 0.2,
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": "You are concise."},
                {"role": "user", "content": "Suggest a tighter opening."},
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "gemini-2.5-flash"
    assert body["choices"][0]["message"]["content"] == "Open with the highest-speed carve."
    assert body["usage"] == {"prompt_tokens": 19, "completion_tokens": 5, "total_tokens": 24}


def test_chat_completions_rejects_insufficient_credits(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    user["remaining_quota"] = 0
    user["quota_status"] = "exhausted"
    user["credits_balance"] = 0
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": f"Bearer {bundle['access_token']}", "Content-Type": "application/json"},
        json={"provider": "deepseek", "model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"


def test_chat_completions_rejects_rate_limited_user(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        return _DummyResponse(
            status_code=200,
            body={
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 1)
    user = _create_user()
    client = TestClient(app)
    headers = _auth_headers(user)
    payload = {"provider": "deepseek", "model": "deepseek-chat", "messages": [{"role": "user", "content": "hello"}]}
    first_response = client.post("/v1/chat/completions", headers=headers, json=payload)
    second_response = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["error"]["code"] == "RATE_LIMITED"


def test_gemini_adapter_surfaces_provider_timeout(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        raise httpx.ReadTimeout("provider timed out")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={"provider": "google_gemini", "model": "gemini-2.5-flash", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "PROVIDER_TIMEOUT"


def test_gemini_adapter_rejects_invalid_response_body(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        return _DummyResponse(status_code=200, body=["not-a-dict"])

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={"provider": "google_gemini", "model": "gemini-2.5-flash", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_PROVIDER_INVALID_RESPONSE"
