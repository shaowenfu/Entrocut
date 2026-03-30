from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from fastapi.testclient import TestClient
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.auth_service import new_id
from app.auth_store import now_utc, to_iso
from app.main import app, quota_service, rate_limit_service, settings, store, token_service


class _DummyResponse:
    def __init__(self, *, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict[str, Any]:
        return self._body


class _DummyStreamResponse:
    def __init__(self, *, status_code: int, lines: list[str]) -> None:
        self.status_code = status_code
        self._lines = lines
        self._closed = False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self) -> bytes:
        return "\n".join(self._lines).encode("utf-8")

    async def aclose(self) -> None:
        self._closed = True


class _DummyStreamContext:
    def __init__(self, response: _DummyStreamResponse) -> None:
        self._response = response

    async def __aenter__(self) -> _DummyStreamResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._response.aclose()


def _create_user() -> dict[str, Any]:
    current_time = now_utc()
    user = {
        "_id": new_id("user"),
        "email": f"{new_id('mail')}@entrocut.local",
        "display_name": "Chat Proxy Test",
        "avatar_url": None,
        "status": "active",
        "primary_provider": "google",
        "credits_balance": 100_000,
        "created_at": to_iso(current_time),
        "updated_at": to_iso(current_time),
        "last_login_at": to_iso(current_time),
    }
    store.mongo.create_user(user)
    return user


def _configure_local_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_proxy_mode", "google_gemini")
    monkeypatch.setattr(settings, "google_api_key", "test-google-key")
    monkeypatch.setattr(settings, "llm_gemini_default_model", "gemini-2.5-flash")
    monkeypatch.setattr(settings, "mongodb_uri", None)
    monkeypatch.setattr(settings, "redis_url", None)
    monkeypatch.setattr(settings, "quota_free_total_tokens", 4321)
    monkeypatch.setattr(settings, "quota_low_watermark_tokens", 50)
    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 20)
    monkeypatch.setattr(settings, "rate_limit_tokens_per_minute", 40000)
    rate_limit_service._memory_counters.clear()
    rate_limit_service._redis = None
    rate_limit_service._redis_ready = None


def test_chat_completions_requires_bearer_token() -> None:
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "entro-reasoning-v1",
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_TOKEN_MISSING"


