from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from helpers import (
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
from core.state import LocalStateRepository
from schemas import (
    AssistantDecisionOperationModel,
    AssistantDecisionTurnModel,
    ChatTarget,
    CoreApiError,
    CreateProjectRequest,
    EditDraftModel,
    EventEnvelope,
    ExportRequest,
    MediaReference,
    ProjectModel,
    ProjectWorkflowState,
    TaskModel,
    UserTurnModel,
    WorkspaceSnapshotModel,
)
from core.manager import WorkspaceManager


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
            self._projects[project_id] = record
            self._subscribers.setdefault(project_id, set())
            self._background_tasks.setdefault(project_id, set())

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
        return [ProjectModel.model_validate(item["project"]) for item in ordered[:limit]]

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
        if edit_draft.assets:
            workflow_state: ProjectWorkflowState = "media_ready"
        elif normalized_prompt:
            workflow_state = "awaiting_media"
        else:
            workflow_state = "prompt_input_required"

        project = ProjectModel(
            id=project_id,
            title=title,
            workflow_state=workflow_state,
            created_at=now,
            updated_at=now,
        )
        workspace_dir = str(self._workspace_manager.prepare_project_workspace(project_id))
        record = {
            "project": project.model_dump(),
            "edit_draft": edit_draft.model_dump(),
            "chat_turns": [],
            "active_task": None,
            "export_result": None,
            "sequence": 0,
            "workspace_dir": workspace_dir,
        }
        async with self._lock:
            self._projects[project_id] = record
            self._subscribers.setdefault(project_id, set())
            self._background_tasks.setdefault(project_id, set())
            self._persist_record_unlocked(project_id)
        return record

    def workspace_snapshot(self, project_id: str) -> WorkspaceSnapshotModel:
        record = self.get_project_or_raise(project_id)
        return WorkspaceSnapshotModel.model_validate(
            {
                "project": record["project"],
                "edit_draft": record["edit_draft"],
                "chat_turns": record["chat_turns"],
                "active_task": record["active_task"],
            }
        )

    async def emit(self, project_id: str, event_name: str, data: dict[str, Any]) -> None:
        async with self._lock:
            record = self.get_project_or_raise(project_id)
            record["sequence"] += 1
            if event_name == "task.updated" and isinstance(data.get("task"), dict):
                self._repository.upsert_task(project_id, data["task"])
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
        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_ingest"),
            type="ingest",
            status="queued",
            progress=0,
            message="Media ingest queued",
            created_at=now,
            updated_at=now,
        )
        record["active_task"] = task.model_dump()
        record["project"]["workflow_state"] = "media_processing"
        record["project"]["updated_at"] = now
        await self.emit(
            project_id,
            "task.updated",
            {"task": task.model_dump(), "workflow_state": "media_processing"},
        )
        background_task = asyncio.create_task(self._run_assets_import(project_id, media, task))
        self._register_background_task(project_id, background_task)
        return task

    async def _run_assets_import(self, project_id: str, media: MediaReference, task: TaskModel) -> None:
        record = self.get_project_or_raise(project_id)
        await asyncio.sleep(0.05)
        running = task.model_copy(
            update={
                "status": "running",
                "progress": 45,
                "message": "Scanning media references",
                "updated_at": _now_iso(),
            }
        )
        record["active_task"] = running.model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": running.model_dump(), "workflow_state": "media_processing"},
        )

        await asyncio.sleep(0.05)
        draft = EditDraftModel.model_validate(record["edit_draft"])
        new_assets = _build_assets(media)
        new_clips = _build_clips(new_assets)
        next_draft = _bump_draft(
            draft,
            assets=[*draft.assets, *new_assets],
            clips=[*draft.clips, *new_clips],
            status="ready" if draft.shots else "draft",
        )
        record["edit_draft"] = next_draft.model_dump()
        record["project"]["workflow_state"] = "ready" if next_draft.shots else "media_ready"
        record["project"]["updated_at"] = next_draft.updated_at
        await self.emit(project_id, "edit_draft.updated", {"edit_draft": next_draft.model_dump()})
        await self.emit(project_id, "project.updated", {"project": record["project"]})

        succeeded = running.model_copy(
            update={
                "status": "succeeded",
                "progress": 100,
                "message": "Media ingest completed",
                "updated_at": _now_iso(),
            }
        )
        record["active_task"] = None
        next_workflow_state: ProjectWorkflowState = "ready" if next_draft.shots else "media_ready"
        record["project"]["workflow_state"] = next_workflow_state
        record["project"]["updated_at"] = _now_iso()
        await self.emit(project_id, "project.updated", {"project": record["project"]})
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded.model_dump(), "workflow_state": next_workflow_state},
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
        draft = EditDraftModel.model_validate(record["edit_draft"])
        if not draft.assets:
            raise CoreApiError(
                status_code=409,
                code="MEDIA_REQUIRED_FOR_CHAT",
                message="At least one media asset is required before chat can run.",
                details={"project_id": project_id},
            )
        active_task = record["active_task"]
        if active_task and active_task.get("status") in {"queued", "running"}:
            raise CoreApiError(
                status_code=409,
                code="TASK_ALREADY_RUNNING",
                message="Another task is already running for this project.",
                details={"project_id": project_id, "active_task_id": active_task.get("id")},
            )

        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_chat"),
            type="chat",
            status="queued",
            progress=None,
            message="Chat queued",
            created_at=now,
            updated_at=now,
        )
        user_turn = UserTurnModel(id=_entity_id("turn"), role="user", content=normalized_prompt)
        record["chat_turns"].append(user_turn.model_dump())
        record["active_task"] = task.model_dump()
        record["project"]["workflow_state"] = "chat_thinking"
        record["project"]["updated_at"] = now

        await self.emit(project_id, "chat.turn.created", {"turn": user_turn.model_dump()})
        await self.emit(
            project_id,
            "task.updated",
            {"task": task.model_dump(), "workflow_state": "chat_thinking"},
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
    ) -> None:
        record = self.get_project_or_raise(project_id)
        record["edit_draft"] = next_draft.model_dump()
        record["chat_turns"].append(assistant_turn.model_dump())
        record["project"]["workflow_state"] = "ready"
        record["project"]["updated_at"] = next_draft.updated_at
        record["active_task"] = None

        await self.emit(project_id, "chat.turn.created", {"turn": assistant_turn.model_dump()})
        await self.emit(project_id, "edit_draft.updated", {"edit_draft": next_draft.model_dump()})
        await self.emit(project_id, "project.updated", {"project": record["project"]})

        succeeded = running_task.model_copy(
            update={"status": "succeeded", "message": "Chat completed", "updated_at": _now_iso()}
        )
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded.model_dump(), "workflow_state": "ready"},
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
        await asyncio.sleep(0.05)
        running = task.model_copy(
            update={"status": "running", "message": "Analyzing footage and updating edit draft", "updated_at": _now_iso()}
        )
        record["active_task"] = running.model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": running.model_dump(), "workflow_state": "chat_thinking"},
        )

        try:
            await asyncio.sleep(0.08)
            draft = EditDraftModel.model_validate(record["edit_draft"])
            auth_session = await auth_session_store.snapshot()
            access_token = auth_session.get("access_token")
            if not access_token:
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
        draft = EditDraftModel.model_validate(record["edit_draft"])
        if not draft.shots:
            raise CoreApiError(
                status_code=409,
                code="EDIT_DRAFT_REQUIRED",
                message="Edit draft with at least one shot is required before export can run.",
                details={"project_id": project_id},
            )
        active_task = record["active_task"]
        if active_task and active_task.get("status") in {"queued", "running"}:
            raise CoreApiError(
                status_code=409,
                code="TASK_ALREADY_RUNNING",
                message="Another task is already running for this project.",
                details={"project_id": project_id, "active_task_id": active_task.get("id")},
            )

        now = _now_iso()
        task = TaskModel(
            id=_entity_id("task_render"),
            type="render",
            status="queued",
            progress=0,
            message="Export queued",
            created_at=now,
            updated_at=now,
        )
        record["active_task"] = task.model_dump()
        record["project"]["workflow_state"] = "rendering"
        record["project"]["updated_at"] = now
        record["edit_draft"] = _bump_draft(draft, status="rendering", updated_at=now).model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": task.model_dump(), "workflow_state": "rendering"},
        )
        background_task = asyncio.create_task(self._run_export(project_id, payload, task))
        self._register_background_task(project_id, background_task)
        return task

    async def _run_export(self, project_id: str, payload: ExportRequest, task: TaskModel) -> None:
        record = self.get_project_or_raise(project_id)
        await asyncio.sleep(0.05)
        running = task.model_copy(
            update={"status": "running", "progress": 50, "message": "Rendering draft export", "updated_at": _now_iso()}
        )
        record["active_task"] = running.model_dump()
        await self.emit(
            project_id,
            "task.updated",
            {"task": running.model_dump(), "workflow_state": "rendering"},
        )

        await asyncio.sleep(0.08)
        export_path = self._workspace_manager.export_output_path(project_id, payload.format or "mp4")
        export_path.parent.mkdir(parents=True, exist_ok=True)
        export_path.write_text("placeholder export artifact\n", encoding="utf-8")
        result = {
            "render_type": "export",
            "output_url": export_path.resolve().as_uri(),
            "duration_ms": 4800,
            "file_size_bytes": 18_000_000,
            "thumbnail_url": None,
            "format": payload.format or "mp4",
            "quality": payload.quality,
            "resolution": "1920x1080",
        }
        draft = EditDraftModel.model_validate(record["edit_draft"])
        ready_draft = _bump_draft(draft, status="ready")
        record["export_result"] = result
        record["edit_draft"] = ready_draft.model_dump()
        record["active_task"] = None
        record["project"]["workflow_state"] = "ready"
        record["project"]["updated_at"] = ready_draft.updated_at

        await self.emit(project_id, "edit_draft.updated", {"edit_draft": ready_draft.model_dump()})
        await self.emit(project_id, "export.completed", {"result": result})
        await self.emit(project_id, "project.updated", {"project": record["project"]})
        succeeded = running.model_copy(
            update={"status": "succeeded", "progress": 100, "message": "Export completed", "updated_at": _now_iso()}
        )
        await self.emit(
            project_id,
            "task.updated",
            {"task": succeeded.model_dump(), "workflow_state": "ready"},
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
    draft = EditDraftModel.model_validate(record["edit_draft"])
    workflow_state: ProjectWorkflowState = "ready" if draft.shots else "media_ready"
    failed_task = task.model_copy(
        update={
            "status": "failed",
            "message": message,
            "updated_at": _now_iso(),
        }
    )
    record["active_task"] = None
    record["project"]["workflow_state"] = workflow_state
    record["project"]["updated_at"] = _now_iso()
    await store.emit(
        project_id,
        "error.occurred",
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
            "workflow_state": workflow_state,
        },
    )
    await store.emit(project_id, "project.updated", {"project": record["project"]})
    await store.emit(
        project_id,
        "task.updated",
        {"task": failed_task.model_dump(), "workflow_state": workflow_state},
    )


store = InMemoryProjectStore()
auth_session_store = CoreAuthSessionStore(app_data_root=store.app_data_root)
