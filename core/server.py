from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Entrocut Core Shell",
    version="0.2.0",
    description="Local Service Shell（本地服务壳层）",
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
    project_id: str = Field(..., description="Project ID（项目标识）")


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


class AddAssetsRequest(BaseModel):
    folder_path: str = Field(..., description="Local folder path（本地文件夹路径）")


class CreateProjectResponse(BaseModel):
    project_id: str
    title: str


class AddAssetsResponse(BaseModel):
    project_id: str
    added_count: int
    total_assets: int


class AssetDTO(BaseModel):
    asset_id: str
    name: str
    duration_ms: int
    type: Literal["video", "audio"] = "video"


class ClipDTO(BaseModel):
    clip_id: str
    asset_id: str
    start_ms: int
    end_ms: int
    score: float
    description: str


class ProjectDetailResponse(BaseModel):
    project_id: str
    title: str
    ai_status: str
    last_ai_edit: str
    assets: list[AssetDTO]
    clips: list[ClipDTO]


class IngestStats(BaseModel):
    clip_count: int
    processing_ms: int


class IngestResponse(BaseModel):
    project_id: str
    assets: list[AssetDTO]
    clips: list[ClipDTO]
    stats: IngestStats


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


class _AssetRecord(BaseModel):
    asset_id: str
    name: str
    duration_ms: int
    type: Literal["video", "audio"] = "video"
    source_path: str | None = None


class _ClipRecord(BaseModel):
    clip_id: str
    asset_id: str
    start_ms: int
    end_ms: int
    score: float
    description: str


_THUMBNAIL_CLASSES = [
    "launch-thumb-cyan",
    "launch-thumb-indigo",
    "launch-thumb-zinc",
    "launch-thumb-rose",
]
_VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".webm"}
_PROJECTS: dict[str, _ProjectRecord] = {}
_PROJECT_ASSETS: dict[str, list[_AssetRecord]] = {}
_PROJECT_CLIPS: dict[str, list[_ClipRecord]] = {}
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


def _new_asset_id() -> str:
    return f"asset_{uuid4().hex[:8]}"


def _new_clip_id() -> str:
    return f"clip_{uuid4().hex[:8]}"


def _is_video_path(path: Path) -> bool:
    return path.suffix.lower() in _VIDEO_EXTENSIONS


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


def _scan_video_files(folder_path: Path) -> list[Path]:
    files: list[Path] = []
    for child in sorted(folder_path.iterdir()):
        if child.is_file() and _is_video_path(child):
            files.append(child)
    return files


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


def _is_video_upload(file: UploadFile) -> bool:
    filename = (file.filename or "").strip()
    content_type = (file.content_type or "").strip().lower()
    ext = Path(filename).suffix.lower()
    return content_type.startswith("video/") or ext in _VIDEO_EXTENSIONS


def _create_project_record(
    *,
    title: str,
    source_folder_path: str | None,
    ai_status: str,
    last_ai_edit: str,
) -> _ProjectRecord:
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


def _asset_duration_seed(name: str) -> int:
    base = abs(hash(name)) % 13
    return (8 + base) * 1000


def _asset_from_path(path: Path) -> _AssetRecord:
    return _AssetRecord(
        asset_id=_new_asset_id(),
        name=path.name,
        duration_ms=_asset_duration_seed(path.name),
        type="video",
        source_path=str(path.resolve()),
    )


def _asset_from_upload_name(filename: str) -> _AssetRecord:
    safe = filename.strip() or "uploaded_video.mp4"
    return _AssetRecord(
        asset_id=_new_asset_id(),
        name=safe,
        duration_ms=_asset_duration_seed(safe),
        type="video",
        source_path=f"upload://{safe}",
    )


def _asset_to_dto(asset: _AssetRecord) -> AssetDTO:
    return AssetDTO(
        asset_id=asset.asset_id,
        name=asset.name,
        duration_ms=asset.duration_ms,
        type=asset.type,
    )


def _clip_to_dto(clip: _ClipRecord) -> ClipDTO:
    return ClipDTO(
        clip_id=clip.clip_id,
        asset_id=clip.asset_id,
        start_ms=clip.start_ms,
        end_ms=clip.end_ms,
        score=clip.score,
        description=clip.description,
    )


