from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from config import SERVER_BASE_URL
from helpers import (
    _asset_clip_counts,
    _build_assets,
    _build_clips,
    _build_edit_plan,
    _derive_title,
    _draft_from_payload,
    _entity_id,
    _media_file_refs,
    _now_iso,
    _trimmed,
    _bump_draft,
)
from ingestion import detect_scenes, extract_and_stitch_frames
from rendering import build_render_plan, render_export
from httpx import AsyncClient
from schemas import (
    AssistantDecisionOperationModel,
    AssistantDecisionTurnModel,
    AssetModel,
    ChatTarget,
    ClipModel,
    CoreApiError,
    CreateProjectRequest,
    EditDraftModel,
    EventEnvelope,
    ExportRequest,
    MediaReference,
    ProjectCapabilities,
    ProjectMediaSummary,
    ProjectModel,
    ProjectRuntimeState,
    TaskModel,
    UserTurnModel,
    WorkspaceSnapshotModel,
)

try:
    from core.state import LocalStateRepository
    from core.manager import WorkspaceManager
except ModuleNotFoundError:
    from state import LocalStateRepository
    from manager import WorkspaceManager


logger = logging.getLogger(__name__)


class InMemoryProjectStore:
    def __init__(self, *, app_data_root: str | Path | None = None) -> None:
        self._repository = LocalStateRepository(app_data_root=app_data_root)
        self._workspace_manager = WorkspaceManager(app_data_root=app_data_root)
        self._projects: dict[str, dict[str, Any]] = {}
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self._background_tasks: dict[str, set[asyncio.Task[Any]]] = {}
        self._lock = asyncio.Lock()
        self._load_persisted_records()

    @property
    def app_data_root(self) -> Path:
        return self._repository.app_data_root

    @property
    def db_path(self) -> Path:
        return self._repository.db_path

    def _load_persisted_records(self) -> None:
        for record in self._repository.load_records():
            project_id = str(record["project"]["id"])
            self._ensure_record_defaults(record)
            self._projects[project_id] = record
            self._subscribers.setdefault(project_id, set())
            self._background_tasks.setdefault(project_id, set())

    def _default_project_runtime_state(self, *, updated_at: str | None = None) -> dict[str, Any]:
        runtime_state = ProjectRuntimeState().model_dump()
        runtime_state["updated_at"] = updated_at
        if updated_at:
            runtime_state["goal_state"]["updated_at"] = updated_at
            runtime_state["focus_state"]["updated_at"] = updated_at
            runtime_state["conversation_state"]["updated_at"] = updated_at
            runtime_state["retrieval_state"]["updated_at"] = updated_at
            runtime_state["execution_state"]["updated_at"] = updated_at
        return runtime_state

    def _default_project_capabilities(self) -> dict[str, Any]:
        return ProjectCapabilities().model_dump()

    def _default_media_summary(self) -> dict[str, Any]:
        return ProjectMediaSummary().model_dump()

    def _default_processing_progress(self, stage: str) -> int | None:
        if stage == "pending":
            return 0
        if stage == "segmenting":
            return 35
        if stage == "vectorizing":
            return 75
        if stage == "ready":
            return 100
        return None

    def _normalize_asset_processing_state(
        self,
        asset_payload: dict[str, Any],
        *,
        clip_count: int,
        default_updated_at: str | None,
    ) -> AssetModel:
        normalized_asset = AssetModel.model_validate(asset_payload)
        normalized_clip_count = max(int(normalized_asset.clip_count or 0), clip_count)
        indexed_clip_count = min(
            normalized_clip_count,
            max(int(normalized_asset.indexed_clip_count or 0), 0),
        )
        stage = normalized_asset.processing_stage
        if normalized_asset.last_error is not None:
            stage = "failed"
        elif indexed_clip_count > 0 and indexed_clip_count >= normalized_clip_count:
            stage = "ready"
            indexed_clip_count = normalized_clip_count
        elif normalized_clip_count > 0:
            stage = "vectorizing"
        elif stage not in {"pending", "segmenting", "failed"}:
            stage = "pending"
        progress = normalized_asset.processing_progress
        if progress is None:
            progress = self._default_processing_progress(stage)
        return normalized_asset.model_copy(
            update={
                "processing_stage": stage,
                "processing_progress": progress,
                "clip_count": normalized_clip_count,
                "indexed_clip_count": indexed_clip_count,
                "updated_at": normalized_asset.updated_at or default_updated_at,
            }
        )

    def _normalize_draft_assets(self, draft_payload: dict[str, Any]) -> dict[str, Any]:
        draft = EditDraftModel.model_validate(draft_payload)
        clip_counts = _asset_clip_counts(draft.clips)
        normalized_assets = [
            self._normalize_asset_processing_state(
                asset.model_dump(),
                clip_count=clip_counts.get(asset.id, 0),
                default_updated_at=draft.updated_at,
            )
            for asset in draft.assets
        ]
        return draft.model_copy(update={"assets": normalized_assets}).model_dump()

    def _sync_runtime_retrieval_state(
        self,
        record: dict[str, Any],
        *,
        media_summary: dict[str, Any] | None = None,
        updated_at: str | None = None,
    ) -> dict[str, Any]:
        media_summary = media_summary or self._derive_media_summary(record)
        retrieval_state = record["runtime_state"]["retrieval_state"]
        retrieval_state["retrieval_ready"] = bool(media_summary["retrieval_ready"])
        if media_summary["retrieval_ready"]:
            retrieval_state["blocking_reason"] = None
        elif media_summary["asset_count"] == 0:
            retrieval_state["blocking_reason"] = "media_required_for_editing"
        else:
            retrieval_state["blocking_reason"] = "media_index_not_ready"
        if updated_at:
            retrieval_state["updated_at"] = updated_at
            record["runtime_state"]["updated_at"] = updated_at
        return media_summary

    def _select_draft_assets(self, draft: EditDraftModel, asset_ids: set[str]) -> list[dict[str, Any]]:
        return [asset.model_dump() for asset in draft.assets if asset.id in asset_ids]

    def _update_draft_assets(
        self,
        draft: EditDraftModel,
        *,
        asset_ids: set[str],
        stage: str | None = None,
        progress: int | None = None,
        clip_counts: dict[str, int] | None = None,
        indexed_clip_counts: dict[str, int] | None = None,
        last_error: dict[str, Any] | None = None,
        append_clips: list[Any] | None = None,
        updated_at: str,
        bump_version: bool,
    ) -> EditDraftModel:
        next_assets = []
        for asset in draft.assets:
            if asset.id not in asset_ids:
                next_assets.append(asset)
                continue
            asset_update: dict[str, Any] = {"updated_at": updated_at}
            if stage is not None:
                asset_update["processing_stage"] = stage
            if progress is not None or stage == "pending":
                asset_update["processing_progress"] = progress
            if clip_counts is not None:
                asset_update["clip_count"] = clip_counts.get(asset.id, asset.clip_count)
            if indexed_clip_counts is not None:
                asset_update["indexed_clip_count"] = indexed_clip_counts.get(asset.id, asset.indexed_clip_count)
            if last_error is not None:
                asset_update["last_error"] = last_error
            elif stage is not None:
                asset_update["last_error"] = None
            next_assets.append(asset.model_copy(update=asset_update))

        next_clips = draft.clips
        if append_clips:
            existing_clip_ids = {clip.id for clip in draft.clips}
            next_clips = [
                *draft.clips,
                *(clip for clip in append_clips if clip.id not in existing_clip_ids),
            ]

        next_draft = _bump_draft(
            draft,
            assets=next_assets,
            clips=next_clips,
            updated_at=updated_at,
            version=draft.version + 1 if bump_version else draft.version,
        )
        return EditDraftModel.model_validate(self._normalize_draft_assets(next_draft.model_dump()))

    async def _emit_derived_state_events(
        self,
        project_id: str,
        *,
        previous_capabilities: dict[str, Any] | None,
        previous_summary_state: str | None,
    ) -> None:
        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        capabilities = self._derive_project_capabilities(record)
        summary_state = self._derive_summary_state(record, capabilities=capabilities)
        record["summary_state"] = summary_state
        record["project"]["summary_state"] = summary_state
        if previous_capabilities != capabilities:
            await self.emit(project_id, "capabilities.updated", {"capabilities": capabilities})
        if previous_summary_state != summary_state:
            await self.emit(project_id, "project.summary.updated", {"summary_state": summary_state})

    def _ensure_record_defaults(self, record: dict[str, Any]) -> None:
        project = record.setdefault("project", {})
        project.setdefault("lifecycle_state", "active")
        record.setdefault("preview_result", None)
        record.setdefault("export_result", None)
        record["edit_draft"] = self._normalize_draft_assets(record["edit_draft"])
        record["runtime_state"] = ProjectRuntimeState.model_validate(
            record.get("runtime_state") or self._default_project_runtime_state()
        ).model_dump()
        active_tasks = record.get("active_tasks") or []
        record["active_tasks"] = [
            TaskModel.model_validate(task).model_dump()
            for task in active_tasks
            if task is not None
        ]
        active_task = record.get("active_task")
        if active_task is not None:
            normalized_active_task = TaskModel.model_validate(active_task).model_dump()
            if normalized_active_task["status"] in {"queued", "running"} and normalized_active_task["id"] not in {
                task["id"] for task in record["active_tasks"]
            }:
                record["active_tasks"].append(normalized_active_task)
            record["active_task"] = normalized_active_task
        self._sync_active_task_compat(record)
        media_summary = self._sync_runtime_retrieval_state(record)
        record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
        project["summary_state"] = record["summary_state"]

    def _task_priority(self, task: dict[str, Any]) -> tuple[int, int, str]:
        slot_priority = {"agent": 0, "preview": 1, "export": 2, "media": 3}
        status_priority = {"running": 0, "queued": 1}
        return (
            slot_priority.get(str(task.get("slot")), 9),
            status_priority.get(str(task.get("status")), 9),
            str(task.get("updated_at") or ""),
        )

    def _sync_active_task_compat(self, record: dict[str, Any]) -> None:
        active_tasks = [
            task
            for task in record.get("active_tasks", [])
            if task.get("status") in {"queued", "running"}
        ]
        active_tasks.sort(key=self._task_priority)
        record["active_tasks"] = active_tasks
        record["active_task"] = active_tasks[0] if active_tasks else None

    def _upsert_active_task(self, record: dict[str, Any], task: TaskModel | dict[str, Any]) -> dict[str, Any]:
        normalized_task = TaskModel.model_validate(task).model_dump()
        active_tasks = [item for item in record.get("active_tasks", []) if item.get("id") != normalized_task["id"]]
        if normalized_task["status"] in {"queued", "running"}:
            active_tasks.append(normalized_task)
        record["active_tasks"] = active_tasks
        self._sync_active_task_compat(record)
        return normalized_task

    def list_running_tasks(self, project_id: str, slot: str | None = None) -> list[dict[str, Any]]:
        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        tasks = [
            task
            for task in record["active_tasks"]
            if task.get("status") in {"queued", "running"}
        ]
        if slot is None:
            return tasks
        return [task for task in tasks if task.get("slot") == slot]

    def get_running_task(self, project_id: str, slot: str) -> dict[str, Any] | None:
        tasks = self.list_running_tasks(project_id, slot)
        return tasks[0] if tasks else None

    def _derive_media_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        draft = EditDraftModel.model_validate(record["edit_draft"])
        summary = self._default_media_summary()
        summary["asset_count"] = len(draft.assets)
        clip_counts = _asset_clip_counts(draft.clips)
        for asset in draft.assets:
            total_clip_count = max(int(asset.clip_count or 0), clip_counts.get(asset.id, 0))
            indexed_clip_count = min(
                total_clip_count,
                max(int(asset.indexed_clip_count or 0), 0),
            )
            summary["total_clip_count"] += total_clip_count
            summary["indexed_clip_count"] += indexed_clip_count
            if asset.processing_stage == "ready":
                summary["ready_asset_count"] += 1
            elif asset.processing_stage == "failed":
                summary["failed_asset_count"] += 1
            elif asset.processing_stage == "pending":
                summary["pending_asset_count"] += 1
            else:
                summary["processing_asset_count"] += 1
        summary["retrieval_ready"] = summary["indexed_clip_count"] > 0
        return summary

    def _derive_project_capabilities(
        self,
        record: dict[str, Any],
        *,
        media_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        draft = EditDraftModel.model_validate(record["edit_draft"])
        media_summary = media_summary or self._derive_media_summary(record)
        capabilities = self._default_project_capabilities()
        can_retrieve = bool(media_summary["retrieval_ready"])
        can_edit = can_retrieve or bool(draft.shots)
        capabilities["can_send_chat"] = True
        capabilities["chat_mode"] = "editing" if can_edit else "planning_only"
        capabilities["can_retrieve"] = can_retrieve
        capabilities["can_inspect"] = can_retrieve and bool(draft.clips)
        capabilities["can_patch_draft"] = can_edit
        capabilities["can_preview"] = bool(draft.shots)
        capabilities["can_export"] = bool(draft.shots)
        if not draft.assets:
            capabilities["blocking_reasons"].append("media_required_for_editing")
        elif not can_retrieve and not draft.shots:
            capabilities["blocking_reasons"].append("media_index_not_ready")
        if not draft.shots:
            capabilities["blocking_reasons"].append("edit_draft_shots_required")
        return capabilities

    def _derive_summary_state(
        self,
        record: dict[str, Any],
        *,
        media_summary: dict[str, Any] | None = None,
        capabilities: dict[str, Any] | None = None,
    ) -> str:
        runtime_state = record.get("runtime_state") or self._default_project_runtime_state()
        execution_state = runtime_state.get("execution_state") if isinstance(runtime_state, dict) else {}
        active_tasks = record.get("active_tasks", [])
        if any(task.get("slot") == "export" for task in active_tasks):
            return "exporting"
        media_summary = media_summary or self._derive_media_summary(record)
        if media_summary["failed_asset_count"] > 0 or execution_state.get("last_error"):
            return "attention_required"
        capabilities = capabilities or self._derive_project_capabilities(record, media_summary=media_summary)
        if any(task.get("slot") == "media" for task in active_tasks) and not capabilities["can_retrieve"]:
            return "media_processing"
        draft = EditDraftModel.model_validate(record["edit_draft"])
        goal_state = runtime_state.get("goal_state") if isinstance(runtime_state, dict) else {}
        has_goal_brief = isinstance(goal_state, dict) and bool(goal_state.get("brief"))
        if not draft.assets and not record.get("chat_turns") and not has_goal_brief:
            return "blank"
        if capabilities["chat_mode"] == "planning_only":
            return "planning"
        return "editing"

    def _persist_record_unlocked(self, project_id: str) -> None:
        record = self.get_project_or_raise(project_id)
        self._repository.upsert_record(record)

    def _register_background_task(self, project_id: str, task: asyncio.Task[Any]) -> None:
        tasks = self._background_tasks.setdefault(project_id, set())
        tasks.add(task)

        def _cleanup(done_task: asyncio.Task[Any]) -> None:
            project_tasks = self._background_tasks.get(project_id)
            if project_tasks is None:
                return
            project_tasks.discard(done_task)
            if not project_tasks:
                self._background_tasks.pop(project_id, None)

        task.add_done_callback(_cleanup)

    def pending_background_task_count(self, project_id: str) -> int:
        return len(self._background_tasks.get(project_id, set()))

    def list_projects(self, limit: int) -> list[ProjectModel]:
        ordered = sorted(self._projects.values(), key=lambda item: item["project"]["updated_at"], reverse=True)
        projects: list[ProjectModel] = []
        for item in ordered[:limit]:
            self._ensure_record_defaults(item)
            projects.append(
                ProjectModel.model_validate(
                    {
                        **item["project"],
                        "summary_state": item.get("summary_state"),
                    }
                )
            )
        return projects

    def get_project_or_raise(self, project_id: str) -> dict[str, Any]:
        project = self._projects.get(project_id)
        if project is None:
            raise CoreApiError(
                status_code=404,
                code="PROJECT_NOT_FOUND",
                message="Project not found.",
                details={"project_id": project_id},
            )
        return project

    async def create_project(self, payload: CreateProjectRequest) -> dict[str, Any]:
        normalized_prompt = _trimmed(payload.prompt)
        normalized_title = _trimmed(payload.title)
        if normalized_title is None and normalized_prompt is None and payload.media is None:
            normalized_title = "Untitled Project"

        now = _now_iso()
        project_id = _entity_id("proj")
        title = _derive_title(normalized_title, normalized_prompt, payload.media)
        edit_draft = _draft_from_payload(project_id, now, payload.media)

        project = ProjectModel(
            id=project_id,
            title=title,
            summary_state="planning" if normalized_prompt else "blank",
            lifecycle_state="active",
            created_at=now,
            updated_at=now,
        )
        runtime_state = self._default_project_runtime_state(updated_at=now)
        if normalized_prompt:
            runtime_state["goal_state"]["brief"] = normalized_prompt
            runtime_state["goal_state"]["updated_at"] = now
        workspace_dir = str(self._workspace_manager.prepare_project_workspace(project_id))
        record = {
            "project": project.model_dump(),
            "edit_draft": edit_draft.model_dump(),
            "chat_turns": [],
            "runtime_state": runtime_state,
            "active_tasks": [],
            "active_task": None,
            "summary_state": project.summary_state,
            "export_result": None,
            "preview_result": None,
            "sequence": 0,
            "workspace_dir": workspace_dir,
        }
        self._ensure_record_defaults(record)
        async with self._lock:
            self._projects[project_id] = record
            self._subscribers.setdefault(project_id, set())
            self._background_tasks.setdefault(project_id, set())
            self._persist_record_unlocked(project_id)
        return record

    def workspace_snapshot(self, project_id: str) -> WorkspaceSnapshotModel:
        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        media_summary = self._derive_media_summary(record)
        self._sync_runtime_retrieval_state(record, media_summary=media_summary)
        capabilities = self._derive_project_capabilities(record, media_summary=media_summary)
        record["summary_state"] = self._derive_summary_state(
            record,
            media_summary=media_summary,
            capabilities=capabilities,
        )
        return WorkspaceSnapshotModel.model_validate(
            {
                "project": record["project"],
                "edit_draft": record["edit_draft"],
                "chat_turns": record["chat_turns"],
                "summary_state": record["summary_state"],
                "runtime_state": record["runtime_state"],
                "media_summary": media_summary,
                "capabilities": capabilities,
                "active_tasks": record["active_tasks"],
                "active_task": record["active_task"],
                "preview_result": record.get("preview_result"),
                "export_result": record.get("export_result"),
            }
        )

    async def emit(self, project_id: str, event_name: str, data: dict[str, Any]) -> None:
        async with self._lock:
            record = self.get_project_or_raise(project_id)
            self._ensure_record_defaults(record)
            record["sequence"] += 1
            if event_name == "task.updated" and isinstance(data.get("task"), dict):
                task_payload = self._upsert_active_task(record, data["task"])
                self._repository.upsert_task(project_id, task_payload)
            if event_name == "preview.completed":
                record["preview_result"] = dict(data)
            if event_name == "export.completed" and isinstance(data.get("result"), dict):
                record["export_result"] = dict(data.get("result") or {})
            media_summary = self._sync_runtime_retrieval_state(record)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            record["project"]["summary_state"] = record["summary_state"]
            self._persist_record_unlocked(project_id)
            envelope = EventEnvelope(
                sequence=record["sequence"],
                event=event_name,
                project_id=project_id,
                emitted_at=_now_iso(),
                data=data,
            ).model_dump()
            subscribers = list(self._subscribers.get(project_id, set()))
        for queue in subscribers:
            await queue.put(envelope)

    def snapshot_event(self, project_id: str) -> dict[str, Any]:
        record = self.get_project_or_raise(project_id)
        return EventEnvelope(
            sequence=record["sequence"],
            event="workspace.snapshot",
            project_id=project_id,
            emitted_at=_now_iso(),
            data={"workspace": self.workspace_snapshot(project_id).model_dump()},
        ).model_dump()

    async def subscribe(self, project_id: str) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        async with self._lock:
            self.get_project_or_raise(project_id)
            self._subscribers.setdefault(project_id, set()).add(queue)
        return queue

    async def unsubscribe(self, project_id: str, queue: asyncio.Queue[dict[str, Any]]) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(project_id)
            if subscribers is not None:
                subscribers.discard(queue)

    def reset_for_test(self) -> None:
        self._projects.clear()
        self._subscribers.clear()
        self._background_tasks.clear()
        self._repository.clear_all()
        self._workspace_manager.clear_all_project_workspaces()

    async def queue_assets_import(self, project_id: str, media: MediaReference) -> TaskModel:
        if not _media_file_refs(media):
            raise CoreApiError(
                status_code=422,
                code="MEDIA_REFERENCE_REQUIRED",
                message="At least one media file or folder_path is required.",
            )

        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        now = _now_iso()
        previous_capabilities = self._derive_project_capabilities(record)
        previous_summary_state = record.get("summary_state")
        pending_assets = _build_assets(
            media,
            processing_stage="pending",
            processing_progress=0,
            updated_at=now,
        )
        if not pending_assets:
            raise CoreApiError(
                status_code=422,
                code="MEDIA_REFERENCE_REQUIRED",
                message="At least one media file or folder_path is required.",
            )
        draft = EditDraftModel.model_validate(record["edit_draft"])
        next_draft = EditDraftModel.model_validate(
            self._normalize_draft_assets(
                _bump_draft(
                    draft,
                    assets=[*draft.assets, *pending_assets],
                    updated_at=now,
                ).model_dump()
            )
        )
        record["edit_draft"] = next_draft.model_dump()
        asset_ids = {asset.id for asset in pending_assets}
        task = TaskModel(
            id=_entity_id("task_ingest"),
            slot="media",
            type="ingest",
            status="queued",
            owner_type="project",
            owner_id=project_id,
            progress=0,
            message="Media ingest queued",
            created_at=now,
            updated_at=now,
        )
        queued_task = self._upsert_active_task(record, task)
        record["project"]["updated_at"] = now
        media_summary = self._sync_runtime_retrieval_state(record, updated_at=now)
        record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
        await self.emit(project_id, "edit_draft.updated", {"edit_draft": next_draft.model_dump()})
        await self.emit(project_id, "asset.updated", {"assets": self._select_draft_assets(next_draft, asset_ids)})
        await self.emit(
            project_id,
            "task.updated",
            {"task": queued_task},
        )
        await self._emit_derived_state_events(
            project_id,
            previous_capabilities=previous_capabilities,
            previous_summary_state=previous_summary_state,
        )
        background_task = asyncio.create_task(self._run_assets_import(project_id, task, asset_ids))
        self._register_background_task(project_id, background_task)
        return task

    async def _run_assets_import(self, project_id: str, task: TaskModel, asset_ids: set[str]) -> None:
        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        current_task = task
        try:
            previous_capabilities = self._derive_project_capabilities(record)
            previous_summary_state = record.get("summary_state")
            segmenting_at = _now_iso()
            running = current_task.model_copy(
                update={
                    "status": "running",
                    "progress": 10,
                    "message": "Segmenting media into clips",
                    "updated_at": segmenting_at,
                }
            )
            running_task = self._upsert_active_task(record, running)
            draft = EditDraftModel.model_validate(record["edit_draft"])
            segmenting_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="segmenting",
                progress=10,
                updated_at=segmenting_at,
                bump_version=False,
            )
            record["edit_draft"] = segmenting_draft.model_dump()
            record["project"]["updated_at"] = segmenting_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=segmenting_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": segmenting_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(segmenting_draft, asset_ids)},
            )
            await self.emit(project_id, "task.updated", {"task": running_task})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )
            current_task = running

            imported_assets = [asset for asset in segmenting_draft.assets if asset.id in asset_ids]
            
            # 1. Segmenting
            new_clips = []
            for asset in imported_assets:
                video_path = asset.source_path
                if not video_path:
                    continue
                # run CPU intensive detection in thread
                scene_list = await asyncio.to_thread(detect_scenes, video_path)
                for i, (start_ms, end_ms) in enumerate(scene_list, start=1):
                    new_clips.append(
                        ClipModel(
                            id=_entity_id("clip"),
                            asset_id=asset.id,
                            source_start_ms=start_ms,
                            source_end_ms=end_ms,
                            visual_desc=f"{asset.name} candidate clip {i}",
                            semantic_tags=[],
                        )
                    )

            clip_counts = _asset_clip_counts(new_clips)

            # Update state to vectorizing
            vectorizing_at = _now_iso()
            vectorizing_task = current_task.model_copy(
                update={
                    "progress": 50,
                    "message": "Vectorizing clips for retrieval",
                    "updated_at": vectorizing_at,
                }
            )
            vectorizing_running_task = self._upsert_active_task(record, vectorizing_task)
            vectorizing_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="vectorizing",
                progress=50,
                clip_counts=clip_counts,
                indexed_clip_counts={asset_id: 0 for asset_id in asset_ids},
                append_clips=new_clips,
                updated_at=vectorizing_at,
                bump_version=True,
            )
            record["edit_draft"] = vectorizing_draft.model_dump()
            record["project"]["updated_at"] = vectorizing_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=vectorizing_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": vectorizing_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(vectorizing_draft, asset_ids)},
            )
            await self.emit(project_id, "task.updated", {"task": vectorizing_running_task})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )
            current_task = vectorizing_task

            # 2. Extract frames and send to vectorizer
            auth_session = await auth_session_store.snapshot()
            access_token = auth_session.get("access_token")
            if not access_token:
                raise RuntimeError("Access token missing, please login.")

            # Batch vectorize
            batch_size = 10
            asset_by_id = {asset.id: asset for asset in imported_assets}
            for i in range(0, len(new_clips), batch_size):
                batch = new_clips[i : i + batch_size]
                docs: list[dict[str, Any]] = []
                for clip in batch:
                    asset = asset_by_id.get(clip.asset_id)
                    if asset is None:
                        continue
                    video_path = asset.source_path
                    if not video_path:
                        continue
                    b64 = await asyncio.to_thread(
                        extract_and_stitch_frames,
                        video_path,
                        clip.source_start_ms,
                        clip.source_end_ms,
                    )
                    docs.append({
                        "id": clip.id,
                        "content": {"image_base64": b64},
                        "fields": {
                            "clip_id": clip.id,
                            "asset_id": clip.asset_id,
                            "project_id": project_id,
                            "source_start_ms": clip.source_start_ms,
                            "source_end_ms": clip.source_end_ms,
                            "frame_count": 4,
                        }
                    })

                # send request to server
                if docs:
                    endpoint_url = f"{SERVER_BASE_URL}/v1/assets/vectorize"
                    request_headers = {
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    }
                    async with AsyncClient(timeout=300) as client:
                        response = await client.post(endpoint_url, json={"docs": docs}, headers=request_headers)
                        response.raise_for_status()

                # Update progress
                progress = 50 + int(50 * (i + len(batch)) / max(1, len(new_clips)))
                current_task = current_task.model_copy(update={"progress": progress})
                self._upsert_active_task(record, current_task)
                await self.emit(project_id, "task.updated", {"task": current_task})

            # Update stage to ready
            ready_at = _now_iso()
            ready_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="ready",
                progress=100,
                clip_counts=clip_counts,
                indexed_clip_counts=clip_counts,
                updated_at=ready_at,
                bump_version=False,
            )
            record["edit_draft"] = ready_draft.model_dump()
            record["project"]["updated_at"] = ready_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=ready_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": ready_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(ready_draft, asset_ids)},
            )
            await self.emit(project_id, "project.updated", {"project": record["project"]})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )

            succeeded = current_task.model_copy(
                update={
                    "status": "succeeded",
                    "progress": 100,
                    "message": "Media ingest completed",
                    "result": {
                        "asset_ids": sorted(asset_ids),
                        "clip_count": sum(clip_counts.values()),
                    },
                    "updated_at": _now_iso(),
                }
            )
            succeeded_task = self._upsert_active_task(record, succeeded)
            await self.emit(
                project_id,
                "task.updated",
                {"task": succeeded_task},
            )
        except Exception as exc:
            logger.error("Asset import failed: %s", exc, exc_info=True)
            record = self.get_project_or_raise(project_id)
            self._ensure_record_defaults(record)
            previous_capabilities = self._derive_project_capabilities(record)
            previous_summary_state = record.get("summary_state")
            failed_at = _now_iso()
            error_body = {"code": "MEDIA_IMPORT_FAILED", "message": str(exc)}
            draft = EditDraftModel.model_validate(record["edit_draft"])
            failed_draft = self._update_draft_assets(
                draft,
                asset_ids=asset_ids,
                stage="failed",
                progress=None,
                last_error=error_body,
                updated_at=failed_at,
                bump_version=False,
            )
            record["edit_draft"] = failed_draft.model_dump()
            record["project"]["updated_at"] = failed_at
            media_summary = self._sync_runtime_retrieval_state(record, updated_at=failed_at)
            record["summary_state"] = self._derive_summary_state(record, media_summary=media_summary)
            await self.emit(project_id, "edit_draft.updated", {"edit_draft": failed_draft.model_dump()})
            await self.emit(
                project_id,
                "asset.updated",
                {"assets": self._select_draft_assets(failed_draft, asset_ids)},
            )
            await self.emit(project_id, "project.updated", {"project": record["project"]})
            await self._emit_derived_state_events(
                project_id,
                previous_capabilities=previous_capabilities,
                previous_summary_state=previous_summary_state,
            )
            failed_task = current_task.model_copy(
                update={
                    "status": "failed",
                    "message": "Media ingest failed",
                    "error": error_body,
                    "updated_at": failed_at,
                }
            )
            await self.emit(
                project_id,
                "task.updated",
                {"task": failed_task.model_dump()},
            )

    async def queue_chat(
        self,
        project_id: str,
        prompt: str,
        target: ChatTarget | None,
        model: str | None,
        routing_mode: str,
        byok_key: str | None,
        byok_base_url: str | None,
        agent_loop_max_iterations: int,
    ) -> TaskModel:
        normalized_prompt = _trimmed(prompt)
        if normalized_prompt is None:
            raise CoreApiError(
                status_code=422,
                code="CHAT_PROMPT_REQUIRED",
                message="Prompt is required.",
            )

        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        draft = EditDraftModel.model_validate(record["edit_draft"])
        active_task = self.get_running_task(project_id, "agent") or self.get_running_task(project_id, "export")
        if active_task:
            raise CoreApiError(
                status_code=409,
                code="TASK_ALREADY_RUNNING",
                message="Another task is already running for this project.",
                details={"project_id": project_id, "active_task_id": active_task.get("id")},
            )

        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_chat"),
            slot="agent",
            type="chat",
            status="queued",
            owner_type="project",
            owner_id=project_id,
            progress=None,
            message="Chat queued",
            created_at=now,
            updated_at=now,
        )
        user_turn = UserTurnModel(id=_entity_id("turn"), role="user", content=normalized_prompt)
        record["chat_turns"].append(user_turn.model_dump())
        queued_task = self._upsert_active_task(record, task)
        record["project"]["updated_at"] = now
        if not record["runtime_state"]["goal_state"].get("brief"):
            record["runtime_state"]["goal_state"]["brief"] = normalized_prompt
        record["runtime_state"]["goal_state"]["updated_at"] = now
        focus_state = record["runtime_state"]["focus_state"]
        focus_state.update(
            {
                "scope_type": "shot"
                if target and target.shot_id
                else "scene"
                if target and target.scene_id
                else "project",
                "scene_id": target.scene_id if target else draft.selected_scene_id,
                "shot_id": target.shot_id if target else draft.selected_shot_id,
                "updated_at": now,
            }
        )
        record["runtime_state"]["execution_state"].update(
            {
                "agent_run_state": "planning",
                "current_task_id": task.id,
                "last_error": None,
                "updated_at": now,
            }
        )
        record["runtime_state"]["updated_at"] = now
        record["summary_state"] = self._derive_summary_state(record)

        await self.emit(project_id, "chat.turn.created", {"turn": user_turn.model_dump()})
        await self.emit(
            project_id,
            "task.updated",
            {"task": queued_task},
        )
        background_task = asyncio.create_task(
            self._run_chat(
                project_id,
                normalized_prompt,
                target,
                task,
                model,
                routing_mode,
                byok_key,
                byok_base_url,
                agent_loop_max_iterations,
            )
        )
        self._register_background_task(project_id, background_task)
        return task

    async def _finalize_chat_success(
        self,
        *,
        project_id: str,
        running_task: TaskModel,
        assistant_turn: AssistantDecisionTurnModel,
        next_draft: EditDraftModel,
        next_runtime_state: dict[str, Any],
    ) -> None:
        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        record["edit_draft"] = next_draft.model_dump()
        record["chat_turns"].append(assistant_turn.model_dump())
        record["project"]["updated_at"] = next_draft.updated_at
        record["runtime_state"] = ProjectRuntimeState.model_validate(next_runtime_state).model_dump()
        record["runtime_state"]["execution_state"].update(
            {
                "agent_run_state": "idle",
                "current_task_id": None,
                "last_error": None,
                "updated_at": next_draft.updated_at,
            }
        )
        record["runtime_state"]["updated_at"] = next_draft.updated_at
        record["summary_state"] = self._derive_summary_state(record)

        await self.emit(project_id, "chat.turn.created", {"turn": assistant_turn.model_dump()})
        await self.emit(project_id, "edit_draft.updated", {"edit_draft": next_draft.model_dump()})
        await self.emit(project_id, "project.updated", {"project": record["project"]})

        succeeded = running_task.model_copy(
            update={"status": "succeeded", "message": "Chat completed", "updated_at": _now_iso()}
        )
        succeeded_task = self._upsert_active_task(record, succeeded)
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded_task},
        )

    async def _run_chat(
        self,
        project_id: str,
        prompt: str,
        target: ChatTarget | None,
        task: TaskModel,
        model: str | None,
        routing_mode: str,
        byok_key: str | None,
        byok_base_url: str | None,
        agent_loop_max_iterations: int,
    ) -> None:
        from agent import _run_chat_agent_loop

        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        await asyncio.sleep(0.05)
        running = task.model_copy(
            update={"status": "running", "message": "Analyzing footage and updating edit draft", "updated_at": _now_iso()}
        )
        running_task = self._upsert_active_task(record, running)
        record["runtime_state"]["execution_state"].update(
            {
                "agent_run_state": "executing_tool",
                "current_task_id": task.id,
                "updated_at": running.updated_at,
            }
        )
        record["runtime_state"]["updated_at"] = running.updated_at
        await self.emit(
            project_id,
            "task.updated",
            {"task": running_task},
        )

        try:
            await asyncio.sleep(0.08)
            draft = EditDraftModel.model_validate(record["edit_draft"])
            auth_session = await auth_session_store.snapshot()
            access_token = auth_session.get("access_token") or ""
            if routing_mode != "BYOK" and not access_token:
                raise CoreApiError(
                    status_code=401,
                    code="AUTH_SESSION_REQUIRED",
                    message="Sign in is required before chat can run.",
                )
            loop_result = await _run_chat_agent_loop(
                record=record,
                access_token=access_token,
                project_id=project_id,
                prompt=prompt,
                draft=draft,
                target=target,
                model=model,
                routing_mode=routing_mode,
                byok_key=byok_key,
                byok_base_url=byok_base_url,
                agent_loop_max_iterations=agent_loop_max_iterations,
            )
            decision = loop_result.final_decision
            next_draft = loop_result.draft
            next_runtime_state = loop_result.runtime_state.model_dump()
            if decision.draft_strategy == "placeholder_first_cut" and not next_draft.shots:
                shots, scenes = _build_edit_plan(next_draft.clips, prompt)
                next_draft = _bump_draft(
                    next_draft,
                    shots=shots,
                    scenes=scenes,
                    selected_scene_id=scenes[0].id if scenes else next_draft.selected_scene_id,
                    selected_shot_id=shots[0].id if shots else next_draft.selected_shot_id,
                    status="ready",
                )
                next_runtime_state["focus_state"].update(
                    {
                        "scope_type": "shot" if shots else next_runtime_state["focus_state"].get("scope_type", "project"),
                        "scene_id": scenes[0].id if scenes else next_runtime_state["focus_state"].get("scene_id"),
                        "shot_id": shots[0].id if shots else next_runtime_state["focus_state"].get("shot_id"),
                        "updated_at": next_draft.updated_at,
                    }
                )
                next_runtime_state["conversation_state"].update(
                    {
                        "pending_questions": [],
                        "updated_at": next_draft.updated_at,
                    }
                )
                next_runtime_state["updated_at"] = next_draft.updated_at
            reply_text = decision.assistant_reply.strip() or decision.reasoning_summary.strip()
            ops = [
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="planner_context_assembled",
                    target="core.agent.loop",
                    summary="Built planner context from workspace snapshot, chat summary, target scope, and user input.",
                ),
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="planner_decision_finalized",
                    target="server.v1.chat.completions",
                    summary=f"Planner returned a final decision with draft strategy {decision.draft_strategy}.",
                ),
                AssistantDecisionOperationModel(
                    id=_entity_id("op"),
                    action="agent_tool_execution_loop",
                    target="core.agent.tools",
                    summary=f"Executed {len(loop_result.observations)} tool step(s) in planner-driven loop.",
                ),
            ]
            if decision.draft_strategy == "placeholder_first_cut" and next_draft.shots:
                ops.append(
                    AssistantDecisionOperationModel(
                        id=_entity_id("op"),
                        action="placeholder_edit_draft_applied",
                        target="workspace.edit_draft",
                        summary="Applied placeholder first-cut strategy after loop finalized.",
                    )
                )
            else:
                ops.append(
                    AssistantDecisionOperationModel(
                        id=_entity_id("op"),
                        action="no_edit_draft_change",
                        target="workspace.edit_draft",
                        summary="Planner explicitly chose not to modify the draft in the current iteration.",
                    )
                )
            assistant_turn = AssistantDecisionTurnModel(
                id=_entity_id("turn"),
                role="assistant",
                type="decision",
                decision_type="EDIT_DRAFT_PATCH",
                reasoning_summary=reply_text,
                ops=ops,
            )
            await self._finalize_chat_success(
                project_id=project_id,
                running_task=running,
                assistant_turn=assistant_turn,
                next_draft=next_draft,
                next_runtime_state=next_runtime_state,
            )
        except CoreApiError as exc:
            await _mark_chat_failed(
                project_id=project_id,
                task=running,
                message=exc.message,
                code=exc.code,
                details=exc.details,
            )
        except Exception as exc:
            await _mark_chat_failed(
                project_id=project_id,
                task=running,
                message="Chat orchestration failed unexpectedly.",
                code="CHAT_ORCHESTRATION_FAILED",
                details={"cause": str(exc)},
            )

    async def queue_export(self, project_id: str, payload: ExportRequest) -> TaskModel:
        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        draft = EditDraftModel.model_validate(record["edit_draft"])
        if not draft.shots:
            raise CoreApiError(
                status_code=409,
                code="EDIT_DRAFT_REQUIRED",
                message="Edit draft with at least one shot is required before export can run.",
                details={"project_id": project_id},
            )
        active_task = self.get_running_task(project_id, "export") or self.get_running_task(project_id, "agent")
        if active_task:
            raise CoreApiError(
                status_code=409,
                code="TASK_ALREADY_RUNNING",
                message="Another task is already running for this project.",
                details={"project_id": project_id, "active_task_id": active_task.get("id")},
            )

        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_render"),
            slot="export",
            type="render",
            status="queued",
            owner_type="draft",
            owner_id=draft.id,
            progress=0,
            message="Export queued",
            created_at=now,
            updated_at=now,
        )
        queued_task = self._upsert_active_task(record, task)
        record["project"]["updated_at"] = now
        record["edit_draft"] = _bump_draft(draft, status="rendering", updated_at=now).model_dump()
        record["summary_state"] = self._derive_summary_state(record)
        await self.emit(
            project_id,
            "task.updated",
            {"task": queued_task},
        )
        background_task = asyncio.create_task(self._run_export(project_id, payload, task))
        self._register_background_task(project_id, background_task)
        return task

    async def _run_export(self, project_id: str, payload: ExportRequest, task: TaskModel) -> None:
        record = self.get_project_or_raise(project_id)
        self._ensure_record_defaults(record)
        await asyncio.sleep(0.05)
        running = task.model_copy(
            update={"status": "running", "progress": 50, "message": "Rendering draft export", "updated_at": _now_iso()}
        )
        running_task = self._upsert_active_task(record, running)
        await self.emit(
            project_id,
            "task.updated",
            {"task": running_task},
        )

        await asyncio.sleep(0.08)
        export_path = self._workspace_manager.export_output_path(project_id, payload.format or "mp4")
        draft = EditDraftModel.model_validate(record["edit_draft"])
        plan = build_render_plan(draft)
        render_result = await asyncio.to_thread(
            render_export,
            plan,
            export_path,
            quality=payload.quality,
        )
        result = {
            "render_type": "export",
            "output_url": render_result["output_url"],
            "duration_ms": render_result["duration_ms"],
            "file_size_bytes": render_result["file_size_bytes"],
            "thumbnail_url": None,
            "format": payload.format or "mp4",
            "quality": payload.quality,
            "resolution": "1920x1080",
        }
        ready_draft = _bump_draft(draft, status="ready")
        record["export_result"] = result
        record["edit_draft"] = ready_draft.model_dump()
        succeeded = running.model_copy(
            update={"status": "succeeded", "progress": 100, "message": "Export completed", "updated_at": _now_iso()}
        )
        succeeded_task = self._upsert_active_task(record, succeeded)
        record["project"]["updated_at"] = ready_draft.updated_at
        record["summary_state"] = self._derive_summary_state(record)

        await self.emit(project_id, "edit_draft.updated", {"edit_draft": ready_draft.model_dump()})
        await self.emit(project_id, "export.completed", {"result": result})
        await self.emit(project_id, "project.updated", {"project": record["project"]})
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded_task},
        )


