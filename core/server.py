from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import jwt
import redis
from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP_VERSION = "0.3.0"
CONTRACT_VERSION = "1.0.0"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CORE_QUEUE_KEY = os.getenv("CORE_INGEST_QUEUE_KEY", "entrocut:core:ingest")
CORE_JOB_WAIT_TIMEOUT_SEC = float(os.getenv("CORE_JOB_WAIT_TIMEOUT_SEC", "20"))
CORE_DB_PATH = Path(os.getenv("CORE_DB_PATH", str(Path(__file__).with_name("core.db"))))
AUTH_JWT_ALGORITHM = os.getenv("AUTH_JWT_ALGORITHM", "HS256")
AUTH_JWT_SECRET = os.getenv("AUTH_JWT_SECRET", "").strip()
AUTH_JWT_PUBLIC_KEY = os.getenv("AUTH_JWT_PUBLIC_KEY", "").strip()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("entrocut.core")

app = FastAPI(
    title="Entrocut Core",
    version=APP_VERSION,
    description="Local Core Service（本地核心服务）",
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


class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.retryable = retryable


class AuthContext(BaseModel):
    user_id: str
    token_id: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any]


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


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
    contract_version: str = CONTRACT_VERSION
    project_id: str
    title: str


class AddAssetsResponse(BaseModel):
    contract_version: str = CONTRACT_VERSION
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
    contract_version: str = CONTRACT_VERSION
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
    contract_version: str = CONTRACT_VERSION
    project_id: str
    assets: list[AssetDTO]
    clips: list[ClipDTO]
    stats: IngestStats


class JobAcceptedResponse(BaseModel):
    job_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    project_id: str
    job_type: str
    retryable: bool


class JobStatusResponse(BaseModel):
    job_id: str
    project_id: str
    job_type: str
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: float
    retryable: bool
    error_code: str | None = None
    error_message: str | None = None
    result: dict[str, Any] | None = None
    updated_at: str


class RetryJobResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    project_id: str
    job_type: str


class _AssetRecord(BaseModel):
    asset_id: str
    project_id: str
    user_id: str
    name: str
    duration_ms: int
    type: Literal["video", "audio"]
    source_path: str | None = None
    source_hash: str


class _ClipRecord(BaseModel):
    clip_id: str
    project_id: str
    user_id: str
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
_DB_LOCK = threading.Lock()
_WORKER_STOP = threading.Event()
_WORKER_READY = threading.Event()
_DB_CONN: sqlite3.Connection | None = None
_REDIS_CLIENT: redis.Redis | None = None
_WORKER_THREAD: threading.Thread | None = None


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _now_iso() -> str:
    return _now().isoformat()


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"req_{uuid4().hex[:12]}")


def _json_log(event: str, **kwargs: Any) -> None:
    payload = {"event": event, "ts": _now_iso(), **kwargs}
    logger.info(json.dumps(payload, ensure_ascii=False))