def test_google_gemini_chat_proxy_normalizes_usage_and_preserves_virtual_model(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert json["model"] == "gemini-2.5-flash"
        assert headers["Authorization"].startswith("Bearer ")
        return _DummyResponse(
            status_code=200,
            body={
                "id": "gemini_resp_001",
                "object": "chat.completion",
                "created": 1773036475,
                "model": "gemini-2.5-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Open with the highest-speed carve."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 19,
                    "completion_tokens": 5,
                    "total_tokens": 135,
                },
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)

    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {bundle['access_token']}",
            "Content-Type": "application/json",
            "X-Request-ID": "req_test_gemini_chat_001",
        },
        json={
            "model": "entro-reasoning-v1",
            "stream": False,
            "temperature": 0.2,
            "max_tokens": 120,
            "messages": [
                {"role": "system", "content": "You are a concise editing assistant."},
                {"role": "user", "content": "Suggest a tighter opening for a skiing highlight cut."},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["model"] == "entro-reasoning-v1"
    assert body["choices"][0]["message"]["content"] == "Open with the highest-speed carve."
    assert body["usage"] == {
        "prompt_tokens": 19,
        "completion_tokens": 5,
        "total_tokens": 24,
    }
    assert body["entro_metadata"]["user_id"] == user["_id"]
    assert body["entro_metadata"]["credits_balance"] == 99_999


def test_chat_completions_rejects_insufficient_credits(monkeypatch) -> None:
    _configure_local_runtime(monkeypatch)
    user = _create_user()
    user["credits_balance"] = 0
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {bundle['access_token']}",
            "Content-Type": "application/json",
            "X-Request-ID": "req_test_quota_exhausted_001",
        },
        json={
            "model": "entro-reasoning-v1",
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 402
    assert response.json()["error"]["code"] == "INSUFFICIENT_CREDITS"


def test_chat_completions_rejects_rate_limited_user(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        return _DummyResponse(
            status_code=200,
            body={
                "id": "gemini_resp_002",
                "object": "chat.completion",
                "created": 1773036476,
                "model": "gemini-2.5-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "Trim the runway and hit the jump sooner."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 4,
                    "total_tokens": 14,
                },
            },
        )

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)
    monkeypatch.setattr(settings, "rate_limit_requests_per_minute", 1)

    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)
    headers = {
        "Authorization": f"Bearer {bundle['access_token']}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "entro-reasoning-v1",
        "stream": False,
        "messages": [{"role": "user", "content": "hello"}],
    }

    first_response = client.post(
        "/v1/chat/completions",
        headers={**headers, "X-Request-ID": "req_test_rate_limit_001"},
        json=payload,
    )
    second_response = client.post(
        "/v1/chat/completions",
        headers={**headers, "X-Request-ID": "req_test_rate_limit_002"},
        json=payload,
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["error"]["code"] == "RATE_LIMITED"


def test_google_gemini_chat_proxy_streams_and_injects_final_usage(monkeypatch) -> None:
    def fake_stream(self, method: str, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyStreamContext:
        assert method == "POST"
        assert url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert json["model"] == "gemini-2.5-flash"
        assert json["stream"] is True
        assert json["stream_options"]["include_usage"] is True
        assert headers["Authorization"].startswith("Bearer ")
        response = _DummyStreamResponse(
            status_code=200,
            lines=[
                'data: {"id":"chatcmpl_stream_001","object":"chat.completion.chunk","created":1773036480,"model":"gemini-2.5-flash","choices":[{"index":0,"delta":{"role":"assistant","content":"Open with "},"finish_reason":null}]}',
                'data: {"id":"chatcmpl_stream_001","object":"chat.completion.chunk","created":1773036480,"model":"gemini-2.5-flash","choices":[{"index":0,"delta":{"content":"the jump."},"finish_reason":null}]}',
                'data: {"id":"chatcmpl_stream_001","object":"chat.completion.chunk","created":1773036480,"model":"gemini-2.5-flash","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":11,"completion_tokens":4,"total_tokens":99}}',
                "data: [DONE]",
            ],
        )
        return _DummyStreamContext(response)

    monkeypatch.setattr("httpx.AsyncClient.stream", fake_stream)
    _configure_local_runtime(monkeypatch)

    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {bundle['access_token']}",
            "Content-Type": "application/json",
            "X-Request-ID": "req_test_gemini_stream_001",
        },
        json={
            "model": "entro-reasoning-v1",
            "stream": True,
            "messages": [{"role": "user", "content": "Suggest a tighter opening for a ski clip."}],
        },
    ) as response:
        chunks = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert chunks[0].startswith("data: ")
    streamed_chunks = [json.loads(chunk[6:]) for chunk in chunks[:-1]]
    assert len(streamed_chunks) == 3
    assert all(chunk["model"] == "gemini-2.5-flash" for chunk in streamed_chunks)
    streamed_text = "".join(
        chunk["choices"][0].get("delta", {}).get("content", "")
        for chunk in streamed_chunks[:-1]
        if isinstance(chunk.get("choices"), list) and chunk["choices"]
    )
    assert streamed_text == "Open with the jump."
    final_chunk = streamed_chunks[-1]
    assert final_chunk["model"] == "gemini-2.5-flash"
    assert final_chunk["choices"][0]["finish_reason"] == "stop"
    assert final_chunk["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 4,
        "total_tokens": 99,
    }
    assert chunks[-1] == "data: [DONE]"


def test_google_gemini_chat_proxy_surfaces_provider_timeout(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        raise httpx.ReadTimeout("provider timed out")

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)

    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {bundle['access_token']}",
            "Content-Type": "application/json",
        },
        json={
            "model": "entro-reasoning-v1",
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "PROVIDER_TIMEOUT"


def test_google_gemini_chat_proxy_rejects_invalid_response_body(monkeypatch) -> None:
    async def fake_post(self, url: str, json: dict[str, Any], headers: dict[str, str]) -> _DummyResponse:
        return _DummyResponse(status_code=200, body=["not-a-dict"])  # type: ignore[list-item]

    monkeypatch.setattr("httpx.AsyncClient.post", fake_post)
    _configure_local_runtime(monkeypatch)

    user = _create_user()
    bundle = token_service.issue_session_bundle(user)
    client = TestClient(app)

    response = client.post(
        "/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {bundle['access_token']}",
            "Content-Type": "application/json",
        },
        json={
            "model": "entro-reasoning-v1",
            "stream": False,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "MODEL_PROVIDER_INVALID_RESPONSE"
