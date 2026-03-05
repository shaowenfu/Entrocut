from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Entrocut Core Shell",
    version="0.1.0",
    description="Local Service Shell（本地服务壳层）"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class IngestRequest(BaseModel):
    video_path: str = Field(..., description="Local video path（本地视频路径）")


class SearchRequest(BaseModel):
    query: str = Field(..., description="Semantic query（语义查询）")


class RenderRequest(BaseModel):
    project: dict[str, Any] = Field(..., description="Editable Timeline JSON（可编辑时间线）")


class ProjectMeta(BaseModel):
    id: str
    title: str
    storage_type: Literal["cloud", "local"] = "local"
    last_active_text: str
    ai_status: str
    last_ai_edit: str
    thumbnail_class_name: str


class ListProjectsResponse(BaseModel):
    items: list[ProjectMeta]


class CreateProjectRequest(BaseModel):
    title: str | None = Field(default=None, description="Project title（项目标题）")
    source_folder_path: str | None = Field(
        default=None, description="Optional media folder path（可选素材目录）"
    )


class ImportProjectRequest(BaseModel):
    folder_path: str = Field(..., description="Local folder path（本地文件夹路径）")


class CreateProjectResponse(BaseModel):
    project_id: str
    title: str


class _ProjectRecord(BaseModel):
    id: str
    title: str
    storage_type: Literal["cloud", "local"] = "local"
    ai_status: str
    last_ai_edit: str
    thumbnail_class_name: str
    source_folder_path: str | None = None
    created_at: datetime
    updated_at: datetime


_THUMBNAIL_CLASSES = [
    "launch-thumb-cyan",
    "launch-thumb-indigo",
    "launch-thumb-zinc",
    "launch-thumb-rose",
]
_PROJECTS: dict[str, _ProjectRecord] = {}
_PROJECT_LOCK = Lock()


def _http_error(
    *,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> None:
    raise HTTPException(
        status_code=status_code,
        detail={
            "code": code,
            "message": message,
            "details": details or {},
        },
    )


def _not_implemented(feature_name: str) -> None:
    _http_error(
        status_code=501,
        code="NOT_IMPLEMENTED",
        message=f"{feature_name} is not implemented in baseline.",
    )


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _to_last_active_text(updated_at: datetime) -> str:
    seconds = int((_now() - updated_at).total_seconds())
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


def _next_thumbnail(seed: int) -> str:
    return _THUMBNAIL_CLASSES[seed % len(_THUMBNAIL_CLASSES)]


def _new_project_id() -> str:
    return f"proj_{uuid4().hex[:8]}"


def _validate_folder(folder_path: str, *, field_name: str) -> Path:
    normalized = folder_path.strip()
    if not normalized:
        _http_error(
            status_code=400,
            code="CORE_INVALID_FOLDER_PATH",
            message=f"{field_name} is required.",
            details={"field": field_name},
        )
    candidate = Path(normalized)
    if not candidate.exists():
        _http_error(
            status_code=400,
            code="CORE_INVALID_FOLDER_PATH",
            message=f"{field_name} must exist.",
            details={"field": field_name, "path": normalized},
        )
    if candidate.is_file():
        candidate = candidate.parent
    if not candidate.is_dir():
        _http_error(
            status_code=400,
            code="CORE_INVALID_FOLDER_PATH",
            message=f"{field_name} must resolve to a directory.",
            details={"field": field_name, "path": normalized},
        )
    return candidate


def _build_project_meta(record: _ProjectRecord) -> ProjectMeta:
    return ProjectMeta(
        id=record.id,
        title=record.title,
        storage_type=record.storage_type,
        last_active_text=_to_last_active_text(record.updated_at),
        ai_status=record.ai_status,
        last_ai_edit=record.last_ai_edit,
        thumbnail_class_name=record.thumbnail_class_name,
    )


def _create_project_record(*, title: str, source_folder_path: str | None, ai_status: str, last_ai_edit: str) -> _ProjectRecord:
    now = _now()
    return _ProjectRecord(
        id=_new_project_id(),
        title=title,
        storage_type="local",
        ai_status=ai_status,
        last_ai_edit=last_ai_edit,
        thumbnail_class_name=_next_thumbnail(seed=len(_PROJECTS)),
        source_folder_path=source_folder_path,
        created_at=now,
        updated_at=now,
    )


def _seed_projects() -> None:
    seed_data = [
        ("Beach Trip Vlog", "Analyzed 42 clips", "Replaced intro sequence"),
        ("Product Launch Promo_v2", "Ready for export", "Applied color grading patch"),
    ]
    with _PROJECT_LOCK:
        for title, ai_status, last_ai_edit in seed_data:
            record = _create_project_record(
                title=title,
                source_folder_path=None,
                ai_status=ai_status,
                last_ai_edit=last_ai_edit,
            )
            _PROJECTS[record.id] = record


_seed_projects()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "core", "version": "0.1.0"}


@app.get("/api/v1/projects", response_model=ListProjectsResponse)
def list_projects() -> ListProjectsResponse:
    with _PROJECT_LOCK:
        records = sorted(_PROJECTS.values(), key=lambda item: item.updated_at, reverse=True)
        return ListProjectsResponse(items=[_build_project_meta(record) for record in records])


@app.post("/api/v1/projects", response_model=CreateProjectResponse)
def create_project(request: CreateProjectRequest) -> CreateProjectResponse:
    source_folder = request.source_folder_path
    normalized_folder: str | None = None
    if source_folder:
        folder_path = _validate_folder(source_folder, field_name="source_folder_path")
        normalized_folder = str(folder_path.resolve())

    title = request.title.strip() if request.title and request.title.strip() else None
    if not title and normalized_folder:
        title = Path(normalized_folder).name
    if not title:
        title = "Untitled Sequence"

    with _PROJECT_LOCK:
        record = _create_project_record(
            title=title,
            source_folder_path=normalized_folder,
            ai_status="Ready for prompt" if not normalized_folder else "Media linked",
            last_ai_edit="Project created",
        )
        _PROJECTS[record.id] = record

    return CreateProjectResponse(project_id=record.id, title=record.title)


@app.post("/api/v1/projects/import", response_model=CreateProjectResponse)
def import_project(request: ImportProjectRequest) -> CreateProjectResponse:
    folder_path = _validate_folder(request.folder_path, field_name="folder_path")
    title = folder_path.name or "Imported Workspace"

    with _PROJECT_LOCK:
        record = _create_project_record(
            title=title,
            source_folder_path=str(folder_path.resolve()),
            ai_status="Indexing media",
            last_ai_edit="Imported from local folder",
        )
        _PROJECTS[record.id] = record

    return CreateProjectResponse(project_id=record.id, title=record.title)


@app.post("/api/v1/ingest")
def ingest(_: IngestRequest) -> None:
    _not_implemented("Ingestion")


@app.post("/api/v1/search")
def search(_: SearchRequest) -> None:
    _not_implemented("Semantic Search")


@app.post("/api/v1/render")
def render(_: RenderRequest) -> None:
    _not_implemented("Render")