def _error_response(
    *,
    request_id: str,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    merged_details = {"request_id": request_id, "retryable": retryable}
    if details:
        merged_details.update(details)
    body = ErrorEnvelope(
        error=ErrorDetail(
            code=code,
            message=message,
            details=merged_details,
        )
    ).model_dump()
    return JSONResponse(status_code=status_code, content=body, headers={"X-Request-ID": request_id})


def _raise_app_error(
    *,
    code: str,
    message: str,
    status_code: int = 400,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> None:
    raise AppError(
        code=code,
        message=message,
        status_code=status_code,
        details=details,
        retryable=retryable,
    )


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", "").strip() or f"req_{uuid4().hex[:12]}"
    request.state.request_id = request_id
    started = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _json_log(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            latency_ms=latency_ms,
            status_code=500,
        )
        raise
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    _json_log(
        "http_request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        latency_ms=latency_ms,
        status_code=response.status_code,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    _json_log(
        "app_error",
        request_id=_get_request_id(request),
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
    )
    return _error_response(
        request_id=_get_request_id(request),
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        retryable=exc.retryable,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return _error_response(
        request_id=_get_request_id(request),
        code="CORE_REQUEST_INVALID",
        message="Request payload is invalid.",
        status_code=422,
        details={"errors": exc.errors()},
        retryable=False,
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    _json_log(
        "unhandled_error",
        request_id=_get_request_id(request),
        error_type=type(exc).__name__,
        message=str(exc),
    )
    return _error_response(
        request_id=_get_request_id(request),
        code="CORE_INTERNAL_ERROR",
        message="Unexpected core error.",
        status_code=500,
        retryable=True,
    )


def _jwt_verify_key() -> str:
    if AUTH_JWT_ALGORITHM.startswith("HS"):
        if not AUTH_JWT_SECRET:
            _raise_app_error(
                code="AUTH_CONFIG_INVALID",
                message="AUTH_JWT_SECRET is required for HS algorithms.",
                status_code=500,
            )
        return AUTH_JWT_SECRET
    if AUTH_JWT_ALGORITHM.startswith("RS"):
        if not AUTH_JWT_PUBLIC_KEY:
            _raise_app_error(
                code="AUTH_CONFIG_INVALID",
                message="AUTH_JWT_PUBLIC_KEY is required for RS algorithms.",
                status_code=500,
            )
        return AUTH_JWT_PUBLIC_KEY
    _raise_app_error(
        code="AUTH_CONFIG_INVALID",
        message="Unsupported JWT algorithm.",
        status_code=500,
        details={"algorithm": AUTH_JWT_ALGORITHM},
    )
    return ""


def _decode_token(authorization: str | None) -> AuthContext:
    if not authorization:
        _raise_app_error(
            code="AUTH_UNAUTHORIZED",
            message="Missing Authorization header.",
            status_code=401,
            retryable=False,
        )
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        _raise_app_error(
            code="AUTH_UNAUTHORIZED",
            message="Authorization header must use Bearer token.",
            status_code=401,
        )
    token = authorization[len(prefix) :].strip()
    if not token:
        _raise_app_error(
            code="AUTH_UNAUTHORIZED",
            message="Bearer token is empty.",
            status_code=401,
        )
    try:
        payload = jwt.decode(
            token,
            key=_jwt_verify_key(),
            algorithms=[AUTH_JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        _raise_app_error(
            code="AUTH_TOKEN_EXPIRED",
            message="Token expired.",
            status_code=401,
        )
    except jwt.InvalidTokenError:
        _raise_app_error(
            code="AUTH_UNAUTHORIZED",
            message="Invalid token.",
            status_code=401,
        )

    user_id = str(payload.get("sub", "")).strip()
    if not user_id:
        _raise_app_error(
            code="AUTH_INVALID_CLAIMS",
            message="Token claim sub is required.",
            status_code=401,
        )
    token_id = payload.get("jti")
    return AuthContext(user_id=user_id, token_id=str(token_id) if token_id else None)


def get_auth_context(authorization: str | None = Header(default=None)) -> AuthContext:
    return _decode_token(authorization)


def _get_db() -> sqlite3.Connection:
    if _DB_CONN is None:
        raise RuntimeError("DB is not initialized.")
    return _DB_CONN


def _db_exec(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
    db = _get_db()
    with _DB_LOCK:
        cursor = db.execute(query, params)
        db.commit()
        return cursor


def _db_fetchall(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    db = _get_db()
    with _DB_LOCK:
        cursor = db.execute(query, params)
        return cursor.fetchall()


def _db_fetchone(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    db = _get_db()
    with _DB_LOCK:
        cursor = db.execute(query, params)
        return cursor.fetchone()


def _init_db() -> None:
    global _DB_CONN
    CORE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CORE_DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                storage_type TEXT NOT NULL,
                ai_status TEXT NOT NULL,
                last_ai_edit TEXT NOT NULL,
                thumbnail_class_name TEXT NOT NULL,
                source_folder_path TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_updated ON projects(user_id, updated_at DESC);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                duration_ms INTEGER NOT NULL,
                type TEXT NOT NULL,
                source_path TEXT,
                source_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(project_id, user_id, source_hash)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project_id, user_id);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clips (
                clip_id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                score REAL NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id, user_id);")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL,
                retryable INTEGER NOT NULL,
                request_id TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                result_json TEXT,
                error_code TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(project_id, user_id, updated_at DESC);")
    _DB_CONN = conn


def _init_redis() -> None:
    global _REDIS_CLIENT
    try:
        client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        client.ping()
    except Exception as exc:
        _json_log("redis_init_failed", error=str(exc), redis_url=REDIS_URL)
        _REDIS_CLIENT = None
        return
    _REDIS_CLIENT = client
    _json_log("redis_ready", redis_url=REDIS_URL)


def _require_redis() -> redis.Redis:
    if _REDIS_CLIENT is None:
        _raise_app_error(
            code="CORE_QUEUE_UNAVAILABLE",
            message="Redis queue is unavailable.",
            status_code=503,
            retryable=True,
            details={"redis_url": REDIS_URL},
        )
    return _REDIS_CLIENT


def _to_last_active_text(updated_at_iso: str) -> str:
    updated_at = datetime.fromisoformat(updated_at_iso)
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


def _new_job_id() -> str:
    return f"job_{uuid4().hex[:10]}"


def _is_video_path(path: Path) -> bool:
    return path.suffix.lower() in _VIDEO_EXTENSIONS


def _is_video_upload(file: UploadFile) -> bool:
    filename = (file.filename or "").strip()
    content_type = (file.content_type or "").strip().lower()
    ext = Path(filename).suffix.lower()
    return content_type.startswith("video/") or ext in _VIDEO_EXTENSIONS


def _validate_folder(folder_path: str, *, field_name: str) -> Path:
    normalized = folder_path.strip()
    if not normalized:
        _raise_app_error(
            code="CORE_INVALID_FOLDER_PATH",
            message=f"{field_name} is required.",
            status_code=400,
            details={"field": field_name},
        )
    candidate = Path(normalized)
    if not candidate.exists():
        _raise_app_error(
            code="CORE_INVALID_FOLDER_PATH",
            message=f"{field_name} must exist.",
            status_code=400,
            details={"field": field_name, "path": normalized},
        )
    if candidate.is_file():
        candidate = candidate.parent
    if not candidate.is_dir():
        _raise_app_error(
            code="CORE_INVALID_FOLDER_PATH",
            message=f"{field_name} must resolve to a directory.",
            status_code=400,
            details={"field": field_name, "path": normalized},
        )
    return candidate


def _scan_video_files(folder_path: Path) -> list[Path]:
    files: list[Path] = []
    for child in sorted(folder_path.iterdir()):
        if child.is_file() and _is_video_path(child):
            files.append(child)
    return files


def _asset_duration_seed(name: str) -> int:
    base = abs(hash(name)) % 13
    return (8 + base) * 1000


def _stable_source_hash(raw: str) -> str:
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _asset_from_path(*, project_id: str, user_id: str, path: Path) -> _AssetRecord:
    resolved = str(path.resolve())
    return _AssetRecord(
        asset_id=_new_asset_id(),
        project_id=project_id,
        user_id=user_id,
        name=path.name,
        duration_ms=_asset_duration_seed(path.name),
        type="video",
        source_path=resolved,
        source_hash=_stable_source_hash(resolved.lower()),
    )


def _asset_from_upload(*, project_id: str, user_id: str, filename: str) -> _AssetRecord:
    safe = filename.strip() or "uploaded_video.mp4"
    source = f"upload://{safe.lower()}"
    return _AssetRecord(
        asset_id=_new_asset_id(),
        project_id=project_id,
        user_id=user_id,
        name=safe,
        duration_ms=_asset_duration_seed(safe),
        type="video",
        source_path=source,
        source_hash=_stable_source_hash(source),
    )


def _asset_to_dto(row: sqlite3.Row) -> AssetDTO:
    return AssetDTO(
        asset_id=row["asset_id"],
        name=row["name"],
        duration_ms=int(row["duration_ms"]),
        type=row["type"],
    )


def _clip_to_dto(row: sqlite3.Row) -> ClipDTO:
    return ClipDTO(
        clip_id=row["clip_id"],
        asset_id=row["asset_id"],
        start_ms=int(row["start_ms"]),
        end_ms=int(row["end_ms"]),
        score=float(row["score"]),
        description=row["description"],
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
                project_id=asset.project_id,
                user_id=asset.user_id,
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
                project_id=asset.project_id,
                user_id=asset.user_id,
                asset_id=asset.asset_id,
                start_ms=second_start,
                end_ms=max(second_start + 1000, second_end),
                score=0.91,
                description=f"Detail shot from {asset.name}",
            )
        )
    return clips


def _require_project(project_id: str, user_id: str) -> sqlite3.Row:
    row = _db_fetchone(
        """
        SELECT project_id, user_id, title, storage_type, ai_status, last_ai_edit, thumbnail_class_name, source_folder_path, created_at, updated_at
        FROM projects
        WHERE project_id = ? AND user_id = ?
        """,
        (project_id, user_id),
    )
    if not row:
        _raise_app_error(
            code="CORE_PROJECT_NOT_FOUND",
            message="project_id not found.",
            status_code=404,
            details={"project_id": project_id},
        )
    return row


def _count_user_projects(user_id: str) -> int:
    row = _db_fetchone("SELECT COUNT(*) AS count FROM projects WHERE user_id = ?", (user_id,))
    return int(row["count"]) if row else 0


def _insert_project(
    *,
    project_id: str,
    user_id: str,
    title: str,
    source_folder_path: str | None,
    ai_status: str,
    last_ai_edit: str,
) -> None:
    now = _now_iso()
    _db_exec(
        """
        INSERT INTO projects (
            project_id, user_id, title, storage_type, ai_status, last_ai_edit, thumbnail_class_name,
            source_folder_path, created_at, updated_at
        ) VALUES (?, ?, ?, 'local', ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            user_id,
            title,
            ai_status,
            last_ai_edit,
            _next_thumbnail(_count_user_projects(user_id)),
            source_folder_path,
            now,
            now,
        ),
    )


def _insert_assets(assets: list[_AssetRecord]) -> int:
    inserted = 0
    for asset in assets:
        cursor = _db_exec(
            """
            INSERT OR IGNORE INTO assets (
                asset_id, project_id, user_id, name, duration_ms, type, source_path, source_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset.asset_id,
                asset.project_id,
                asset.user_id,
                asset.name,
                asset.duration_ms,
                asset.type,
                asset.source_path,
                asset.source_hash,
                _now_iso(),
            ),
        )
        if cursor.rowcount > 0:
            inserted += 1
    return inserted


def _list_project_assets(project_id: str, user_id: str) -> list[sqlite3.Row]:
    return _db_fetchall(
        """
        SELECT asset_id, project_id, user_id, name, duration_ms, type, source_path, source_hash
        FROM assets
        WHERE project_id = ? AND user_id = ?
        ORDER BY created_at ASC
        """,
        (project_id, user_id),
    )


def _list_project_clips(project_id: str, user_id: str) -> list[sqlite3.Row]:
    return _db_fetchall(
        """
        SELECT clip_id, project_id, user_id, asset_id, start_ms, end_ms, score, description
        FROM clips
        WHERE project_id = ? AND user_id = ?
        ORDER BY start_ms ASC
        """,
        (project_id, user_id),
    )


def _touch_project(*, project_id: str, user_id: str, ai_status: str, last_ai_edit: str) -> None:
    _db_exec(
        """
        UPDATE projects
        SET ai_status = ?, last_ai_edit = ?, updated_at = ?
        WHERE project_id = ? AND user_id = ?
        """,
        (ai_status, last_ai_edit, _now_iso(), project_id, user_id),
    )


def _job_row_to_status(row: sqlite3.Row) -> JobStatusResponse:
    result = json.loads(row["result_json"]) if row["result_json"] else None
    return JobStatusResponse(
        job_id=row["job_id"],
        project_id=row["project_id"],
        job_type=row["job_type"],
        status=row["status"],
        progress=float(row["progress"]),
        retryable=bool(row["retryable"]),
        error_code=row["error_code"],
        error_message=row["error_message"],
        result=result,
        updated_at=row["updated_at"],
    )


def _create_job(
    *,
    user_id: str,
    project_id: str,
    job_type: str,
    payload: dict[str, Any],
    request_id: str,
) -> str:
    job_id = _new_job_id()
    now = _now_iso()
    _db_exec(
        """
        INSERT INTO jobs (
            job_id, user_id, project_id, job_type, status, progress, retryable, request_id,
            payload_json, result_json, error_code, error_message, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'queued', 0.0, 1, ?, ?, NULL, NULL, NULL, ?, ?)
        """,
        (
            job_id,
            user_id,
            project_id,
            job_type,
            request_id,
            json.dumps(payload, ensure_ascii=False),
            now,
            now,
        ),
    )
    return job_id


def _load_job(job_id: str, user_id: str) -> sqlite3.Row:
    row = _db_fetchone(
        """
        SELECT job_id, user_id, project_id, job_type, status, progress, retryable, request_id, payload_json, result_json,
               error_code, error_message, created_at, updated_at
        FROM jobs
        WHERE job_id = ? AND user_id = ?
        """,
        (job_id, user_id),
    )
    if not row:
        _raise_app_error(
            code="CORE_JOB_NOT_FOUND",
            message="job_id not found.",
            status_code=404,
            details={"job_id": job_id},
        )
    return row


def _set_job_running(job_id: str) -> None:
    _db_exec(
        """
        UPDATE jobs
        SET status = 'running', progress = 0.1, updated_at = ?
        WHERE job_id = ?
        """,
        (_now_iso(), job_id),
    )


def _set_job_progress(job_id: str, progress: float) -> None:
    _db_exec(
        """
        UPDATE jobs
        SET progress = ?, updated_at = ?
        WHERE job_id = ?
        """,
        (max(0.0, min(1.0, progress)), _now_iso(), job_id),
    )


def _set_job_success(job_id: str, result: dict[str, Any]) -> None:
    _db_exec(
        """
        UPDATE jobs
        SET status = 'succeeded', progress = 1.0, retryable = 0, result_json = ?, error_code = NULL, error_message = NULL, updated_at = ?
        WHERE job_id = ?
        """,
        (json.dumps(result, ensure_ascii=False), _now_iso(), job_id),
    )


def _set_job_failed(
    job_id: str,
    *,
    error_code: str,
    error_message: str,
    retryable: bool,
) -> None:
    _db_exec(
        """
        UPDATE jobs
        SET status = 'failed', retryable = ?, error_code = ?, error_message = ?, updated_at = ?
        WHERE job_id = ?
        """,
        (1 if retryable else 0, error_code, error_message, _now_iso(), job_id),
    )


def _enqueue_job(queue_key: str, job_id: str) -> None:
    redis_client = _require_redis()
    try:
        redis_client.lpush(queue_key, job_id)
    except Exception as exc:
        _set_job_failed(
            job_id,
            error_code="CORE_QUEUE_ENQUEUE_FAILED",
            error_message="Failed to enqueue job.",
            retryable=True,
        )
        _raise_app_error(
            code="CORE_QUEUE_ENQUEUE_FAILED",
            message="Failed to enqueue job.",
            status_code=503,
            details={"reason": str(exc), "job_id": job_id},
            retryable=True,
        )


def _wait_job_completion(*, job_id: str, user_id: str, timeout_sec: float) -> sqlite3.Row:
    start = time.monotonic()
    while time.monotonic() - start < timeout_sec:
        row = _load_job(job_id, user_id)
        if row["status"] in {"succeeded", "failed"}:
            return row
        time.sleep(0.1)
    _raise_app_error(
        code="CORE_JOB_TIMEOUT",
        message="Job timed out.",
        status_code=504,
        details={"job_id": job_id},
        retryable=True,
    )
    raise RuntimeError("unreachable")


def _enqueue_ingest_job(*, user_id: str, project_id: str, request_id: str) -> str:
    _require_project(project_id, user_id)
    job_id = _create_job(
        user_id=user_id,
        project_id=project_id,
        job_type="ingest",
        payload={"project_id": project_id, "user_id": user_id},
        request_id=request_id,
    )
    _enqueue_job(CORE_QUEUE_KEY, job_id)
    return job_id


def _process_ingest_job(job_id: str) -> None:
    row = _db_fetchone(
        """
        SELECT job_id, user_id, project_id, job_type, status, payload_json
        FROM jobs
        WHERE job_id = ?
        """,
        (job_id,),
    )
    if not row or row["status"] not in {"queued", "running"}:
        return

    payload = json.loads(row["payload_json"])
    project_id = payload["project_id"]
    user_id = payload["user_id"]

    try:
        _set_job_running(job_id)
        _set_job_progress(job_id, 0.2)
        _require_project(project_id, user_id)

        asset_rows = _list_project_assets(project_id, user_id)
        if not asset_rows:
            _set_job_failed(
                job_id,
                error_code="CORE_NO_MEDIA",
                error_message="No media assets found for project.",
                retryable=False,
            )
            return

        assets = [
            _AssetRecord(
                asset_id=asset["asset_id"],
                project_id=project_id,
                user_id=user_id,
                name=asset["name"],
                duration_ms=int(asset["duration_ms"]),
                type=asset["type"],
                source_path=asset["source_path"],
                source_hash=asset["source_hash"],
            )
            for asset in asset_rows
        ]
        clips = _generate_clips_for_assets(assets)
        _set_job_progress(job_id, 0.7)

        _db_exec("DELETE FROM clips WHERE project_id = ? AND user_id = ?", (project_id, user_id))
        for clip in clips:
            _db_exec(
                """
                INSERT INTO clips (
                    clip_id, project_id, user_id, asset_id, start_ms, end_ms, score, description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clip.clip_id,
                    clip.project_id,
                    clip.user_id,
                    clip.asset_id,
                    clip.start_ms,
                    clip.end_ms,
                    clip.score,
                    clip.description,
                    _now_iso(),
                ),
            )

        _touch_project(
            project_id=project_id,
            user_id=user_id,
            ai_status=f"Analyzed {len(clips)} clips",
            last_ai_edit="Ingest completed",
        )

        result = IngestResponse(
            project_id=project_id,
            assets=[AssetDTO(asset_id=item.asset_id, name=item.name, duration_ms=item.duration_ms, type=item.type) for item in assets],
            clips=[
                ClipDTO(
                    clip_id=item.clip_id,
                    asset_id=item.asset_id,
                    start_ms=item.start_ms,
                    end_ms=item.end_ms,
                    score=item.score,
                    description=item.description,
                )
                for item in clips
            ],
            stats=IngestStats(
                clip_count=len(clips),
                processing_ms=1200 + len(clips) * 60,
            ),
        ).model_dump()
        _set_job_success(job_id, result)
    except AppError as exc:
        _set_job_failed(
            job_id,
            error_code=exc.code,
            error_message=exc.message,
            retryable=exc.retryable,
        )
    except Exception as exc:
        _set_job_failed(
            job_id,
            error_code="CORE_INGEST_FAILED",
            error_message="Ingest job failed unexpectedly.",
            retryable=True,
        )
        _json_log("ingest_job_crash", job_id=job_id, reason=str(exc))


def _worker_loop() -> None:
    _WORKER_READY.set()
    while not _WORKER_STOP.is_set():
        if _REDIS_CLIENT is None:
            time.sleep(1.0)
            continue
        try:
            item = _REDIS_CLIENT.brpop(CORE_QUEUE_KEY, timeout=1)
        except Exception as exc:
            _json_log("worker_redis_error", reason=str(exc))
            time.sleep(1.0)
            continue
        if not item:
            continue
        _, job_id = item
        _process_ingest_job(job_id)


@app.on_event("startup")
def on_startup() -> None:
    global _WORKER_THREAD
    _init_db()
    _init_redis()
    _WORKER_STOP.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, name="core-ingest-worker", daemon=True)
    _WORKER_THREAD.start()
    _WORKER_READY.wait(timeout=2)
    _json_log("core_started", version=APP_VERSION, db=str(CORE_DB_PATH), redis_url=REDIS_URL)


@app.on_event("shutdown")
def on_shutdown() -> None:
    _WORKER_STOP.set()
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        _WORKER_THREAD.join(timeout=2)
    if _DB_CONN is not None:
        _DB_CONN.close()


@app.get("/health")
def health() -> dict[str, Any]:
    redis_ok = False
    if _REDIS_CLIENT is not None:
        try:
            redis_ok = bool(_REDIS_CLIENT.ping())
        except Exception:
            redis_ok = False
    return {
        "status": "ok",
        "service": "core",
        "version": APP_VERSION,
        "queue": {
            "backend": "redis",
            "redis_url": REDIS_URL,
            "ready": redis_ok,
        },
        "storage": {
            "backend": "sqlite",
            "db_path": str(CORE_DB_PATH),
        },
    }


@app.get("/api/v1/projects", response_model=ListProjectsResponse)
def list_projects(auth: AuthContext = Depends(get_auth_context)) -> ListProjectsResponse:
    rows = _db_fetchall(
        """
        SELECT project_id, title, storage_type, ai_status, last_ai_edit, thumbnail_class_name, updated_at
        FROM projects
        WHERE user_id = ?
        ORDER BY updated_at DESC
        """,
        (auth.user_id,),
    )
    items = [
        ProjectMeta(
            id=row["project_id"],
            title=row["title"],
            storage_type=row["storage_type"],
            last_active_text=_to_last_active_text(row["updated_at"]),
            ai_status=row["ai_status"],
            last_ai_edit=row["last_ai_edit"],
            thumbnail_class_name=row["thumbnail_class_name"],
        )
        for row in rows
    ]
    return ListProjectsResponse(items=items)


@app.get("/api/v1/projects/{project_id}", response_model=ProjectDetailResponse)
def get_project(project_id: str, auth: AuthContext = Depends(get_auth_context)) -> ProjectDetailResponse:
    record = _require_project(project_id, auth.user_id)
    assets = _list_project_assets(project_id, auth.user_id)
    clips = _list_project_clips(project_id, auth.user_id)
    return ProjectDetailResponse(
        project_id=record["project_id"],
        title=record["title"],
        ai_status=record["ai_status"],
        last_ai_edit=record["last_ai_edit"],
        assets=[_asset_to_dto(asset) for asset in assets],
        clips=[_clip_to_dto(clip) for clip in clips],
    )


@app.post("/api/v1/projects", response_model=CreateProjectResponse)
def create_project(request: CreateProjectRequest, auth: AuthContext = Depends(get_auth_context)) -> CreateProjectResponse:
    source_folder = request.source_folder_path
    normalized_folder: str | None = None
    imported_assets: list[_AssetRecord] = []
    project_id = _new_project_id()

    if source_folder:
        folder_path = _validate_folder(source_folder, field_name="source_folder_path")
        normalized_folder = str(folder_path.resolve())
        imported_assets = [
            _asset_from_path(project_id=project_id, user_id=auth.user_id, path=path)
            for path in _scan_video_files(folder_path)
        ]

    title = request.title.strip() if request.title and request.title.strip() else None
    if not title and normalized_folder:
        title = Path(normalized_folder).name
    if not title:
        title = "Untitled Sequence"

    _insert_project(
        project_id=project_id,
        user_id=auth.user_id,
        title=title,
        source_folder_path=normalized_folder,
        ai_status="Media linked" if imported_assets else "Ready for prompt",
        last_ai_edit="Project created",
    )
    if imported_assets:
        _insert_assets(imported_assets)
    return CreateProjectResponse(project_id=project_id, title=title)


@app.post("/api/v1/projects/import", response_model=CreateProjectResponse)
def import_project(request: ImportProjectRequest, auth: AuthContext = Depends(get_auth_context)) -> CreateProjectResponse:
    folder_path = _validate_folder(request.folder_path, field_name="folder_path")
    project_id = _new_project_id()
    assets = [
        _asset_from_path(project_id=project_id, user_id=auth.user_id, path=path)
        for path in _scan_video_files(folder_path)
    ]
    title = folder_path.name or "Imported Workspace"
    _insert_project(
        project_id=project_id,
        user_id=auth.user_id,
        title=title,
        source_folder_path=str(folder_path.resolve()),
        ai_status="Media linked" if assets else "No media found",
        last_ai_edit="Imported from local folder",
    )
    if assets:
        _insert_assets(assets)
    return CreateProjectResponse(project_id=project_id, title=title)


@app.post("/api/v1/projects/upload", response_model=CreateProjectResponse)
async def upload_project(
    auth: AuthContext = Depends(get_auth_context),
    files: list[UploadFile] = File(..., description="Video files（视频文件）"),
    title: str | None = Form(default=None),
) -> CreateProjectResponse:
    valid_videos = [file for file in files if _is_video_upload(file)]
    if not valid_videos:
        _raise_app_error(
            code="CORE_INVALID_UPLOAD_FILES",
            message="No valid video files were provided.",
            status_code=400,
            details={"accepted_ext": sorted(_VIDEO_EXTENSIONS), "total_received": len(files)},
        )

    project_id = _new_project_id()
    normalized_title = title.strip() if title and title.strip() else ""
    if not normalized_title:
        sample_name = (valid_videos[0].filename or "").strip()
        normalized_title = Path(sample_name).stem if sample_name else "Uploaded Workspace"
    if not normalized_title:
        normalized_title = "Uploaded Workspace"

    assets = [
        _asset_from_upload(project_id=project_id, user_id=auth.user_id, filename=file.filename or "uploaded_video.mp4")
        for file in valid_videos
    ]
    _insert_project(
        project_id=project_id,
        user_id=auth.user_id,
        title=normalized_title,
        source_folder_path=None,
        ai_status=f"Uploaded {len(assets)} videos",
        last_ai_edit="Uploaded from browser picker",
    )
    _insert_assets(assets)

    for file in files:
        await file.close()

    return CreateProjectResponse(project_id=project_id, title=normalized_title)


@app.post("/api/v1/projects/{project_id}/assets/import", response_model=AddAssetsResponse)
def add_assets_from_folder(
    project_id: str,
    request: AddAssetsRequest,
    auth: AuthContext = Depends(get_auth_context),
) -> AddAssetsResponse:
    _require_project(project_id, auth.user_id)
    folder_path = _validate_folder(request.folder_path, field_name="folder_path")
    assets = [
        _asset_from_path(project_id=project_id, user_id=auth.user_id, path=path)
        for path in _scan_video_files(folder_path)
    ]
    if not assets:
        _raise_app_error(
            code="CORE_NO_MEDIA",
            message="No supported video files were found in folder.",
            status_code=400,
            details={"folder_path": str(folder_path.resolve())},
        )
    inserted = _insert_assets(assets)
    total_assets = len(_list_project_assets(project_id, auth.user_id))
    _touch_project(
        project_id=project_id,
        user_id=auth.user_id,
        ai_status=f"Media linked ({total_assets} assets)",
        last_ai_edit="Added assets from local folder",
    )
    return AddAssetsResponse(project_id=project_id, added_count=inserted, total_assets=total_assets)


@app.post("/api/v1/projects/{project_id}/assets/upload", response_model=AddAssetsResponse)
async def add_assets_from_upload(
    project_id: str,
    auth: AuthContext = Depends(get_auth_context),
    files: list[UploadFile] = File(..., description="Video files（视频文件）"),
) -> AddAssetsResponse:
    _require_project(project_id, auth.user_id)
    valid_videos = [file for file in files if _is_video_upload(file)]
    if not valid_videos:
        _raise_app_error(
            code="CORE_INVALID_UPLOAD_FILES",
            message="No valid video files were provided.",
            status_code=400,
            details={"accepted_ext": sorted(_VIDEO_EXTENSIONS), "total_received": len(files)},
        )
    assets = [
        _asset_from_upload(project_id=project_id, user_id=auth.user_id, filename=file.filename or "uploaded_video.mp4")
        for file in valid_videos
    ]
    inserted = _insert_assets(assets)
    total_assets = len(_list_project_assets(project_id, auth.user_id))
    _touch_project(
        project_id=project_id,
        user_id=auth.user_id,
        ai_status=f"Media linked ({total_assets} assets)",
        last_ai_edit=f"Uploaded {inserted} assets",
    )
    for file in files:
        await file.close()
    return AddAssetsResponse(project_id=project_id, added_count=inserted, total_assets=total_assets)


@app.post("/api/v1/ingest/jobs", response_model=JobAcceptedResponse)
def create_ingest_job(
    request: IngestRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> JobAcceptedResponse:
    job_id = _enqueue_ingest_job(user_id=auth.user_id, project_id=request.project_id, request_id=_get_request_id(req))
    return JobAcceptedResponse(
        job_id=job_id,
        status="queued",
        project_id=request.project_id,
        job_type="ingest",
        retryable=True,
    )


@app.post("/api/v1/ingest", response_model=IngestResponse)
def ingest(
    request: IngestRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> IngestResponse:
    job_id = _enqueue_ingest_job(user_id=auth.user_id, project_id=request.project_id, request_id=_get_request_id(req))
    row = _wait_job_completion(job_id=job_id, user_id=auth.user_id, timeout_sec=CORE_JOB_WAIT_TIMEOUT_SEC)
    if row["status"] == "failed":
        _raise_app_error(
            code=row["error_code"] or "CORE_INGEST_FAILED",
            message=row["error_message"] or "Ingest failed.",
            status_code=400,
            retryable=bool(row["retryable"]),
            details={"job_id": job_id},
        )
    result_json = row["result_json"]
    if not result_json:
        _raise_app_error(
            code="CORE_INGEST_RESULT_MISSING",
            message="Ingest result is empty.",
            status_code=500,
            details={"job_id": job_id},
            retryable=True,
        )
    return IngestResponse.model_validate(json.loads(result_json))


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, auth: AuthContext = Depends(get_auth_context)) -> JobStatusResponse:
    row = _load_job(job_id, auth.user_id)
    return _job_row_to_status(row)


@app.post("/api/v1/jobs/{job_id}/retry", response_model=RetryJobResponse)
def retry_job(job_id: str, auth: AuthContext = Depends(get_auth_context)) -> RetryJobResponse:
    row = _load_job(job_id, auth.user_id)
    if row["status"] != "failed":
        _raise_app_error(
            code="CORE_JOB_RETRY_INVALID_STATE",
            message="Only failed jobs can be retried.",
            status_code=409,
            details={"status": row["status"], "job_id": job_id},
        )
    if not bool(row["retryable"]):
        _raise_app_error(
            code="CORE_JOB_NOT_RETRYABLE",
            message="Job is not retryable.",
            status_code=409,
            details={"job_id": job_id},
        )
    _db_exec(
        """
        UPDATE jobs
        SET status = 'queued', progress = 0.0, error_code = NULL, error_message = NULL, updated_at = ?
        WHERE job_id = ? AND user_id = ?
        """,
        (_now_iso(), job_id, auth.user_id),
    )
    _enqueue_job(CORE_QUEUE_KEY, job_id)
    return RetryJobResponse(
        job_id=job_id,
        status="queued",
        project_id=row["project_id"],
        job_type=row["job_type"],
    )


@app.post("/api/v1/search")
def search(_: SearchRequest, __: AuthContext = Depends(get_auth_context)) -> None:
    _raise_app_error(
        code="NOT_IMPLEMENTED",
        message="Semantic Search is not implemented in baseline.",
        status_code=501,
        retryable=False,
    )


@app.post("/api/v1/render")
def render(_: RenderRequest, __: AuthContext = Depends(get_auth_context)) -> None:
    _raise_app_error(
        code="NOT_IMPLEMENTED",
        message="Render is not implemented in baseline.",
        status_code=501,
        retryable=False,
    )
