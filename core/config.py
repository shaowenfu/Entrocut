import os
from pathlib import Path


def _load_local_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_local_env()

APP_VERSION = "0.8.0-edit-draft"
REWRITE_PHASE = "clean_room_rewrite"
CORE_MODE = "local_persistence_bootstrap"
DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8001"
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", DEFAULT_SERVER_BASE_URL).rstrip("/")
SERVER_DEFAULT_PROVIDER = os.getenv("SERVER_DEFAULT_PROVIDER", "deepseek").strip() or "deepseek"
SERVER_DEFAULT_MODEL = os.getenv("SERVER_DEFAULT_MODEL", "deepseek-v4-flash").strip() or "deepseek-v4-flash"
SERVER_CHAT_TIMEOUT_SECONDS = float(os.getenv("SERVER_CHAT_TIMEOUT_SECONDS", "30"))
AGENT_LOOP_MAX_ITERATIONS = int(os.getenv("AGENT_LOOP_MAX_ITERATIONS", "3"))
