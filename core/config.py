import os

APP_VERSION = "0.8.0-edit-draft"
REWRITE_PHASE = "clean_room_rewrite"
CORE_MODE = "local_persistence_bootstrap"
DEFAULT_SERVER_BASE_URL = "http://127.0.0.1:8001"
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", DEFAULT_SERVER_BASE_URL).rstrip("/")
SERVER_DEFAULT_PROVIDER = os.getenv("SERVER_DEFAULT_PROVIDER", "deepseek").strip() or "deepseek"
SERVER_DEFAULT_MODEL = os.getenv("SERVER_DEFAULT_MODEL", "deepseek-chat").strip() or "deepseek-chat"
SERVER_CHAT_TIMEOUT_SECONDS = float(os.getenv("SERVER_CHAT_TIMEOUT_SECONDS", "30"))
AGENT_LOOP_MAX_ITERATIONS = int(os.getenv("AGENT_LOOP_MAX_ITERATIONS", "3"))
