#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.auth_service import TokenService, UserService  # noqa: E402
from app.auth_store import AuthStore  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.errors import ServerApiError  # noqa: E402


class RegressionFailure(RuntimeError):
    pass


@dataclass
class SeededLoginSession:
    login_session_id: str
    user_id: str
    access_token: str
    refresh_token: str


def _pretty_json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True)


def _print_step(message: str) -> None:
    print(f"[e2e-auth] {message}")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise RegressionFailure(message)


def _request(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    expected_status: int | None = None,
    json_body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    response = client.request(method, url, json=json_body, headers=headers)
    if expected_status is not None and response.status_code != expected_status:
        raise RegressionFailure(
            f"{method} {url} expected {expected_status}, got {response.status_code}: {response.text[:800]}"
        )
    return response


def _seed_authenticated_login_session(login_session_id: str) -> SeededLoginSession:
    settings = get_settings()
    store = AuthStore(settings)
    store.ensure_indexes()
    user_service = UserService(store)
    token_service = TokenService(settings, store)

    login_session = store.login_sessions.get(login_session_id)
    if login_session is None:
        raise RegressionFailure(f"login_session not found while seeding: {login_session_id}")

    unique_suffix = uuid4().hex[:12]
    profile = {
        "provider_user_id": f"google_e2e_{unique_suffix}",
        "email": f"e2e-auth-{unique_suffix}@entrocut.local",
        "display_name": f"E2E Auth {unique_suffix[:6]}",
        "avatar_url": None,
    }
    try:
        user = user_service.upsert_user_from_provider("google", profile)
    except ServerApiError as exc:
        raise RegressionFailure(f"failed to seed user: {exc.code} {exc.message}") from exc

    bundle = token_service.issue_session_bundle(user)
    login_session["status"] = "authenticated"
    login_session["result"] = {
        "access_token": bundle["access_token"],
        "refresh_token": bundle["refresh_token"],
        "expires_in": bundle["expires_in"],
        "token_type": bundle["token_type"],
        "user": user_service.user_profile(user),
    }
    login_session["error"] = None
    store.login_sessions.save(login_session)
    return SeededLoginSession(
        login_session_id=login_session_id,
        user_id=user["_id"],
        access_token=bundle["access_token"],
        refresh_token=bundle["refresh_token"],
    )


def _poll_workspace_for_assistant_turn(
    client: httpx.Client,
    core_base_url: str,
    project_id: str,
    expected_user_prompt: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_body: dict[str, Any] | None = None
    while time.time() < deadline:
        response = _request(client, "GET", f"{core_base_url}/api/v1/projects/{project_id}", expected_status=200)
        last_body = response.json()
        workspace = last_body.get("workspace") or {}
        chat_turns = workspace.get("chat_turns") or []
        if any(turn.get("role") == "assistant" for turn in chat_turns):
            if any(turn.get("role") == "user" and turn.get("content") == expected_user_prompt for turn in chat_turns):
                return last_body
        time.sleep(0.5)
    raise RegressionFailure(
        "timed out waiting for assistant turn after core chat. "
        f"Last workspace snapshot: {_pretty_json(last_body) if last_body is not None else 'null'}"
    )


def run_regression(
    server_base_url: str,
    core_base_url: str,
    timeout_seconds: float,
    bootstrap_secret: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "server_base_url": server_base_url,
        "core_base_url": core_base_url,
    }
    with httpx.Client(timeout=20.0, follow_redirects=False) as client:
        _print_step("检查 health endpoint")
        server_health = _request(client, "GET", f"{server_base_url}/health", expected_status=200).json()
        core_health = _request(client, "GET", f"{core_base_url}/health", expected_status=200).json()
        _assert(server_health.get("service") == "server", "server /health did not return service=server")
        _assert(core_health.get("service") == "core", "core /health did not return service=core")
        summary["server_health"] = server_health
        summary["core_health"] = core_health

        _print_step("创建 login_session")
        create_login_session_response = _request(
            client,
            "POST",
            f"{server_base_url}/api/v1/auth/login-sessions",
            expected_status=200,
            json_body={
                "provider": "google",
                "client_redirect_uri": "http://127.0.0.1:5173/",
            },
        ).json()
        login_session_id = create_login_session_response["login_session_id"]
        summary["login_session_id"] = login_session_id

        _print_step("注入已完成 OAuth 的 login_session 结果")
        claim_response: dict[str, Any] | None = None
        if bootstrap_secret:
            bootstrap_response = _request(
                client,
                "POST",
                f"{server_base_url}/api/v1/test/bootstrap/login-session",
                expected_status=200,
                headers={"X-Bootstrap-Secret": bootstrap_secret},
                json_body={
                    "login_session_id": login_session_id,
                    "provider": "google",
                },
            ).json()
            claim_response = _request(
                client,
                "GET",
                f"{server_base_url}/api/v1/auth/login-sessions/{login_session_id}",
                expected_status=200,
            ).json()
            claim_result = claim_response.get("result")
            _assert(isinstance(claim_result, dict), "bootstrap login_session did not return token bundle")
            seeded = SeededLoginSession(
                login_session_id=login_session_id,
                user_id=bootstrap_response["user"]["id"],
                access_token=claim_result["access_token"],
                refresh_token=claim_result["refresh_token"],
            )
            summary["bootstrap_mode"] = "staging_api"
            summary["bootstrap_user"] = bootstrap_response["user"]
        else:
            seeded = _seed_authenticated_login_session(login_session_id)

        _print_step("首次 claim login_session")
        if claim_response is None:
            claim_response = _request(
                client,
                "GET",
                f"{server_base_url}/api/v1/auth/login-sessions/{login_session_id}",
                expected_status=200,
            ).json()
        claim_result = claim_response.get("result")
        _assert(isinstance(claim_result, dict), "first login_session claim did not return token bundle")
        access_token_1 = claim_result["access_token"]
        refresh_token_1 = claim_result["refresh_token"]
        user_id = claim_result["user"]["id"]
        _assert(access_token_1 == seeded.access_token, "claimed access_token does not match seeded session")
        _assert(refresh_token_1 == seeded.refresh_token, "claimed refresh_token does not match seeded session")
        summary["first_claim"] = {
            "status": claim_response.get("status"),
            "user_id": user_id,
        }

        _print_step("验证 login_session 一次性消费")
        second_claim_response = _request(
            client,
            "GET",
            f"{server_base_url}/api/v1/auth/login-sessions/{login_session_id}",
            expected_status=200,
        ).json()
        _assert(second_claim_response.get("status") == "consumed", "second login_session claim did not return consumed")
        _assert(second_claim_response.get("result") is None, "second login_session claim still returned token result")
        summary["second_claim"] = second_claim_response

        _print_step("验证 /api/v1/me")
        me_response = _request(
            client,
            "GET",
            f"{server_base_url}/api/v1/me",
            expected_status=200,
            headers={"Authorization": f"Bearer {access_token_1}"},
        ).json()
        _assert(me_response.get("user", {}).get("id") == user_id, "/api/v1/me user.id mismatch")
        summary["me_user"] = me_response["user"]

        _print_step("同步 access token 到 core")
        set_core_auth_response = _request(
            client,
            "POST",
            f"{core_base_url}/api/v1/auth/session",
            expected_status=200,
            json_body={
                "access_token": access_token_1,
                "user_id": user_id,
            },
        ).json()
        _assert(set_core_auth_response.get("user_id") == user_id, "core auth session did not store expected user_id")

        _print_step("创建带 media 的项目")
        create_project_response = _request(
            client,
            "POST",
            f"{core_base_url}/api/v1/projects",
            expected_status=200,
            json_body={
                "title": "e2e-auth-regression",
                "prompt": "exercise auth sync",
                "media": {
                    "files": [
                        {
                            "name": "e2e-auth-regression.mp4",
                            "path": "/tmp/e2e-auth-regression.mp4",
                            "size_bytes": 1024,
                            "mime_type": "video/mp4",
                        }
                    ]
                },
            },
        ).json()
        project_id = create_project_response["project"]["id"]
        summary["project_id"] = project_id

        _print_step("第一次 core chat，验证已登录状态可透传到 server")
        first_prompt = "make a tighter opening"
        first_chat_response = _request(
            client,
            "POST",
            f"{core_base_url}/api/v1/projects/{project_id}/chat",
            expected_status=200,
            json_body={"prompt": first_prompt},
        ).json()
        _assert(first_chat_response.get("task", {}).get("type") == "chat", "first core chat did not queue chat task")
        first_workspace = _poll_workspace_for_assistant_turn(
            client,
            core_base_url,
            project_id,
            first_prompt,
            timeout_seconds,
        )
        first_chat_turns = first_workspace["workspace"]["chat_turns"]
        _assert(any(turn.get("role") == "assistant" for turn in first_chat_turns), "first core chat did not create assistant turn")
        summary["first_chat"] = {
            "task_id": first_chat_response["task"]["id"],
            "assistant_turn_count": sum(1 for turn in first_chat_turns if turn.get("role") == "assistant"),
        }

        _print_step("刷新 token")
        refresh_response = _request(
            client,
            "POST",
            f"{server_base_url}/api/v1/auth/refresh",
            expected_status=200,
            json_body={"refresh_token": refresh_token_1},
        ).json()
        access_token_2 = refresh_response["access_token"]
        refresh_token_2 = refresh_response["refresh_token"]
        _assert(access_token_2 != access_token_1, "refresh did not rotate access_token")
        _assert(refresh_token_2 != refresh_token_1, "refresh did not rotate refresh_token")
        summary["refresh"] = {
            "access_rotated": True,
            "refresh_rotated": True,
        }

        _print_step("refresh 后重新同步 access token 到 core")
        refresh_core_auth_response = _request(
            client,
            "POST",
            f"{core_base_url}/api/v1/auth/session",
            expected_status=200,
            json_body={
                "access_token": access_token_2,
            },
        ).json()
        _assert(refresh_core_auth_response.get("status") == "ok", "core auth session refresh sync failed")

        _print_step("验证旧 refresh token 已失效")
        old_refresh_response = _request(
            client,
            "POST",
            f"{server_base_url}/api/v1/auth/refresh",
            expected_status=401,
            json_body={"refresh_token": refresh_token_1},
        ).json()
        _assert(old_refresh_response.get("error", {}).get("code") == "AUTH_TOKEN_INVALID", "old refresh token was not revoked")
        summary["old_refresh_after_rotation"] = old_refresh_response

        _print_step("第二次 core chat，验证 refresh 后 core 仍可正常透传")
        second_prompt = "make the pacing faster"
        second_chat_response = _request(
            client,
            "POST",
            f"{core_base_url}/api/v1/projects/{project_id}/chat",
            expected_status=200,
            json_body={"prompt": second_prompt},
        ).json()
        second_workspace = _poll_workspace_for_assistant_turn(
            client,
            core_base_url,
            project_id,
            second_prompt,
            timeout_seconds,
        )
        second_chat_turns = second_workspace["workspace"]["chat_turns"]
        assistant_turns = [turn for turn in second_chat_turns if turn.get("role") == "assistant"]
        _assert(len(assistant_turns) >= 2, "second core chat did not create a new assistant turn")
        summary["second_chat"] = {
            "task_id": second_chat_response["task"]["id"],
            "assistant_turn_count": len(assistant_turns),
        }

        _print_step("logout")
        logout_response = _request(
            client,
            "POST",
            f"{server_base_url}/api/v1/auth/logout",
            expected_status=200,
            headers={"Authorization": f"Bearer {access_token_2}"},
        ).json()
        _assert(logout_response.get("status") == "ok", "logout did not return status=ok")

        _print_step("清空 core auth session")
        clear_core_auth_response = _request(
            client,
            "DELETE",
            f"{core_base_url}/api/v1/auth/session",
            expected_status=200,
        ).json()
        _assert(clear_core_auth_response.get("user_id") is None, "core auth clear did not return user_id=null")

        _print_step("验证 logout 后 core chat 被拒绝")
        logged_out_chat_response = _request(
            client,
            "POST",
            f"{core_base_url}/api/v1/projects/{project_id}/chat",
            expected_status=401,
            json_body={"prompt": "should fail after logout"},
        ).json()
        _assert(
            logged_out_chat_response.get("error", {}).get("code") == "AUTH_SESSION_REQUIRED",
            "core chat after logout did not return AUTH_SESSION_REQUIRED",
        )
        summary["chat_after_logout"] = logged_out_chat_response

        _print_step("验证 logout 后最后一个 refresh token 也失效")
        refresh_after_logout_response = _request(
            client,
            "POST",
            f"{server_base_url}/api/v1/auth/refresh",
            expected_status=401,
            json_body={"refresh_token": refresh_token_2},
        ).json()
        _assert(
            refresh_after_logout_response.get("error", {}).get("code") == "AUTH_TOKEN_INVALID",
            "refresh token still worked after logout",
        )
        summary["refresh_after_logout"] = refresh_after_logout_response

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the EntroCut auth -> core -> server end-to-end regression flow.",
    )
    parser.add_argument("--server-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--core-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--bootstrap-secret", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = run_regression(
            server_base_url=args.server_base_url.rstrip("/"),
            core_base_url=args.core_base_url.rstrip("/"),
            timeout_seconds=args.timeout_seconds,
            bootstrap_secret=args.bootstrap_secret,
        )
    except RegressionFailure as exc:
        print(f"[e2e-auth] FAILED: {exc}", file=sys.stderr)
        return 1
    except httpx.HTTPError as exc:
        print(f"[e2e-auth] HTTP ERROR: {exc}", file=sys.stderr)
        return 1

    print("[e2e-auth] PASS")
    print(_pretty_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
