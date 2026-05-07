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


class _DummyUsage:
    def __init__(self, *, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        self.prompt_token_count = prompt_tokens
        self.candidates_token_count = completion_tokens
        self.total_token_count = total_tokens


class _DummyGeminiResponse:
    def __init__(self, *, text: str, usage: _DummyUsage | None = None) -> None:
        self.text = text
        self.usage_metadata = usage


def _install_fake_gemini_sdk(monkeypatch, *, response: _DummyGeminiResponse | None = None, error: Exception | None = None) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    class _Part:
        @staticmethod
        def from_text(*, text: str) -> dict[str, str]:
            return {"text": text}

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
            return response or _DummyGeminiResponse(
                text="ok",
                usage=_DummyUsage(prompt_tokens=2, completion_tokens=1, total_tokens=3),
            )

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

    monkeypatch.setattr("app.services.models.adapters.gemini._load_genai_modules", lambda: (_Genai, _Types))
    return calls


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
            "model": "deepseek-v4-flash",
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_admin_access_token_uses_persisted_admin_user(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        return _DummyResponse(
            status_code=200,
            body={
                "id": "admin_resp_001",
                "object": "chat.completion",
                "created": 1773036475,
                "model": "deepseek-v4-flash",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    monkeypatch.setattr(settings, "admin_access_token", "test-admin-token")
    current_time = now_utc()
    store.mongo.create_user(
        {
            "_id": "admin",
            "email": "admin@entrocut.local",
            "display_name": "Admin",
            "avatar_url": None,
            "status": "active",
            "primary_provider": "admin",
            "quota_total": 4321,
            "remaining_quota": 4321,
            "quota_status": "healthy",
            "credits_balance": 4321,
            "created_at": to_iso(current_time),
            "updated_at": to_iso(current_time),
            "last_login_at": to_iso(current_time),
        }
    )
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers={"Authorization": "Bearer test-admin-token", "Content-Type": "application/json"},
        json={
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["choices"][0]["message"]["content"] == "ok"
    assert body["entro_metadata"]["remaining_quota"] == 4318


def test_deepseek_chat_uses_openai_compatible_adapter(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        assert url == "https://api.deepseek.com/chat/completions"
        assert json["model"] == "deepseek-v4-flash"
        assert "provider" not in json
        assert "custom_model" not in json
        assert "stream_options" not in json
        assert headers["Authorization"] == "Bearer test-deepseek-key"
        return _DummyResponse(
            status_code=200,
            body={
                "id": "deepseek_resp_001",
                "object": "chat.completion",
                "created": 1773036475,
                "model": "deepseek-v4-flash",
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
            "model": "deepseek-v4-flash",
            "stream": False,
            "messages": [{"role": "user", "content": "Make a fast travel opener."}],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "deepseek-v4-flash"
    assert body["choices"][0]["message"]["content"] == "ok"
    assert body["usage"] == {"prompt_tokens": 19, "completion_tokens": 5, "total_tokens": 24}
    assert body["entro_metadata"]["remaining_quota"] == 4297


def test_deepseek_custom_model_is_forwarded_to_upstream(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        assert json["model"] == "deepseek-v4-flash-2026"
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
            "model": "deepseek-v4-flash",
            "custom_model": "deepseek-v4-flash-2026",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["model"] == "deepseek-v4-flash-2026"


def test_gemini_adapter_normalizes_native_response(monkeypatch) -> None:
    calls = _install_fake_gemini_sdk(
        monkeypatch,
        response=_DummyGeminiResponse(
            text="Open with the highest-speed carve.",
            usage=_DummyUsage(prompt_tokens=19, completion_tokens=5, total_tokens=24),
        ),
    )
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={
            "provider": "google_gemini",
            "model": "gemini-3.1-flash-lite-preview",
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
    assert calls[0]["model"] == "gemini-3.1-flash-lite-preview"
    assert calls[0]["contents"][0].role == "user"
    assert calls[0]["config"].kwargs["system_instruction"] == "You are concise."
    assert body["model"] == "gemini-3.1-flash-lite-preview"
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
        json={"provider": "deepseek", "model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hello"}]},
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
    payload = {"provider": "deepseek", "model": "deepseek-v4-flash", "messages": [{"role": "user", "content": "hello"}]}
    first_response = client.post("/v1/chat/completions", headers=headers, json=payload)
    second_response = client.post("/v1/chat/completions", headers=headers, json=payload)
    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["error"]["code"] == "RATE_LIMITED"


def test_gemini_adapter_surfaces_provider_timeout(monkeypatch) -> None:
    _install_fake_gemini_sdk(monkeypatch, error=TimeoutError("provider timed out"))
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={"provider": "google_gemini", "model": "gemini-3.1-flash-lite-preview", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 504
    assert response.json()["error"]["code"] == "PROVIDER_TIMEOUT"


def test_gemini_adapter_surfaces_sdk_error(monkeypatch) -> None:
    _install_fake_gemini_sdk(monkeypatch, error=RuntimeError("provider failed"))
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    client = TestClient(app)
    response = client.post(
        "/v1/chat/completions",
        headers=_auth_headers(user),
        json={"provider": "google_gemini", "model": "gemini-3.1-flash-lite-preview", "messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_PROVIDER_UNAVAILABLE"
