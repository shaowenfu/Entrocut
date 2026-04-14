from __future__ import annotations

import os

import uvicorn


def _read_port() -> int:
    raw = os.getenv("CORE_PORT", "8000").strip()
    try:
        port = int(raw)
    except ValueError:
        return 8000
    if port <= 0 or port > 65535:
        return 8000
    return port


def main() -> None:
    uvicorn.run("server:app", host="127.0.0.1", port=_read_port(), log_level=os.getenv("CORE_LOG_LEVEL", "info"))


if __name__ == "__main__":
    main()