def _generate_clips_for_assets(assets: list[_AssetRecord]) -> list[_ClipRecord]:
    clips: list[_ClipRecord] = []
    for index, asset in enumerate(assets):
        first_end = min(asset.duration_ms, 5000 + (index % 4) * 500)
        second_start = max(0, first_end - 2000)
        second_end = min(asset.duration_ms, second_start + 4500)
        clips.append(
            _ClipRecord(
                clip_id=_new_clip_id(),
                asset_id=asset.asset_id,
                start_ms=0,
                end_ms=max(1200, first_end),
                score=0.86,
                description=f"Auto clip from {asset.name}",
            )
        )
        clips.append(
            _ClipRecord(
                clip_id=_new_clip_id(),
                asset_id=asset.asset_id,
                start_ms=second_start,
                end_ms=max(second_start + 1000, second_end),
                score=0.91,
                description=f"Detail shot from {asset.name}",
            )
        )
    return clips


def _get_project_or_raise(project_id: str) -> _ProjectRecord:
    record = _PROJECTS.get(project_id)
    if not record:
        _http_error(
            status_code=404,
            code="CORE_PROJECT_NOT_FOUND",
            message="project_id not found.",
            details={"project_id": project_id},
        )
    return record


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
            _PROJECT_ASSETS[record.id] = []
            _PROJECT_CLIPS[record.id] = []


_seed_projects()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "core", "version": "0.2.0"}


@app.get("/api/v1/projects", response_model=ListProjectsResponse)
def list_projects() -> ListProjectsResponse:
    with _PROJECT_LOCK:
        records = sorted(_PROJECTS.values(), key=lambda item: item.updated_at, reverse=True)
        return ListProjectsResponse(items=[_build_project_meta(record) for record in records])


