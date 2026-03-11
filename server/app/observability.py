from __future__ import annotations

import json
import logging
import sys
import time
from datetime import UTC, datetime
from threading import Lock
from typing import Any

from .config import Settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        extra_payload = getattr(record, "payload", None)
        if isinstance(extra_payload, dict):
            payload.update(extra_payload)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_logging(settings: Settings) -> None:
    root_logger = logging.getLogger()
    if getattr(root_logger, "_entrocut_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, settings.server_log_level.upper(), logging.INFO))
    root_logger._entrocut_configured = True  # type: ignore[attr-defined]


def log_event(logger: logging.Logger, message: str, **payload: Any) -> None:
    logger.info(message, extra={"payload": payload})


def log_audit_event(
    message: str,
    *,
    env: str,
    request_id: str | None,
    actor_user_id: str | None = None,
    actor_session_id: str | None = None,
    action: str,
    result: str,
    target_type: str,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    audit_logger = logging.getLogger("app.audit")
    payload: dict[str, Any] = {
        "service": "server",
        "env": env,
        "category": "audit",
        "request_id": request_id,
        "actor_user_id": actor_user_id,
        "actor_session_id": actor_session_id,
        "action": action,
        "result": result,
        "target_type": target_type,
        "target_id": target_id,
    }
    if details:
        payload["details"] = details
    log_event(audit_logger, message, **payload)


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._histograms: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}
        self._gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._lock = Lock()

    @staticmethod
    def _label_key(labels: dict[str, Any] | None = None) -> tuple[tuple[str, str], ...]:
        if not labels:
            return ()
        return tuple(sorted((str(key), str(value)) for key, value in labels.items()))

    def inc(self, name: str, value: float = 1.0, **labels: Any) -> None:
        key = (name, self._label_key(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def observe(self, name: str, value: float, **labels: Any) -> None:
        key = (name, self._label_key(labels))
        with self._lock:
            bucket = self._histograms.setdefault(key, [])
            bucket.append(float(value))

    def set_gauge(self, name: str, value: float, **labels: Any) -> None:
        key = (name, self._label_key(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (name, labels), value in sorted(self._counters.items()):
                lines.append(self._render_line(name, value, labels))
            for (name, labels), values in sorted(self._histograms.items()):
                if not values:
                    continue
                lines.append(self._render_line(f"{name}_count", len(values), labels))
                lines.append(self._render_line(f"{name}_sum", sum(values), labels))
                lines.append(self._render_line(f"{name}_avg", sum(values) / len(values), labels))
            for (name, labels), value in sorted(self._gauges.items()):
                lines.append(self._render_line(name, value, labels))
        return "\n".join(lines) + ("\n" if lines else "")

    @staticmethod
    def _render_line(name: str, value: float, labels: tuple[tuple[str, str], ...]) -> str:
        if not labels:
            return f"{name} {value}"
        rendered_labels = ",".join(f'{key}="{value}"' for key, value in labels)
        return f"{name}{{{rendered_labels}}} {value}"


def now_ms() -> float:
    return time.perf_counter() * 1000
