#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.e2e_auth_regression import RegressionFailure, run_regression  # noqa: E402


def _print_step(message: str) -> None:
    print(f"[staging-smoke] {message}")


def _require(response: httpx.Response, expected_status: int) -> dict[str, Any]:
    if response.status_code != expected_status:
        raise RegressionFailure(
            f"{response.request.method} {response.request.url} expected {expected_status}, "
            f"got {response.status_code}: {response.text[:800]}"
        )
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        return response.json()
    return {"raw": response.text}


def run_smoke(
    server_base_url: str,
    core_base_url: str,
    timeout_seconds: float,
    bootstrap_secret: str | None = None,
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "server_base_url": server_base_url,
        "core_base_url": core_base_url,
    }
    with httpx.Client(timeout=20.0) as client:
        _print_step("检查 /livez")
        summary["livez"] = _require(client.get(f"{server_base_url}/livez"), 200)

        _print_step("检查 /readyz")
        readyz = _require(client.get(f"{server_base_url}/readyz"), 200)
        if readyz.get("status") != "ready":
            raise RegressionFailure(f"/readyz is not ready: {json.dumps(readyz, ensure_ascii=True)}")
        summary["readyz"] = readyz

        _print_step("检查 /metrics")
        metrics_response = client.get(f"{server_base_url}/metrics")
        if metrics_response.status_code != 200:
            raise RegressionFailure(f"/metrics expected 200, got {metrics_response.status_code}")
        metrics_text = metrics_response.text
        required_metrics = [
            "server_http_requests_total",
            "server_dependency_health",
        ]
        for metric_name in required_metrics:
            if metric_name not in metrics_text:
                raise RegressionFailure(f"/metrics missing required metric: {metric_name}")
        summary["metrics"] = {"required_metrics": required_metrics}

    _print_step("执行鉴权与聊天主链回归")
    summary["auth_regression"] = run_regression(
        server_base_url,
        core_base_url,
        timeout_seconds,
        bootstrap_secret,
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run server staging smoke test.")
    parser.add_argument("--server-base-url", default="http://127.0.0.1:8001")
    parser.add_argument("--core-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--timeout-seconds", type=float, default=25.0)
    parser.add_argument("--bootstrap-secret", default=None)
    args = parser.parse_args()

    try:
        summary = run_smoke(
            args.server_base_url.rstrip("/"),
            args.core_base_url.rstrip("/"),
            args.timeout_seconds,
            args.bootstrap_secret,
        )
    except RegressionFailure as exc:
        print(f"[staging-smoke] FAILED: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
