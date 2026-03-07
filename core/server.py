from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4
from urllib.parse import quote

import jwt
import redis
from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.schemas.events import CoreEventEnvelope, CoreSessionReadyPayload, NotificationPayload
from app.services.runtime import build_core_runtime

APP_VERSION = "0.3.0"
CONTRACT_VERSION = "1.0.0"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
CORE_QUEUE_KEY = os.getenv("CORE_INGEST_QUEUE_KEY", "entrocut:core:ingest")
CORE_JOB_WAIT_TIMEOUT_SEC = float(os.getenv("CORE_JOB_WAIT_TIMEOUT_SEC", "20"))
CORE_DB_PATH = Path(os.getenv("CORE_DB_PATH", str(Path(__file__).with_name("core.db"))))
SERVER_BASE_URL = os.getenv("SERVER_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
CORE_SERVER_TIMEOUT_SEC = float(os.getenv("CORE_SERVER_TIMEOUT_SEC", "20"))
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


class IndexUpsertRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    clips: list[dict[str, Any]] = Field(default_factory=list, description="Clip payload（片段负载）")


class ChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    session_id: str | None = Field(default=None, description="Session ID（会话标识）")
    user_id: str | None = Field(default=None, description="User ID（用户标识）")
    message: str = Field(..., description="User prompt（用户输入）")
    context: dict[str, Any] | None = Field(default=None, description="Context payload（上下文）")
    current_project: dict[str, Any] | None = Field(
        default=None, description="Current project contract（当前项目契约）"
    )


class SearchRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    query: str = Field(..., description="Semantic query（语义查询）")
    top_k: int = Field(default=5, ge=1, le=20, description="Top K（返回条数）")


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
    workflow_state: str = "ready"
    active_task_type: str | None = None
    pending_prompt: str | None = None
    last_event_sequence: int = 0
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


class RuntimeCapabilitiesResponse(BaseModel):
    service: Literal["core"] = "core"
    websocket_path: str
    websocket_auth: str = "query_token"
    session_resume: bool = True
    workflows: list[str]
    tools: list[str]
    gateways: list[str]


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
_WORKFLOW_PROMPT_INPUT_REQUIRED = "prompt_input_required"
_WORKFLOW_AWAITING_MEDIA = "awaiting_media"
_WORKFLOW_MEDIA_READY = "media_ready"
_WORKFLOW_MEDIA_PROCESSING = "media_processing"
_WORKFLOW_CHAT_THINKING = "chat_thinking"
_WORKFLOW_READY = "ready"
_WORKFLOW_RENDERING = "rendering"
_WORKFLOW_FAILED = "failed"
_ACTIVE_TASK_TYPES = {"ingest", "index", "chat", "render"}
_UNSET = object()
_DB_LOCK = threading.Lock()
_WORKER_STOP = threading.Event()
_WORKER_READY = threading.Event()
_DB_CONN: sqlite3.Connection | None = None
_REDIS_CLIENT: redis.Redis | None = None
_WORKER_THREAD: threading.Thread | None = None
_CORE_RUNTIME = build_core_runtime()


def _now() -> datetime:
    return datetime.now(tz=UTC)


def _now_iso() -> str:
    return _now().isoformat()


def _get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"req_{uuid4().hex[:12]}")


def _json_log(event: str, **kwargs: Any) -> None:
    payload = {"event": event, "ts": _now_iso(), **kwargs}
    logger.info(json.dumps(payload, ensure_ascii=False))


def _run_sync_coro(coro: Any) -> Any:
    return asyncio.run(coro)


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


def _get_websocket_auth_context(websocket: WebSocket) -> AuthContext:
    query_authorization = websocket.query_params.get("authorization", "").strip()
    access_token = websocket.query_params.get("access_token", "").strip()
    header_authorization = websocket.headers.get("authorization", "").strip()
    authorization = header_authorization
    if not authorization and query_authorization:
        authorization = query_authorization
    if not authorization and access_token:
        authorization = f"Bearer {access_token}"
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


