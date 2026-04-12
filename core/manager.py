from __future__ import annotations

import shutil
from pathlib import Path

try:
    from core.storage import ensure_app_data_layout, project_workspace_dir, resolve_app_data_root
except ModuleNotFoundError:
    from storage import ensure_app_data_layout, project_workspace_dir, resolve_app_data_root


class WorkspaceManager:
    def __init__(self, app_data_root: str | Path | None = None) -> None:
        self.app_data_root = resolve_app_data_root(app_data_root)
        ensure_app_data_layout(self.app_data_root)

    def prepare_project_workspace(self, project_id: str) -> Path:
        workspace_dir = project_workspace_dir(project_id, self.app_data_root)
        for relative in ("thumbs", "preview", "exports", "temp", "proxies"):
            (workspace_dir / relative).mkdir(parents=True, exist_ok=True)
        return workspace_dir

    def project_workspace_dir(self, project_id: str) -> Path:
        return project_workspace_dir(project_id, self.app_data_root)

    def project_subdir(self, project_id: str, kind: str) -> Path:
        allowed = {"thumbs", "preview", "exports", "temp", "proxies"}
        if kind not in allowed:
            raise ValueError(f"Unsupported workspace subdir: {kind}")
        workspace_dir = self.prepare_project_workspace(project_id)
        return workspace_dir / kind

    def export_output_path(self, project_id: str, format_name: str) -> Path:
        normalized_format = (format_name or "mp4").strip().lower() or "mp4"
        return self.project_subdir(project_id, "exports") / f"{project_id}_draft.{normalized_format}"

    def preview_output_path(self, project_id: str, suffix: str = "json") -> Path:
        normalized_suffix = (suffix or "json").strip().lower() or "json"
        return self.project_subdir(project_id, "preview") / f"{project_id}_preview.{normalized_suffix}"

    def clear_all_project_workspaces(self) -> None:
        projects_root = self.app_data_root / "projects"
        if projects_root.exists():
            shutil.rmtree(projects_root)
        projects_root.mkdir(parents=True, exist_ok=True)
