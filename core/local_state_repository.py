from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from storage_paths import ensure_app_data_layout, resolve_app_data_root, sqlite_db_path


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
                    type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    progress INTEGER,
                    message TEXT,
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
                    created_at TEXT NOT NULL,
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
            self._migrate_legacy_snapshot_records(connection)
            connection.commit()

    def load_records(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    p.id AS project_id,
                    p.title,
                    p.workflow_state,
                    p.workspace_dir,
                    p.created_at AS project_created_at,
                    p.updated_at AS project_updated_at,
                    d.draft_json,
                    r.active_task_id,
                    r.export_result_json,
                    r.sequence
                FROM projects p
                JOIN edit_drafts d ON d.project_id = p.id
                LEFT JOIN project_runtime r ON r.project_id = p.id
                ORDER BY p.updated_at DESC
                """
            ).fetchall()
            task_rows = connection.execute("SELECT project_id, payload_json FROM tasks").fetchall()
            turn_rows = connection.execute(
                "SELECT project_id, payload_json FROM chat_turns ORDER BY created_at ASC, rowid ASC"
            ).fetchall()

        tasks_by_project: dict[str, dict[str, dict[str, Any]]] = {}
        for row in task_rows:
            tasks_by_project.setdefault(row["project_id"], {})[json.loads(row["payload_json"])["id"]] = json.loads(
                row["payload_json"]
            )

        turns_by_project: dict[str, list[dict[str, Any]]] = {}
        for row in turn_rows:
            turns_by_project.setdefault(row["project_id"], []).append(json.loads(row["payload_json"]))

        records: list[dict[str, Any]] = []
        for row in rows:
            project_id = str(row["project_id"])
            active_task_id = row["active_task_id"]
            active_task = None
            if active_task_id:
                active_task = tasks_by_project.get(project_id, {}).get(str(active_task_id))
            records.append(
                {
                    "project": {
                        "id": project_id,
                        "title": row["title"],
                        "workflow_state": row["workflow_state"],
                        "created_at": row["project_created_at"],
                        "updated_at": row["project_updated_at"],
                    },
                    "edit_draft": json.loads(row["draft_json"]),
                    "chat_turns": turns_by_project.get(project_id, []),
                    "active_task": active_task,
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
        connection.execute(
            """
            INSERT INTO projects (id, title, workflow_state, workspace_dir, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                workflow_state = excluded.workflow_state,
                workspace_dir = excluded.workspace_dir,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                project["title"],
                project["workflow_state"],
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
        if active_task is not None:
            self._upsert_task(connection, project_id, active_task)

        connection.execute(
            """
            INSERT INTO project_runtime (project_id, active_task_id, export_result_json, sequence, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                active_task_id = excluded.active_task_id,
                export_result_json = excluded.export_result_json,
                sequence = excluded.sequence,
                updated_at = excluded.updated_at
            """,
            (
                project_id,
                active_task["id"] if active_task else None,
                json.dumps(record.get("export_result"), ensure_ascii=True)
                if record.get("export_result") is not None
                else None,
                int(record.get("sequence", 0)),
                project["updated_at"],
            ),
        )

        connection.execute("DELETE FROM assets WHERE project_id = ?", (project_id,))
        for asset in draft.get("assets", []):
            connection.execute(
                """
                INSERT INTO assets (id, project_id, source_path, file_name, size_bytes, modified_at, content_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset["id"],
                    project_id,
                    asset.get("source_path"),
                    asset["name"],
                    None,
                    None,
                    None,
                    draft["created_at"],
                ),
            )
    def _upsert_task(self, connection: sqlite3.Connection, project_id: str, task: dict[str, Any]) -> None:
        connection.execute(
            """
            INSERT INTO tasks (id, project_id, type, status, progress, message, payload_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                type = excluded.type,
                status = excluded.status,
                progress = excluded.progress,
                message = excluded.message,
                payload_json = excluded.payload_json,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at
            """,
            (
                task["id"],
                project_id,
                task["type"],
                task["status"],
                task.get("progress"),
                task.get("message"),
                json.dumps(task, ensure_ascii=True),
                task["created_at"],
                task["updated_at"],
            ),
        )

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
