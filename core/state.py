from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from core.storage import ensure_app_data_layout, resolve_app_data_root, sqlite_db_path


class LocalStateRepository:
    def __init__(self, app_data_root: str | Path | None = None) -> None:
        self.app_data_root = resolve_app_data_root(app_data_root)
        ensure_app_data_layout(self.app_data_root)
        self.db_path = sqlite_db_path(self.app_data_root)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    workflow_state TEXT NOT NULL,
                    lifecycle_state TEXT NOT NULL DEFAULT 'active',
                    workspace_dir TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS edit_drafts (
                    project_id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    draft_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_turns (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    turn_type TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    slot TEXT NOT NULL DEFAULT 'agent',
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    owner_type TEXT DEFAULT 'project',
                    owner_id TEXT,
                    progress INTEGER,
                    message TEXT,
                    result_json TEXT,
                    error_json TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS project_runtime (
                    project_id TEXT PRIMARY KEY,
                    active_task_id TEXT,
                    runtime_state_json TEXT,
                    summary_state TEXT,
                    export_result_json TEXT,
                    sequence INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    source_path TEXT,
                    file_name TEXT NOT NULL,
                    size_bytes INTEGER,
                    modified_at TEXT,
                    content_hash TEXT,
                    processing_stage TEXT NOT NULL DEFAULT 'pending',
                    processing_progress INTEGER,
                    clip_count INTEGER NOT NULL DEFAULT 0,
                    indexed_clip_count INTEGER NOT NULL DEFAULT 0,
                    last_error_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS core_auth_session (
                    session_key TEXT PRIMARY KEY,
                    access_token TEXT,
                    user_id TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._ensure_schema_extensions(connection)
            self._migrate_legacy_snapshot_records(connection)
            connection.commit()

    def load_records(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.id AS project_id,
                    p.title,
                    p.lifecycle_state,
                    p.workspace_dir,
                    p.created_at AS project_created_at,
                    p.updated_at AS project_updated_at,
                    d.draft_json,
                    r.active_task_id,
                    r.runtime_state_json,
                    r.summary_state,
                    r.export_result_json,
                    r.sequence
                FROM projects p
                JOIN edit_drafts d ON d.project_id = p.id
                LEFT JOIN project_runtime r ON r.project_id = p.id
                ORDER BY p.updated_at DESC
                """
            ).fetchall()
            task_rows = connection.execute(
                """
                SELECT
                    project_id,
                    id,
                    slot,
                    type,
                    status,
                    owner_type,
                    owner_id,
                    progress,
                    message,
                    result_json,
                    error_json,
                    payload_json,
                    created_at,
                    updated_at
                FROM tasks
                """
            ).fetchall()
            turn_rows = connection.execute(
                "SELECT project_id, payload_json FROM chat_turns ORDER BY created_at ASC, rowid ASC"
            ).fetchall()
            asset_rows = connection.execute(
                """
                SELECT
                    project_id,
                    id,
                    source_path,
                    file_name,
                    processing_stage,
                    processing_progress,
                    clip_count,
                    indexed_clip_count,
                    last_error_json,
                    updated_at
                FROM assets
                ORDER BY created_at ASC, rowid ASC
                """
            ).fetchall()

        tasks_by_project: dict[str, dict[str, dict[str, Any]]] = {}
        task_list_by_project: dict[str, list[dict[str, Any]]] = {}
        for row in task_rows:
            normalized_task = self._normalize_task_row(row)
            project_id = str(row["project_id"])
            tasks_by_project.setdefault(project_id, {})[normalized_task["id"]] = normalized_task
            task_list_by_project.setdefault(project_id, []).append(normalized_task)

        turns_by_project: dict[str, list[dict[str, Any]]] = {}
        for row in turn_rows:
            turns_by_project.setdefault(row["project_id"], []).append(json.loads(row["payload_json"]))

        assets_by_project: dict[str, dict[str, dict[str, Any]]] = {}
        for row in asset_rows:
            project_id = str(row["project_id"])
            assets_by_project.setdefault(project_id, {})[str(row["id"])] = self._normalize_asset_row(row)

        records: list[dict[str, Any]] = []
        for row in rows:
            project_id = str(row["project_id"])
            active_task_id = row["active_task_id"]
            active_task = None
            if active_task_id:
                active_task = tasks_by_project.get(project_id, {}).get(str(active_task_id))
            active_tasks = [
                task
                for task in task_list_by_project.get(project_id, [])
                if task.get("status") in {"queued", "running"}
            ]
            runtime_state = self._normalize_runtime_state(row["runtime_state_json"])
            draft = json.loads(row["draft_json"])
            draft = self._merge_asset_rows_into_draft(draft, assets_by_project.get(project_id, {}))
            records.append(
                {
                    "project": {
                        "id": project_id,
                        "title": row["title"],
                        "lifecycle_state": row["lifecycle_state"] or "active",
                        "created_at": row["project_created_at"],
                        "updated_at": row["project_updated_at"],
                    },
                    "edit_draft": draft,
                    "chat_turns": turns_by_project.get(project_id, []),
                    "active_task": active_task,
                    "active_tasks": active_tasks,
                    "runtime_state": runtime_state,
                    "summary_state": row["summary_state"],
                    "export_result": json.loads(row["export_result_json"]) if row["export_result_json"] else None,
                    "sequence": int(row["sequence"] or 0),
                    "workspace_dir": row["workspace_dir"],
                }
            )
        return records

    def upsert_record(self, record: dict[str, Any]) -> None:
        with self._connect() as connection:
            self._upsert_record(connection, record)
            connection.commit()

    def clear_all(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM assets")
            connection.execute("DELETE FROM project_runtime")
            connection.execute("DELETE FROM tasks")
            connection.execute("DELETE FROM chat_turns")
            connection.execute("DELETE FROM edit_drafts")
            connection.execute("DELETE FROM core_auth_session")
            connection.execute("DELETE FROM projects")
            connection.commit()

    def upsert_task(self, project_id: str, task: dict[str, Any]) -> None:
        with self._connect() as connection:
            self._upsert_task(connection, project_id, task)
            connection.commit()

    def load_auth_session(self) -> dict[str, str | None]:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT access_token, user_id
                FROM core_auth_session
                WHERE session_key = 'default'
                """
            ).fetchone()
        if row is None:
            return {"access_token": None, "user_id": None}
        return {
            "access_token": row["access_token"],
            "user_id": row["user_id"],
        }

    def upsert_auth_session(self, access_token: str | None, user_id: str | None, updated_at: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO core_auth_session (session_key, access_token, user_id, updated_at)
                VALUES ('default', ?, ?, ?)
                ON CONFLICT(session_key) DO UPDATE SET
                    access_token = excluded.access_token,
                    user_id = excluded.user_id,
                    updated_at = excluded.updated_at
                """,
                (access_token, user_id, updated_at),
            )
            connection.commit()

    def clear_auth_session(self, updated_at: str) -> None:
        self.upsert_auth_session(None, None, updated_at)

    def _upsert_record(self, connection: sqlite3.Connection, record: dict[str, Any]) -> None:
        project = record["project"]
        project_id = str(project["id"])
        workspace_dir = str(record.get("workspace_dir") or "")
        legacy_workflow_state = self._legacy_workflow_state(record)
        connection.execute(
            """
            INSERT INTO projects (id, title, workflow_state, lifecycle_state, workspace_dir, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                workflow_state = excluded.workflow_state,
                lifecycle_state = excluded.lifecycle_state,
                workspace_dir = excluded.workspace_dir,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                project["title"],
                legacy_workflow_state,
                project.get("lifecycle_state", "active"),
                workspace_dir,
                project["created_at"],
                project["updated_at"],
            ),
        )

        draft = record["edit_draft"]
        connection.execute(
            """
            INSERT INTO edit_drafts (project_id, draft_id, version, status, draft_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                draft_id = excluded.draft_id,
                version = excluded.version,
                status = excluded.status,
                draft_json = excluded.draft_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                draft["id"],
                int(draft["version"]),
                draft["status"],
                json.dumps(draft, ensure_ascii=True),
                draft["created_at"],
                draft["updated_at"],
            ),
        )

        connection.execute("DELETE FROM chat_turns WHERE project_id = ?", (project_id,))
        for index, turn in enumerate(record.get("chat_turns", []), start=1):
            connection.execute(
                """
                INSERT INTO chat_turns (id, project_id, role, turn_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    turn["id"],
                    project_id,
                    turn["role"],
                    turn.get("type"),
                    json.dumps(turn, ensure_ascii=True),
                    self._turn_created_at(turn, project["created_at"], index),
                ),
            )

        active_task = record.get("active_task")
        for task in record.get("active_tasks", []):
            self._upsert_task(connection, project_id, task)
        if active_task is not None and active_task["id"] not in {
            task["id"] for task in record.get("active_tasks", [])
        }:
            self._upsert_task(connection, project_id, active_task)

        connection.execute(
            """
            INSERT INTO project_runtime (
                project_id,
                active_task_id,
                runtime_state_json,
                summary_state,
                export_result_json,
                sequence,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                active_task_id = excluded.active_task_id,
                runtime_state_json = excluded.runtime_state_json,
                summary_state = excluded.summary_state,
                export_result_json = excluded.export_result_json,
                sequence = excluded.sequence,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                active_task["id"] if active_task else None,
                json.dumps(self._normalize_runtime_state(record.get("runtime_state")), ensure_ascii=True),
                record.get("summary_state"),
                json.dumps(record.get("export_result"), ensure_ascii=True)
                if record.get("export_result") is not None
                else None,
                int(record.get("sequence", 0)),
                project["updated_at"],
            ),
        )

        connection.execute("DELETE FROM assets WHERE project_id = ?", (project_id,))
        asset_clip_counts = self._asset_clip_counts(draft)
        for asset in draft.get("assets", []):
            clip_count = int(asset.get("clip_count", asset_clip_counts.get(asset["id"], 0)) or 0)
            processing_stage = asset.get("processing_stage") or ("ready" if clip_count > 0 else "pending")
            processing_progress = asset.get("processing_progress")
            if processing_progress is None:
                processing_progress = self._default_processing_progress(processing_stage)
            indexed_clip_count = int(
                asset.get(
                    "indexed_clip_count",
                    clip_count if processing_stage == "ready" else 0,
                )
                or 0
            )
            connection.execute(
                """
                INSERT INTO assets (
                    id,
                    project_id,
                    source_path,
                    file_name,
                    size_bytes,
                    modified_at,
                    content_hash,
                    processing_stage,
                    processing_progress,
                    clip_count,
                    indexed_clip_count,
                    last_error_json,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset["id"],
                    project_id,
                    asset.get("source_path"),
                    asset["name"],
                    None,
                    None,
                    None,
                    processing_stage,
                    processing_progress,
                    clip_count,
                    indexed_clip_count,
                    json.dumps(asset.get("last_error"), ensure_ascii=True)
                    if asset.get("last_error") is not None
                    else None,
                    draft["created_at"],
                    asset.get("updated_at") or draft["updated_at"],
                ),
            )

    def _upsert_task(self, connection: sqlite3.Connection, project_id: str, task: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO tasks (
                id,
                project_id,
                slot,
                type,
                status,
                owner_type,
                owner_id,
                progress,
                message,
                result_json,
                error_json,
                payload_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                slot = excluded.slot,
                type = excluded.type,
                status = excluded.status,
                owner_type = excluded.owner_type,
                owner_id = excluded.owner_id,
                progress = excluded.progress,
                message = excluded.message,
                result_json = excluded.result_json,
                error_json = excluded.error_json,
                payload_json = excluded.payload_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                task["id"],
                project_id,
                task.get("slot", self._default_task_slot(task.get("type"))),
                task["type"],
                task["status"],
                task.get("owner_type", "project"),
                task.get("owner_id"),
                task.get("progress"),
                task.get("message"),
                json.dumps(task.get("result"), ensure_ascii=True) if task.get("result") is not None else None,
                json.dumps(task.get("error"), ensure_ascii=True) if task.get("error") is not None else None,
                json.dumps(task, ensure_ascii=True),
                task["created_at"],
                task["updated_at"],
            ),
        )

    def _legacy_workflow_state(self, record: dict[str, Any]) -> str:
        summary_state = str(record.get("summary_state") or "")
        active_tasks = record.get("active_tasks", [])
        draft = record.get("edit_draft") or {}
        assets = draft.get("assets") or []
        shots = draft.get("shots") or []
        runtime_state = record.get("runtime_state") or {}
        execution_state = runtime_state.get("execution_state") if isinstance(runtime_state, dict) else {}

        if any(task.get("slot") == "export" and task.get("status") in {"queued", "running"} for task in active_tasks):
            return "rendering"
        if any(task.get("slot") == "agent" and task.get("status") in {"queued", "running"} for task in active_tasks):
            return "chat_thinking"
        if summary_state == "media_processing":
            return "media_processing"
        if summary_state == "attention_required" or execution_state.get("last_error"):
            return "failed"
        if summary_state == "blank":
            return "prompt_input_required"
        if summary_state == "planning":
            return "media_ready" if assets else "awaiting_media"
        if summary_state == "editing":
            return "ready" if shots else "media_ready"
        return "media_ready" if assets else "awaiting_media"

    def _turn_created_at(self, turn: dict[str, Any], fallback: str, order_index: int) -> str:
        timestamp = turn.get("created_at")
        if isinstance(timestamp, str) and timestamp.strip():
            return timestamp
        return f"{fallback}#{order_index:06d}"

    def _migrate_legacy_snapshot_records(self, connection: sqlite3.Connection) -> None:
        table_row = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'project_records'
            """
        ).fetchone()
        if table_row is None:
            return
        legacy_count = connection.execute("SELECT COUNT(*) FROM project_records").fetchone()[0]
        structured_count = connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        if legacy_count > 0 and structured_count == 0:
            rows = connection.execute("SELECT record_json FROM project_records").fetchall()
            for row in rows:
                self._upsert_record(connection, json.loads(row["record_json"]))
        connection.execute("DROP TABLE IF EXISTS project_records")
        if legacy_count == 0 or structured_count > 0:
            return

    def _ensure_schema_extensions(self, connection: sqlite3.Connection) -> None:
        self._ensure_column(connection, "projects", "lifecycle_state", "TEXT NOT NULL DEFAULT 'active'")
        self._ensure_column(connection, "project_runtime", "runtime_state_json", "TEXT")
        self._ensure_column(connection, "project_runtime", "summary_state", "TEXT")
        self._ensure_column(connection, "tasks", "slot", "TEXT NOT NULL DEFAULT 'agent'")
        self._ensure_column(connection, "tasks", "owner_type", "TEXT DEFAULT 'project'")
        self._ensure_column(connection, "tasks", "owner_id", "TEXT")
        self._ensure_column(connection, "tasks", "result_json", "TEXT")
        self._ensure_column(connection, "tasks", "error_json", "TEXT")
        self._ensure_column(connection, "assets", "processing_stage", "TEXT NOT NULL DEFAULT 'pending'")
        self._ensure_column(connection, "assets", "processing_progress", "INTEGER")
        self._ensure_column(connection, "assets", "clip_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(connection, "assets", "indexed_clip_count", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(connection, "assets", "last_error_json", "TEXT")
        self._ensure_column(connection, "assets", "updated_at", "TEXT")

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")

    def _normalize_runtime_state(self, runtime_state: Any) -> dict[str, Any]:
        default = {
            "goal_state": {
                "brief": None,
                "constraints": [],
                "preferences": [],
                "open_questions": [],
                "updated_at": None,
            },
            "focus_state": {
                "scope_type": "project",
                "scene_id": None,
                "shot_id": None,
                "updated_at": None,
            },
            "conversation_state": {
                "pending_questions": [],
                "confirmed_facts": [],
                "latest_user_feedback": "unknown",
                "updated_at": None,
            },
            "retrieval_state": {
                "last_query": None,
                "candidate_clip_ids": [],
                "retrieval_ready": False,
                "blocking_reason": None,
                "updated_at": None,
            },
            "execution_state": {
                "agent_run_state": "idle",
                "current_task_id": None,
                "last_tool_name": None,
                "last_error": None,
                "updated_at": None,
            },
            "updated_at": None,
        }
        if runtime_state is None:
            return default
        if isinstance(runtime_state, str):
            try:
                runtime_state = json.loads(runtime_state)
            except json.JSONDecodeError:
                return default
        if not isinstance(runtime_state, dict):
            return default
        normalized = dict(default)
        normalized["goal_state"] = {**default["goal_state"], **self._as_dict(runtime_state.get("goal_state"))}
        normalized["focus_state"] = {**default["focus_state"], **self._as_dict(runtime_state.get("focus_state"))}
        normalized["conversation_state"] = {
            **default["conversation_state"],
            **self._as_dict(runtime_state.get("conversation_state")),
        }
        normalized["retrieval_state"] = {
            **default["retrieval_state"],
            **self._as_dict(runtime_state.get("retrieval_state")),
        }
        normalized["execution_state"] = {
            **default["execution_state"],
            **self._as_dict(runtime_state.get("execution_state")),
        }
        normalized["updated_at"] = runtime_state.get("updated_at")
        return normalized

    def _normalize_task_row(self, row: sqlite3.Row) -> dict[str, Any]:
        payload = json.loads(row["payload_json"])
        if not isinstance(payload, dict):
            payload = {}
        normalized = dict(payload)
        normalized["id"] = str(row["id"] or normalized.get("id"))
        normalized["slot"] = row["slot"] or normalized.get("slot") or self._default_task_slot(row["type"])
        normalized["type"] = row["type"] or normalized.get("type")
        normalized["status"] = row["status"] or normalized.get("status")
        normalized["owner_type"] = row["owner_type"] or normalized.get("owner_type") or "project"
        normalized["owner_id"] = row["owner_id"] or normalized.get("owner_id")
        normalized["progress"] = row["progress"] if row["progress"] is not None else normalized.get("progress")
        normalized["message"] = row["message"] if row["message"] is not None else normalized.get("message")
        normalized["result"] = (
            json.loads(row["result_json"]) if row["result_json"] else normalized.get("result", {})
        )
        normalized["error"] = json.loads(row["error_json"]) if row["error_json"] else normalized.get("error")
        normalized["created_at"] = row["created_at"] or normalized.get("created_at")
        normalized["updated_at"] = row["updated_at"] or normalized.get("updated_at")
        return normalized

    def _normalize_asset_row(self, row: sqlite3.Row) -> dict[str, Any]:
        last_error = json.loads(row["last_error_json"]) if row["last_error_json"] else None
        processing_stage = row["processing_stage"] or "pending"
        processing_progress = row["processing_progress"]
        if processing_progress is None:
            processing_progress = self._default_processing_progress(processing_stage)
        return {
            "id": str(row["id"]),
            "source_path": row["source_path"],
            "name": row["file_name"],
            "processing_stage": processing_stage,
            "processing_progress": processing_progress,
            "clip_count": int(row["clip_count"] or 0),
            "indexed_clip_count": int(row["indexed_clip_count"] or 0),
            "last_error": last_error,
            "updated_at": row["updated_at"],
        }

    def _merge_asset_rows_into_draft(
        self,
        draft: dict[str, Any],
        asset_rows: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        if not draft.get("assets"):
            return draft
        clip_counts = self._asset_clip_counts(draft)
        merged_assets: list[dict[str, Any]] = []
        for asset in draft.get("assets", []):
            merged = dict(asset)
            row = asset_rows.get(str(asset.get("id")))
            clip_count = int(merged.get("clip_count", clip_counts.get(asset.get("id"), 0)) or 0)
            indexed_clip_count = int(merged.get("indexed_clip_count", 0) or 0)
            if row is not None:
                merged["source_path"] = row["source_path"] or merged.get("source_path")
                merged["processing_stage"] = row["processing_stage"] or merged.get("processing_stage")
                merged["processing_progress"] = row["processing_progress"]
                clip_count = max(clip_count, int(row["clip_count"] or 0))
                indexed_clip_count = max(indexed_clip_count, int(row["indexed_clip_count"] or 0))
                merged["last_error"] = row["last_error"]
                merged["updated_at"] = row["updated_at"] or merged.get("updated_at")
            if merged.get("last_error") is not None:
                merged["processing_stage"] = "failed"
            elif indexed_clip_count > 0 and indexed_clip_count >= clip_count:
                merged["processing_stage"] = "ready"
                indexed_clip_count = clip_count
            elif clip_count > 0 and merged.get("processing_stage") not in {"failed", "ready"}:
                merged["processing_stage"] = "vectorizing"
            else:
                merged["processing_stage"] = merged.get("processing_stage") or "pending"
            if merged.get("processing_progress") is None:
                merged["processing_progress"] = self._default_processing_progress(merged["processing_stage"])
            merged["clip_count"] = clip_count
            merged["indexed_clip_count"] = indexed_clip_count
            merged_assets.append(merged)
        next_draft = dict(draft)
        next_draft["assets"] = merged_assets
        return next_draft

    def _default_task_slot(self, task_type: Any) -> str:
        if task_type in {"ingest", "index"}:
            return "media"
        if task_type == "render":
            return "export"
        return "agent"

    def _default_processing_progress(self, processing_stage: str) -> int | None:
        if processing_stage == "pending":
            return 0
        if processing_stage == "segmenting":
            return 35
        if processing_stage == "vectorizing":
            return 75
        if processing_stage == "ready":
            return 100
        return None

    def _asset_clip_counts(self, draft: dict[str, Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for clip in draft.get("clips", []):
            asset_id = clip.get("asset_id")
            if not isinstance(asset_id, str) or not asset_id:
                continue
            counts[asset_id] = counts.get(asset_id, 0) + 1
        return counts

    def _as_dict(self, value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}