class CoreAuthSessionStore:
    def __init__(self, *, app_data_root: str | Path | None = None) -> None:
        self._repository = LocalStateRepository(app_data_root=app_data_root)
        self._lock = asyncio.Lock()
        self._session: dict[str, str | None] = self._repository.load_auth_session()

    async def set_session(self, access_token: str, user_id: str | None) -> None:
        async with self._lock:
            self._session = {
                "access_token": access_token.strip(),
                "user_id": user_id.strip() if user_id and user_id.strip() else None,
            }
            self._repository.upsert_auth_session(
                self._session["access_token"],
                self._session["user_id"],
                _now_iso(),
            )

    async def clear_session(self) -> None:
        async with self._lock:
            self._session = {"access_token": None, "user_id": None}
            self._repository.clear_auth_session(_now_iso())

    async def snapshot(self) -> dict[str, str | None]:
        async with self._lock:
            return dict(self._session)

    def reset_for_test(self) -> None:
        self._session = {"access_token": None, "user_id": None}
        self._repository.clear_auth_session(_now_iso())


async def _mark_chat_failed(
    *,
    project_id: str,
    task: TaskModel,
    message: str,
    code: str,
    details: dict[str, Any] | None = None,
) -> None:
    record = store.get_project_or_raise(project_id)
    store._ensure_record_defaults(record)
    draft = EditDraftModel.model_validate(record["edit_draft"])
    failed_task = task.model_copy(
        update={
            "status": "failed",
            "message": message,
            "updated_at": _now_iso(),
        }
    )
    normalized_failed_task = store._upsert_active_task(record, failed_task)
    record["project"]["updated_at"] = _now_iso()
    record["runtime_state"]["execution_state"].update(
        {
            "agent_run_state": "failed",
            "current_task_id": None,
            "last_error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
            "updated_at": record["project"]["updated_at"],
        }
    )
    record["runtime_state"]["updated_at"] = record["project"]["updated_at"]
    record["summary_state"] = store._derive_summary_state(record)
    await store.emit(
        project_id,
        "error.occurred",
        {
            "code": code,
            "message": message,
            "details": details or {},
        },
    )
    await store.emit(project_id, "project.updated", {"project": record["project"]})
    await store.emit(
        project_id,
        "task.updated",
        {"task": normalized_failed_task},
    )


store = InMemoryProjectStore()
auth_session_store = CoreAuthSessionStore(app_data_root=store.app_data_root)