def _server_url(path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{SERVER_BASE_URL}{normalized}"


def _decode_json_object(raw: bytes, *, code: str, message: str) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        _raise_app_error(
            code=code,
            message=message,
            status_code=502,
            details={"cause": str(exc)},
            retryable=True,
        )
    if not isinstance(payload, dict):
        _raise_app_error(
            code=code,
            message=message,
            status_code=502,
            details={"response_type": type(payload).__name__},
            retryable=True,
        )
    return payload


def _proxy_server_json(*, path: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Request-ID": _get_request_id(request),
    }
    authorization = request.headers.get("authorization")
    if authorization:
        headers["Authorization"] = authorization

    upstream_request = urllib.request.Request(
        _server_url(path),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(upstream_request, timeout=CORE_SERVER_TIMEOUT_SEC) as response:
            return _decode_json_object(
                response.read(),
                code="SERVER_PROXY_INVALID_RESPONSE",
                message="Server returned invalid response payload.",
            )
    except urllib.error.HTTPError as exc:
        upstream_headers = getattr(exc, "headers", None)
        upstream_request_id = upstream_headers.get("X-Request-ID") if upstream_headers else None
        upstream_payload = _decode_json_object(
            exc.read(),
            code="SERVER_PROXY_INVALID_ERROR_RESPONSE",
            message="Server returned invalid error payload.",
        )
        upstream_error = upstream_payload.get("error")
        if isinstance(upstream_error, dict):
            details = upstream_error.get("details")
            parsed_details = dict(details) if isinstance(details, dict) else {}
            if upstream_request_id and "request_id" not in parsed_details:
                parsed_details["request_id"] = upstream_request_id
            _raise_app_error(
                code=str(upstream_error.get("code") or "SERVER_PROXY_HTTP_ERROR"),
                message=str(upstream_error.get("message") or f"Upstream server request failed ({exc.code})."),
                status_code=exc.code,
                details=parsed_details,
                retryable=bool(parsed_details.get("retryable")),
            )
        _raise_app_error(
            code="SERVER_PROXY_HTTP_ERROR",
            message=f"Upstream server request failed (http_{exc.code}).",
            status_code=502,
            details={"upstream_status": exc.code, "request_id": upstream_request_id},
            retryable=exc.code >= 500,
        )
    except urllib.error.URLError as exc:
        _raise_app_error(
            code="SERVER_UNAVAILABLE",
            message="Server is unreachable from core.",
            status_code=502,
            details={"cause": str(exc.reason)},
            retryable=True,
        )


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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_runtime_state (
                project_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                workflow_state TEXT NOT NULL,
                pending_prompt TEXT,
                pending_session_id TEXT,
                active_task_type TEXT,
                active_task_request_id TEXT,
                active_task_started_at TEXT,
                event_sequence INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_runtime_user ON project_runtime_state(user_id, updated_at DESC);"
        )
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


def _default_workflow_state(*, has_media: bool) -> str:
    return _WORKFLOW_MEDIA_READY if has_media else _WORKFLOW_PROMPT_INPUT_REQUIRED


def _seed_project_runtime_state(*, project_id: str, user_id: str, workflow_state: str) -> None:
    _db_exec(
        """
        INSERT OR IGNORE INTO project_runtime_state (
            project_id, user_id, workflow_state, pending_prompt, pending_session_id,
            active_task_type, active_task_request_id, active_task_started_at, event_sequence, updated_at
        ) VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, 0, ?)
        """,
        (project_id, user_id, workflow_state, _now_iso()),
    )


def _load_project_runtime_state(project_id: str, user_id: str) -> sqlite3.Row:
    row = _db_fetchone(
        """
        SELECT project_id, user_id, workflow_state, pending_prompt, pending_session_id,
               active_task_type, active_task_request_id, active_task_started_at, event_sequence, updated_at
        FROM project_runtime_state
        WHERE project_id = ? AND user_id = ?
        """,
        (project_id, user_id),
    )
    if row:
        return row
    project = _require_project(project_id, user_id)
    _seed_project_runtime_state(
        project_id=project_id,
        user_id=user_id,
        workflow_state=_default_workflow_state(
            has_media=bool(_list_project_assets(project_id, user_id) or project["source_folder_path"])
        ),
    )
    row = _db_fetchone(
        """
        SELECT project_id, user_id, workflow_state, pending_prompt, pending_session_id,
               active_task_type, active_task_request_id, active_task_started_at, event_sequence, updated_at
        FROM project_runtime_state
        WHERE project_id = ? AND user_id = ?
        """,
        (project_id, user_id),
    )
    if row is None:
        raise RuntimeError("project_runtime_state bootstrap failed")
    return row


def _update_project_runtime_state(
    *,
    project_id: str,
    user_id: str,
    workflow_state: str | object = _UNSET,
    pending_prompt: str | None | object = _UNSET,
    pending_session_id: str | None | object = _UNSET,
    active_task_type: str | None | object = _UNSET,
    active_task_request_id: str | None | object = _UNSET,
    active_task_started_at: str | None | object = _UNSET,
    event_sequence: int | object = _UNSET,
) -> None:
    assignments: list[str] = []
    params: list[Any] = []
    if workflow_state is not _UNSET:
        assignments.append("workflow_state = ?")
        params.append(workflow_state)
    if pending_prompt is not _UNSET:
        assignments.append("pending_prompt = ?")
        params.append(pending_prompt)
    if pending_session_id is not _UNSET:
        assignments.append("pending_session_id = ?")
        params.append(pending_session_id)
    if active_task_type is not _UNSET:
        assignments.append("active_task_type = ?")
        params.append(active_task_type)
    if active_task_request_id is not _UNSET:
        assignments.append("active_task_request_id = ?")
        params.append(active_task_request_id)
    if active_task_started_at is not _UNSET:
        assignments.append("active_task_started_at = ?")
        params.append(active_task_started_at)
    if event_sequence is not _UNSET:
        assignments.append("event_sequence = ?")
        params.append(event_sequence)
    assignments.append("updated_at = ?")
    params.append(_now_iso())
    params.extend((project_id, user_id))
    _db_exec(
        f"""
        UPDATE project_runtime_state
        SET {", ".join(assignments)}
        WHERE project_id = ? AND user_id = ?
        """,
        tuple(params),
    )


def _set_project_workflow_state(
    *,
    project_id: str,
    user_id: str,
    workflow_state: str,
    pending_prompt: str | None | object = _UNSET,
    pending_session_id: str | None | object = _UNSET,
) -> None:
    _load_project_runtime_state(project_id, user_id)
    _update_project_runtime_state(
        project_id=project_id,
        user_id=user_id,
        workflow_state=workflow_state,
        pending_prompt=pending_prompt,
        pending_session_id=pending_session_id,
    )


def _acquire_project_task(*, project_id: str, user_id: str, task_type: str, request_id: str) -> None:
    if task_type not in _ACTIVE_TASK_TYPES:
        raise ValueError(f"unsupported task_type: {task_type}")
    state = _load_project_runtime_state(project_id, user_id)
    active_task_type = state["active_task_type"]
    if active_task_type:
        _raise_app_error(
            code="CORE_PROJECT_BUSY",
            message="Project already has an active task.",
            status_code=409,
            details={
                "project_id": project_id,
                "active_task_type": active_task_type,
                "active_task_request_id": state["active_task_request_id"],
            },
        )
    cursor = _db_exec(
        """
        UPDATE project_runtime_state
        SET active_task_type = ?, active_task_request_id = ?, active_task_started_at = ?, updated_at = ?
        WHERE project_id = ? AND user_id = ? AND (active_task_type IS NULL OR active_task_type = '')
        """,
        (task_type, request_id, _now_iso(), _now_iso(), project_id, user_id),
    )
    if cursor.rowcount <= 0:
        refreshed = _load_project_runtime_state(project_id, user_id)
        _raise_app_error(
            code="CORE_PROJECT_BUSY",
            message="Project already has an active task.",
            status_code=409,
            details={
                "project_id": project_id,
                "active_task_type": refreshed["active_task_type"],
                "active_task_request_id": refreshed["active_task_request_id"],
            },
        )


def _release_project_task(*, project_id: str, user_id: str, task_type: str, request_id: str | None = None) -> None:
    _db_exec(
        """
        UPDATE project_runtime_state
        SET active_task_type = NULL, active_task_request_id = NULL, active_task_started_at = NULL, updated_at = ?
        WHERE project_id = ? AND user_id = ? AND active_task_type = ?
          AND (? IS NULL OR active_task_request_id = ?)
        """,
        (_now_iso(), project_id, user_id, task_type, request_id, request_id),
    )


def _set_project_event_sequence(project_id: str, user_id: str, sequence: int) -> int:
    _load_project_runtime_state(project_id, user_id)
    _update_project_runtime_state(project_id=project_id, user_id=user_id, event_sequence=sequence)
    return sequence


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
    _acquire_project_task(project_id=project_id, user_id=user_id, task_type="ingest", request_id=request_id)
    try:
        _set_project_workflow_state(
            project_id=project_id,
            user_id=user_id,
            workflow_state=_WORKFLOW_MEDIA_PROCESSING,
        )
        job_id = _create_job(
            user_id=user_id,
            project_id=project_id,
            job_type="ingest",
            payload={"project_id": project_id, "user_id": user_id, "request_id": request_id},
            request_id=request_id,
        )
        _enqueue_job(CORE_QUEUE_KEY, job_id)
        return job_id
    except Exception:
        _release_project_task(
            project_id=project_id,
            user_id=user_id,
            task_type="ingest",
            request_id=request_id,
        )
        raise


def _process_ingest_job(job_id: str) -> None:
    """处理 ingest 任务

    使用新的 workflow/repository 架构，替代 legacy 的 _generate_clips_for_assets
    """
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
    request_id = str(payload.get("request_id") or "")

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

        # 使用新的 workflow/repository 架构处理 ingest
        clips = _run_ingest_with_new_workflow(
            project_id=project_id,
            user_id=user_id,
            job_id=job_id,
            asset_rows=asset_rows,
            request_id=request_id,
        )

        _touch_project(
            project_id=project_id,
            user_id=user_id,
            ai_status=f"Analyzed {len(clips)} clips",
            last_ai_edit="Ingest completed",
        )
        runtime_state = _load_project_runtime_state(project_id, user_id)
        next_workflow_state = _WORKFLOW_READY
        if runtime_state["pending_prompt"]:
            next_workflow_state = _WORKFLOW_MEDIA_READY

        # 准备返回结果
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
        _set_project_workflow_state(
            project_id=project_id,
            user_id=user_id,
            workflow_state=next_workflow_state,
        )
    except AppError as exc:
        _set_job_failed(
            job_id,
            error_code=exc.code,
            error_message=exc.message,
            retryable=exc.retryable,
        )
        _set_project_workflow_state(
            project_id=project_id,
            user_id=user_id,
            workflow_state=_WORKFLOW_FAILED,
        )
    except Exception as exc:
        _set_job_failed(
            job_id,
            error_code="CORE_INGEST_FAILED",
            error_message="Ingest job failed unexpectedly.",
            retryable=True,
        )
        _set_project_workflow_state(
            project_id=project_id,
            user_id=user_id,
            workflow_state=_WORKFLOW_FAILED,
        )
        _json_log("ingest_job_crash", job_id=job_id, reason=str(exc))
    finally:
        _release_project_task(
            project_id=project_id,
            user_id=user_id,
            task_type="ingest",
            request_id=request_id or None,
        )


def _run_ingest_with_new_workflow(
    *,
    project_id: str,
    user_id: str,
    job_id: str,
    asset_rows: list[sqlite3.Row],
    request_id: str,
) -> list[_ClipRecord]:
    """使用新的 workflow/repository 架构运行 ingest

    这是主链路接入新实现的核心函数，替代 _generate_clips_for_assets

    Args:
        project_id: 项目ID
        user_id: 用户ID
        job_id: 任务ID
        asset_rows: 资产行数据
        request_id: 请求ID

    Returns:
        生成的片段列表
    """
    import asyncio

    from app.repositories.asset_repository import AssetRepository
    from app.repositories.ingest_state_repository import IngestStateRepository
    from app.tools.ingest_coordinator import IngestCoordinatorTool
    from app.tools.media_scanner import MediaScannerTool
    from app.tools.path_normalizer import PathNormalizerTool

    # 创建 repository 实例（使用全局数据库连接）
    asset_repo = AssetRepository(_DB_CONN, _DB_LOCK)
    state_repo = IngestStateRepository(_DB_CONN, _DB_LOCK)

    # 创建工具实例
    path_normalizer = PathNormalizerTool()
    media_scanner = MediaScannerTool(path_normalizer)
    coordinator = IngestCoordinatorTool()

    # 通知进度开始
    _set_job_progress(job_id, 0.3)

    # 转换资产数据
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

    # 使用新的阶段化处理逻辑
    # 注意：当前是 mock 实现，未来会接入真实的 segmentation/frame extraction 工具
    try:
        # 启动 SCAN 阶段
        coordinator.run("start_phase", phase="scan", total_items=1)
        _set_job_progress(job_id, 0.35)
        coordinator.run("complete_phase", phase="scan")

        # 启动 SEGMENT 阶段（mock）
        coordinator.run("start_phase", phase="segment", total_items=len(assets))
        _set_job_progress(job_id, 0.4)

        # 生成片段（使用 mock 逻辑，保持向后兼容）
        clips = _generate_clips_for_assets(assets)

        # 更新进度
        coordinator.run("update_progress", phase="segment", items_processed=len(assets))
        _set_job_progress(job_id, 0.6)
        coordinator.run("complete_phase", phase="segment")

        # 启动 EXTRACT_FRAMES 阶段（mock）
        coordinator.run("start_phase", phase="extract_frames", total_items=len(assets))
        _set_job_progress(job_id, 0.65)
        coordinator.run("complete_phase", phase="extract_frames")

        # 启动 EMBED 阶段（mock）
        coordinator.run("start_phase", phase="embed", total_items=1)
        _set_job_progress(job_id, 0.75)
        coordinator.run("complete_phase", phase="embed")

        # 启动 INDEX 阶段（mock）
        coordinator.run("start_phase", phase="index", total_items=1)
        _set_job_progress(job_id, 0.85)
        coordinator.run("complete_phase", phase="index")

        # 启动 RENDER 阶段（mock）
        coordinator.run("start_phase", phase="render", total_items=1)
        _set_job_progress(job_id, 0.9)
        coordinator.run("complete_phase", phase="render")

        # 获取总体进度
        progress_result = coordinator.run("get_overall_progress")
        overall_progress = progress_result.payload.get("overall_progress", 1.0)
        _set_job_progress(job_id, overall_progress)

        # 插入片段到数据库（保留原有逻辑）
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

        # 更新 ingest 状态（标记资产为已处理）
        for asset in assets:
            state_repo.mark_phase_completed(
                asset_id=asset.asset_id,
                project_id=project_id,
                user_id=user_id,
                phase="segment",
            )

        _json_log(
            "ingest_workflow_completed",
            job_id=job_id,
            project_id=project_id,
            asset_count=len(assets),
            clip_count=len(clips),
            overall_progress=overall_progress,
        )

        return clips

    except Exception as exc:
        _json_log(
            "ingest_workflow_failed",
            job_id=job_id,
            project_id=project_id,
            error=str(exc),
        )
        # 回退到 legacy 逻辑
        _set_job_progress(job_id, 0.5)
        clips = _generate_clips_for_assets(assets)

        # 插入片段到数据库
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

        return clips


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
        "runtime": {
            "websocket": "/ws/projects/{project_id}",
            "websocket_auth": "query_token",
            "session_resume": True,
            "workflows": ["launchpad", "ingest", "chat", "render"],
            "tools": _CORE_RUNTIME.tool_registry.list_names(),
            "gateways": ["server_proxy", "mock_server_gateway"],
        },
    }


@app.get("/api/v1/runtime/capabilities", response_model=RuntimeCapabilitiesResponse)
def runtime_capabilities() -> RuntimeCapabilitiesResponse:
    return RuntimeCapabilitiesResponse(
        websocket_path="/ws/projects/{project_id}",
        websocket_auth="query_token",
        session_resume=True,
        workflows=["launchpad", "ingest", "chat", "render"],
        tools=_CORE_RUNTIME.tool_registry.list_names(),
        gateways=["server_proxy", "mock_server_gateway"],
    )


@app.websocket("/ws/projects/{project_id}")
async def project_event_stream(websocket: WebSocket, project_id: str) -> None:
    try:
        auth = _get_websocket_auth_context(websocket)
        _require_project(project_id, auth.user_id)
        runtime_state = _load_project_runtime_state(project_id, auth.user_id)
        session_id = websocket.query_params.get("session_id", "").strip() or None
        raw_last_sequence = websocket.query_params.get("last_sequence", "0").strip() or "0"
        last_sequence = int(raw_last_sequence)
    except ValueError:
        await websocket.accept()
        await websocket.send_json(
            CoreEventEnvelope(
                event="notification",
                project_id=project_id,
                payload=NotificationPayload(level="error", message="invalid_last_sequence").model_dump(),
            ).model_dump()
        )
        await websocket.close(code=4400, reason="invalid_last_sequence")
        return
    except AppError as exc:
        await websocket.accept()
        await websocket.send_json(
            CoreEventEnvelope(
                event="notification",
                project_id=project_id,
                payload=NotificationPayload(level="error", message=f"ws_auth_failed:{exc.code}").model_dump(),
            ).model_dump()
        )
        close_code = 4401 if exc.status_code == 401 else 4403
        await websocket.close(code=close_code, reason=exc.code)
        return

    connection_id = await _CORE_RUNTIME.websocket_hub.connect(project_id, websocket)
    try:
        replayed_count = 0
        if last_sequence > 0:
            replayed_count = await _CORE_RUNTIME.websocket_hub.replay(
                project_id,
                websocket,
                after_sequence=last_sequence,
            )
        current_sequence = await _CORE_RUNTIME.websocket_hub.current_sequence(project_id)
        await websocket.send_json(
            CoreEventEnvelope(
                event="session.ready",
                project_id=project_id,
                session_id=session_id,
                sequence=current_sequence,
                payload=CoreSessionReadyPayload(
                    project_id=project_id,
                    connection_id=connection_id,
                    authenticated_user_id=auth.user_id,
                    last_sequence=current_sequence,
                    replayed_count=replayed_count,
                    active_task_type=runtime_state["active_task_type"],
                    workflow_state=runtime_state["workflow_state"],
                ).model_dump(),
            ).model_dump()
        )
        while True:
            message = await websocket.receive_json()
            action = str(message.get("action", "")).strip()
            session_id = str(message.get("session_id", "")).strip() or session_id

            if action == "ping":
                await websocket.send_json(
                    CoreEventEnvelope(
                        event="notification",
                        project_id=project_id,
                        sequence=await _CORE_RUNTIME.websocket_hub.current_sequence(project_id),
                        session_id=session_id,
                        payload=NotificationPayload(level="info", message="pong").model_dump(),
                    ).model_dump()
                )
                continue

            if action == "chat.send":
                prompt = str(message.get("message", "")).strip()
                await _CORE_RUNTIME.workspace_workflow.notify_chat_received(
                    project_id=project_id,
                    message=prompt,
                )
                mock_plan = _CORE_RUNTIME.server_gateway.plan_chat(
                    prompt,
                    project_id=project_id,
                    context={"source": "websocket_shell"},
                )
                summary = str(mock_plan.payload.get("reasoning_summary", "mock_plan_ready"))
                ops = mock_plan.payload.get("ops")
                parsed_ops = ops if isinstance(ops, list) else []
                await _CORE_RUNTIME.workspace_workflow.notify_chat_ready(
                    project_id=project_id,
                    summary=summary,
                    workflow_state=_WORKFLOW_READY,
                )
                await _CORE_RUNTIME.workspace_workflow.notify_patch_ready(
                    project_id=project_id,
                    reasoning_summary=summary,
                    ops=[item for item in parsed_ops if isinstance(item, dict)],
                    turn_id=f"turn_{uuid4().hex[:12]}",
                    workflow_state=_WORKFLOW_READY,
                )
                _update_project_runtime_state(
                    project_id=project_id,
                    user_id=auth.user_id,
                    event_sequence=await _CORE_RUNTIME.websocket_hub.current_sequence(project_id),
                )
                continue

            if action == "launchpad.warmup":
                prompt = str(message.get("prompt", "")).strip()
                warmup = _CORE_RUNTIME.server_gateway.warmup_launchpad(prompt, project_id=project_id)
                summary = str(warmup.payload.get("intent_summary", "launchpad_warmup_ready"))
                await websocket.send_json(
                    CoreEventEnvelope(
                        event="notification",
                        project_id=project_id,
                        sequence=await _CORE_RUNTIME.websocket_hub.current_sequence(project_id),
                        session_id=session_id,
                        payload=NotificationPayload(level="info", message=summary).model_dump(),
                    ).model_dump()
                )
                continue

            await websocket.send_json(
                CoreEventEnvelope(
                    event="notification",
                    project_id=project_id,
                    sequence=await _CORE_RUNTIME.websocket_hub.current_sequence(project_id),
                    session_id=session_id,
                    payload=NotificationPayload(level="warning", message=f"unsupported_action:{action or 'unknown'}").model_dump(),
                ).model_dump()
            )
    except WebSocketDisconnect:
        pass
    finally:
        await _CORE_RUNTIME.websocket_hub.disconnect(project_id, websocket)


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
    runtime_state = _load_project_runtime_state(project_id, auth.user_id)
    assets = _list_project_assets(project_id, auth.user_id)
    clips = _list_project_clips(project_id, auth.user_id)
    return ProjectDetailResponse(
        project_id=record["project_id"],
        title=record["title"],
        ai_status=record["ai_status"],
        last_ai_edit=record["last_ai_edit"],
        workflow_state=runtime_state["workflow_state"],
        active_task_type=runtime_state["active_task_type"],
        pending_prompt=runtime_state["pending_prompt"],
        last_event_sequence=int(runtime_state["event_sequence"] or 0),
        assets=[_asset_to_dto(asset) for asset in assets],
        clips=[_clip_to_dto(clip) for clip in clips],
    )


@app.post("/api/v1/projects", response_model=CreateProjectResponse)
def create_project(
    request: CreateProjectRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> CreateProjectResponse:
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
    _seed_project_runtime_state(
        project_id=project_id,
        user_id=auth.user_id,
        workflow_state=_default_workflow_state(has_media=bool(imported_assets)),
    )
    if imported_assets:
        _insert_assets(imported_assets)
    event_sequence = int(
        _run_sync_coro(
        _CORE_RUNTIME.launchpad_workflow.notify_project_initialized(
            project_id=project_id,
            title=title,
            request_id=_get_request_id(req),
        )
        )
        or 0
    )
    _set_project_event_sequence(project_id, auth.user_id, event_sequence)
    return CreateProjectResponse(project_id=project_id, title=title)


@app.post("/api/v1/projects/import", response_model=CreateProjectResponse)
def import_project(
    request: ImportProjectRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> CreateProjectResponse:
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
    _seed_project_runtime_state(
        project_id=project_id,
        user_id=auth.user_id,
        workflow_state=_default_workflow_state(has_media=bool(assets)),
    )
    if assets:
        _insert_assets(assets)
    event_sequence = int(
        _run_sync_coro(
        _CORE_RUNTIME.launchpad_workflow.notify_project_initialized(
            project_id=project_id,
            title=title,
            request_id=_get_request_id(req),
        )
        )
        or 0
    )
    _set_project_event_sequence(project_id, auth.user_id, event_sequence)
    return CreateProjectResponse(project_id=project_id, title=title)


@app.post("/api/v1/projects/upload", response_model=CreateProjectResponse)
async def upload_project(
    req: Request,
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
    _seed_project_runtime_state(
        project_id=project_id,
        user_id=auth.user_id,
        workflow_state=_default_workflow_state(has_media=bool(assets)),
    )
    _insert_assets(assets)

    for file in files:
        await file.close()

    event_sequence = await _CORE_RUNTIME.launchpad_workflow.notify_project_initialized(
        project_id=project_id,
        title=normalized_title,
        request_id=_get_request_id(req),
    )
    _set_project_event_sequence(project_id, auth.user_id, int(event_sequence or 0))
    return CreateProjectResponse(project_id=project_id, title=normalized_title)


@app.post("/api/v1/projects/{project_id}/assets/import", response_model=AddAssetsResponse)
def add_assets_from_folder(
    project_id: str,
    request: AddAssetsRequest,
    req: Request,
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
    _set_project_workflow_state(
        project_id=project_id,
        user_id=auth.user_id,
        workflow_state=_WORKFLOW_MEDIA_READY,
    )
    event_sequence = int(
        _run_sync_coro(
        _CORE_RUNTIME.launchpad_workflow.notify_media_progress(
            project_id=project_id,
            stage="scan",
            progress=0.2,
            message="folder_assets_linked",
            request_id=_get_request_id(req),
        )
        )
        or 0
    )
    _set_project_event_sequence(project_id, auth.user_id, event_sequence)
    return AddAssetsResponse(project_id=project_id, added_count=inserted, total_assets=total_assets)


@app.post("/api/v1/projects/{project_id}/assets/upload", response_model=AddAssetsResponse)
async def add_assets_from_upload(
    project_id: str,
    req: Request,
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
    _set_project_workflow_state(
        project_id=project_id,
        user_id=auth.user_id,
        workflow_state=_WORKFLOW_MEDIA_READY,
    )
    for file in files:
        await file.close()
    event_sequence = await _CORE_RUNTIME.launchpad_workflow.notify_media_progress(
        project_id=project_id,
        stage="scan",
        progress=0.2,
        message="uploaded_assets_linked",
        request_id=_get_request_id(req),
    )
    _set_project_event_sequence(project_id, auth.user_id, int(event_sequence or 0))
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
    response = IngestResponse.model_validate(json.loads(result_json))
    event_sequence = int(
        _run_sync_coro(
        _CORE_RUNTIME.launchpad_workflow.notify_media_completed(
            project_id=request.project_id,
            message="ingest_completed",
            request_id=_get_request_id(req),
        )
        )
        or 0
    )
    _set_project_event_sequence(request.project_id, auth.user_id, event_sequence)
    return response


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
    request_id = str(row["request_id"] or f"req_{uuid4().hex[:12]}")
    if row["job_type"] == "ingest":
        _acquire_project_task(
            project_id=row["project_id"],
            user_id=auth.user_id,
            task_type="ingest",
            request_id=request_id,
        )
        _set_project_workflow_state(
            project_id=row["project_id"],
            user_id=auth.user_id,
            workflow_state=_WORKFLOW_MEDIA_PROCESSING,
        )
    _db_exec(
        """
        UPDATE jobs
        SET status = 'queued', progress = 0.0, error_code = NULL, error_message = NULL, updated_at = ?
        WHERE job_id = ? AND user_id = ?
        """,
        (_now_iso(), job_id, auth.user_id),
    )
    try:
        _enqueue_job(CORE_QUEUE_KEY, job_id)
    except Exception:
        if row["job_type"] == "ingest":
            _release_project_task(
                project_id=row["project_id"],
                user_id=auth.user_id,
                task_type="ingest",
                request_id=request_id,
            )
        raise
    return RetryJobResponse(
        job_id=job_id,
        status="queued",
        project_id=row["project_id"],
        job_type=row["job_type"],
    )


@app.post("/api/v1/index/upsert-clips")
def proxy_index_upsert(
    request: IndexUpsertRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _require_project(request.project_id, auth.user_id)
    request_id = _get_request_id(req)
    _acquire_project_task(project_id=request.project_id, user_id=auth.user_id, task_type="index", request_id=request_id)
    try:
        response = _proxy_server_json(
            path="/api/v1/index/upsert-clips",
            payload=request.model_dump(),
            request=req,
        )
        indexed = response.get("indexed")
        _touch_project(
            project_id=request.project_id,
            user_id=auth.user_id,
            ai_status=f"Indexed {indexed or 0} clips",
            last_ai_edit="Clip index updated",
        )
        _set_project_workflow_state(
            project_id=request.project_id,
            user_id=auth.user_id,
            workflow_state=_WORKFLOW_READY,
        )
        event_sequence = int(
            _run_sync_coro(
            _CORE_RUNTIME.launchpad_workflow.notify_media_progress(
                project_id=request.project_id,
                stage="index",
                progress=1.0,
                message=f"index_upsert_completed:{indexed}",
                request_id=request_id,
            )
            )
            or 0
        )
        _set_project_event_sequence(request.project_id, auth.user_id, event_sequence)
        return response
    except AppError:
        _set_project_workflow_state(
            project_id=request.project_id,
            user_id=auth.user_id,
            workflow_state=_WORKFLOW_FAILED,
        )
        raise
    finally:
        _release_project_task(
            project_id=request.project_id,
            user_id=auth.user_id,
            task_type="index",
            request_id=request_id,
        )


@app.post("/api/v1/chat")
def proxy_chat(
    request: ChatRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    _require_project(request.project_id, auth.user_id)
    request_id = _get_request_id(req)
    asset_count = len(_list_project_assets(request.project_id, auth.user_id))
    clip_count = len(_list_project_clips(request.project_id, auth.user_id))
    runtime_state = _load_project_runtime_state(request.project_id, auth.user_id)

    _acquire_project_task(project_id=request.project_id, user_id=auth.user_id, task_type="chat", request_id=request_id)
    _set_project_workflow_state(
        project_id=request.project_id,
        user_id=auth.user_id,
        workflow_state=_WORKFLOW_CHAT_THINKING,
    )
    try:
        engineered = _CORE_RUNTIME.context_engineering.build_chat_request(
            prompt=request.message,
            project_id=request.project_id,
            user_id=auth.user_id,
            client_context=request.context,
            runtime_state={
                "workflow_state": runtime_state["workflow_state"],
                "active_task_type": runtime_state["active_task_type"],
                "pending_prompt": runtime_state["pending_prompt"],
            },
            asset_count=asset_count,
            clip_count=clip_count,
            current_project=request.current_project,
        )
        _run_sync_coro(
            _CORE_RUNTIME.workspace_workflow.notify_chat_received(
                project_id=request.project_id,
                message=request.message,
                request_id=request_id,
            )
        )
        response = _proxy_server_json(
            path="/api/v1/chat",
            payload={
                **request.model_dump(exclude_none=True),
                "message": engineered.prompt,
                "user_id": auth.user_id,
                "context": engineered.context,
            },
            request=req,
        )
        reasoning_summary = str(response.get("reasoning_summary", "chat_ready"))
        ops = response.get("ops")
        parsed_ops = ops if isinstance(ops, list) else []
        decision_type = str(response.get("decision_type") or "UPDATE_PROJECT_CONTRACT")
        next_workflow_state = _WORKFLOW_AWAITING_MEDIA if engineered.requires_media else _WORKFLOW_READY
        if decision_type == "ASK_USER_CLARIFICATION" and engineered.requires_media:
            _touch_project(
                project_id=request.project_id,
                user_id=auth.user_id,
                ai_status="Awaiting media upload",
                last_ai_edit="Prompt requires media",
            )
            _set_project_workflow_state(
                project_id=request.project_id,
                user_id=auth.user_id,
                workflow_state=_WORKFLOW_AWAITING_MEDIA,
                pending_prompt=None,
                pending_session_id=request.session_id,
            )
        else:
            _touch_project(
                project_id=request.project_id,
                user_id=auth.user_id,
                ai_status="AI ready",
                last_ai_edit="Chat response prepared",
            )
            _set_project_workflow_state(
                project_id=request.project_id,
                user_id=auth.user_id,
                workflow_state=next_workflow_state,
                pending_prompt=None,
                pending_session_id=request.session_id if engineered.requires_media else None,
            )
        chat_ready_sequence = int(
            _run_sync_coro(
            _CORE_RUNTIME.workspace_workflow.notify_chat_ready(
                project_id=request.project_id,
                summary=reasoning_summary,
                workflow_state=next_workflow_state,
                request_id=request_id,
            )
            )
            or 0
        )
        patch_sequence = int(
            _run_sync_coro(
            _CORE_RUNTIME.workspace_workflow.notify_patch_ready(
                project_id=request.project_id,
                reasoning_summary=reasoning_summary,
                ops=[item for item in parsed_ops if isinstance(item, dict)],
                turn_id=f"turn_{request_id}",
                decision_type=decision_type,
                workflow_state=next_workflow_state,
                request_id=request_id,
            )
            )
            or 0
        )
        current_sequence = _set_project_event_sequence(
            request.project_id,
            auth.user_id,
            max(chat_ready_sequence, patch_sequence),
        )
        meta = dict(response.get("meta") or {})
        meta["core_request_id"] = request_id
        meta["core_event_sequence"] = current_sequence
        meta["interaction_mode"] = engineered.interaction_mode
        response["meta"] = meta
        return response
    except AppError:
        _set_project_workflow_state(
            project_id=request.project_id,
            user_id=auth.user_id,
            workflow_state=_WORKFLOW_FAILED,
        )
        raise
    finally:
        _release_project_task(
            project_id=request.project_id,
            user_id=auth.user_id,
            task_type="chat",
            request_id=request_id,
        )


@app.post("/api/v1/search")
def search(
    request: SearchRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    project_id = request.project_id.strip()
    query = request.query.strip()
    if not project_id:
        _raise_app_error(
            code="CORE_SEARCH_PROJECT_ID_REQUIRED",
            message="project_id is required.",
            status_code=400,
        )
    if not query:
        _raise_app_error(
            code="CORE_SEARCH_QUERY_REQUIRED",
            message="query is required.",
            status_code=400,
        )
    _require_project(project_id, auth.user_id)
    return _proxy_server_json(
        path="/api/v1/search",
        payload={
            "project_id": project_id,
            "query": query,
            "top_k": request.top_k,
        },
        request=req,
    )


@app.post("/api/v1/render")
def render(
    request: RenderRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> dict[str, Any]:
    project = dict(request.project)
    project_id = str(project.get("project_id") or "").strip()
    if not project_id:
        _raise_app_error(
            code="CORE_RENDER_PROJECT_ID_REQUIRED",
            message="project.project_id is required.",
            status_code=400,
        )
    _require_project(project_id, auth.user_id)
    request_id = _get_request_id(req)
    render_type = str(project.get("render_type") or "preview").strip() or "preview"
    _acquire_project_task(project_id=project_id, user_id=auth.user_id, task_type="render", request_id=request_id)
    _set_project_workflow_state(
        project_id=project_id,
        user_id=auth.user_id,
        workflow_state=_WORKFLOW_RENDERING,
    )
    try:
        render_kwargs: dict[str, Any]
        if render_type == "export":
            render_kwargs = {
                "format": str(project.get("format") or project.get("export_format") or "mp4"),
                "resolution": str(project.get("resolution") or project.get("export_resolution") or "original"),
                "codec": str(project.get("codec") or project.get("export_codec") or "h264"),
                "output_path": project.get("output_path"),
            }
        else:
            render_kwargs = {
                "quality": str(project.get("preview_quality") or "low"),
                "format": str(project.get("format") or project.get("preview_format") or "webm"),
            }
        result = _run_sync_coro(
            _CORE_RUNTIME.render_workflow.render(
                project_id=project_id,
                timeline_json=project,
                render_type=render_type,
                request_id=request_id,
                **render_kwargs,
            )
        )
        current_sequence = int(_run_sync_coro(_CORE_RUNTIME.websocket_hub.current_sequence(project_id)) or 0)
        _set_project_event_sequence(project_id, auth.user_id, current_sequence)
        _touch_project(
            project_id=project_id,
            user_id=auth.user_id,
            ai_status=f"{render_type.capitalize()} ready",
            last_ai_edit=f"{render_type.capitalize()} render completed",
        )
        _set_project_workflow_state(
            project_id=project_id,
            user_id=auth.user_id,
            workflow_state=_WORKFLOW_READY,
        )
        return result
    except AppError:
        _set_project_workflow_state(
            project_id=project_id,
            user_id=auth.user_id,
            workflow_state=_WORKFLOW_FAILED,
        )
        raise
    except Exception as exc:
        _set_project_workflow_state(
            project_id=project_id,
            user_id=auth.user_id,
            workflow_state=_WORKFLOW_FAILED,
        )
        _raise_app_error(
            code="CORE_RENDER_FAILED",
            message="Render failed unexpectedly.",
            status_code=500,
            details={"cause": str(exc), "project_id": project_id},
            retryable=True,
        )
    finally:
        _release_project_task(
            project_id=project_id,
            user_id=auth.user_id,
            task_type="render",
            request_id=request_id,
        )