@app.get("/api/v1/projects/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: str) -> ProjectDetailResponse:
    with _PROJECT_LOCK:
        record = _get_project_or_raise(project_id)
        assets = _PROJECT_ASSETS.get(project_id, [])
        clips = _PROJECT_CLIPS.get(project_id, [])
        return ProjectDetailResponse(
            project_id=record.id,
            title=record.title,
            ai_status=record.ai_status,
            last_ai_edit=record.last_ai_edit,
            assets=[_asset_to_dto(asset) for asset in assets],
            clips=[_clip_to_dto(clip) for clip in clips],
        )


@app.post("/api/v1/projects", response_model=CreateProjectResponse)
def create_project(request: CreateProjectRequest) -> CreateProjectResponse:
    source_folder = request.source_folder_path
    normalized_folder: str | None = None
    imported_assets: list[_AssetRecord] = []
    if source_folder:
        folder_path = _validate_folder(source_folder, field_name="source_folder_path")
        normalized_folder = str(folder_path.resolve())
        imported_assets = [_asset_from_path(path) for path in _scan_video_files(folder_path)]

    title = request.title.strip() if request.title and request.title.strip() else None
    if not title and normalized_folder:
        title = Path(normalized_folder).name
    if not title:
        title = "Untitled Sequence"

    with _PROJECT_LOCK:
        record = _create_project_record(
            title=title,
            source_folder_path=normalized_folder,
            ai_status="Media linked" if imported_assets else "Ready for prompt",
            last_ai_edit="Project created",
        )
        _PROJECTS[record.id] = record
        _PROJECT_ASSETS[record.id] = imported_assets
        _PROJECT_CLIPS[record.id] = []

    return CreateProjectResponse(project_id=record.id, title=record.title)


@app.post("/api/v1/projects/import", response_model=CreateProjectResponse)
def import_project(request: ImportProjectRequest) -> CreateProjectResponse:
    folder_path = _validate_folder(request.folder_path, field_name="folder_path")
    assets = [_asset_from_path(path) for path in _scan_video_files(folder_path)]
    title = folder_path.name or "Imported Workspace"

    with _PROJECT_LOCK:
        record = _create_project_record(
            title=title,
            source_folder_path=str(folder_path.resolve()),
            ai_status="Media linked" if assets else "No media found",
            last_ai_edit="Imported from local folder",
        )
        _PROJECTS[record.id] = record
        _PROJECT_ASSETS[record.id] = assets
        _PROJECT_CLIPS[record.id] = []

    return CreateProjectResponse(project_id=record.id, title=record.title)


@app.post("/api/v1/projects/upload", response_model=CreateProjectResponse)
async def upload_project(
    files: list[UploadFile] = File(..., description="Video files（视频文件）"),
    title: str | None = Form(default=None),
) -> CreateProjectResponse:
    valid_videos = [file for file in files if _is_video_upload(file)]
    if not valid_videos:
        _http_error(
            status_code=400,
            code="CORE_INVALID_UPLOAD_FILES",
            message="No valid video files were provided.",
            details={"accepted_ext": sorted(_VIDEO_EXTENSIONS), "total_received": len(files)},
        )

    normalized_title = title.strip() if title and title.strip() else ""
    if not normalized_title:
        sample_name = (valid_videos[0].filename or "").strip()
        normalized_title = Path(sample_name).stem if sample_name else "Uploaded Workspace"
    if not normalized_title:
        normalized_title = "Uploaded Workspace"

    assets = [_asset_from_upload_name(file.filename or "uploaded_video.mp4") for file in valid_videos]

    with _PROJECT_LOCK:
        record = _create_project_record(
            title=normalized_title,
            source_folder_path=None,
            ai_status=f"Uploaded {len(assets)} videos",
            last_ai_edit="Uploaded from browser picker",
        )
        _PROJECTS[record.id] = record
        _PROJECT_ASSETS[record.id] = assets
        _PROJECT_CLIPS[record.id] = []

    for file in files:
        await file.close()

    return CreateProjectResponse(project_id=record.id, title=record.title)


@app.post("/api/v1/projects/{project_id}/assets/import", response_model=AddAssetsResponse)
def add_assets_from_folder(project_id: str, request: AddAssetsRequest) -> AddAssetsResponse:
    folder_path = _validate_folder(request.folder_path, field_name="folder_path")
    assets = [_asset_from_path(path) for path in _scan_video_files(folder_path)]
    if not assets:
        _http_error(
            status_code=400,
            code="CORE_NO_MEDIA",
            message="No supported video files were found in folder.",
            details={"folder_path": str(folder_path.resolve())},
        )

    with _PROJECT_LOCK:
        record = _get_project_or_raise(project_id)
        existing_assets = _PROJECT_ASSETS.get(project_id, [])
        existing_assets.extend(assets)
        _PROJECT_ASSETS[project_id] = existing_assets
        record.ai_status = f"Media linked ({len(existing_assets)} assets)"
        record.last_ai_edit = "Added assets from local folder"
        record.updated_at = _now()

    return AddAssetsResponse(
        project_id=project_id,
        added_count=len(assets),
        total_assets=len(_PROJECT_ASSETS.get(project_id, [])),
    )


@app.post("/api/v1/projects/{project_id}/assets/upload", response_model=AddAssetsResponse)
async def add_assets_from_upload(
    project_id: str,
    files: list[UploadFile] = File(..., description="Video files（视频文件）"),
) -> AddAssetsResponse:
    valid_videos = [file for file in files if _is_video_upload(file)]
    if not valid_videos:
        _http_error(
            status_code=400,
            code="CORE_INVALID_UPLOAD_FILES",
            message="No valid video files were provided.",
            details={"accepted_ext": sorted(_VIDEO_EXTENSIONS), "total_received": len(files)},
        )

    assets = [_asset_from_upload_name(file.filename or "uploaded_video.mp4") for file in valid_videos]
    with _PROJECT_LOCK:
        record = _get_project_or_raise(project_id)
        existing_assets = _PROJECT_ASSETS.get(project_id, [])
        existing_assets.extend(assets)
        _PROJECT_ASSETS[project_id] = existing_assets
        record.ai_status = f"Media linked ({len(existing_assets)} assets)"
        record.last_ai_edit = f"Uploaded {len(assets)} assets"
        record.updated_at = _now()

    for file in files:
        await file.close()

    return AddAssetsResponse(
        project_id=project_id,
        added_count=len(assets),
        total_assets=len(_PROJECT_ASSETS.get(project_id, [])),
    )


@app.post("/api/v1/ingest", response_model=IngestResponse)
def ingest(request: IngestRequest) -> IngestResponse:
    with _PROJECT_LOCK:
        record = _get_project_or_raise(request.project_id)
        assets = _PROJECT_ASSETS.get(request.project_id, [])
        if not assets:
            _http_error(
                status_code=400,
                code="CORE_NO_MEDIA",
                message="No media assets found for project.",
                details={"project_id": request.project_id},
            )
        clips = _generate_clips_for_assets(assets)
        _PROJECT_CLIPS[request.project_id] = clips
        record.ai_status = f"Analyzed {len(clips)} clips"
        record.last_ai_edit = "Ingest completed"
        record.updated_at = _now()

    return IngestResponse(
        project_id=request.project_id,
        assets=[_asset_to_dto(asset) for asset in assets],
        clips=[_clip_to_dto(clip) for clip in clips],
        stats=IngestStats(
            clip_count=len(clips),
            processing_ms=1200 + len(clips) * 60,
        ),
    )


@app.post("/api/v1/search")
def search(_: SearchRequest) -> None:
    _not_implemented("Semantic Search")


@app.post("/api/v1/render")
def render(_: RenderRequest) -> None:
    _not_implemented("Render")
