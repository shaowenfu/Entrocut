from __future__ import annotations

import os
import sys
from pathlib import Path


APP_DIR_NAME = "EntroCut"


def resolve_app_data_root(override: str | Path | None = None) -> Path:
    if override is not None:
        return Path(override).expanduser().resolve()

    env_root = os.getenv("ENTROCUT_APP_DATA_ROOT", "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()

    home = Path.home()
    if sys.platform == "darwin":
        return (home / "Library" / "Application Support" / APP_DIR_NAME).resolve()
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA", "").strip()
        if local_app_data:
            return (Path(local_app_data) / APP_DIR_NAME).resolve()
        return (home / "AppData" / "Local" / APP_DIR_NAME).resolve()
    return (home / ".local" / "share" / APP_DIR_NAME).resolve()


def ensure_app_data_layout(app_data_root: str | Path | None = None) -> Path:
    root = resolve_app_data_root(app_data_root)
    for relative in ("db", "projects", "logs"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    return root


def sqlite_db_path(app_data_root: str | Path | None = None) -> Path:
    root = ensure_app_data_layout(app_data_root)
    return root / "db" / "entrocut.sqlite3"


def project_workspace_dir(project_id: str, app_data_root: str | Path | None = None) -> Path:
    root = ensure_app_data_layout(app_data_root)
    return root / "projects" / project_id
