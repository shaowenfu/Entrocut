from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

import jwt
import redis
from fastapi import Depends, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

APP_VERSION = "0.3.0"
CONTRACT_VERSION = "1.0.0"
REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
SERVER_INDEX_QUEUE_KEY = os.getenv("SERVER_INDEX_QUEUE_KEY", "entrocut:server:index")
SERVER_CHAT_QUEUE_KEY = os.getenv("SERVER_CHAT_QUEUE_KEY", "entrocut:server:chat")
SERVER_JOB_WAIT_TIMEOUT_SEC = float(os.getenv("SERVER_JOB_WAIT_TIMEOUT_SEC", "20"))
SERVER_DB_PATH = os.getenv("SERVER_DB_PATH", os.path.join(os.path.dirname(__file__), "server.db"))
AUTH_JWT_ALGORITHM = os.getenv("AUTH_JWT_ALGORITHM", "HS256")
AUTH_JWT_SECRET = os.getenv("AUTH_JWT_SECRET", "").strip()
AUTH_JWT_PUBLIC_KEY = os.getenv("AUTH_JWT_PUBLIC_KEY", "").strip()

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("entrocut.server")

app = FastAPI(
    title="Entrocut Server",
    version=APP_VERSION,
    description="Cloud Orchestration Service（云端编排服务）",
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


class ClipPayload(BaseModel):
    clip_id: str
    asset_id: str
    start_ms: int
    end_ms: int
    score: float
    description: str


class IndexUpsertRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    clips: list[ClipPayload] = Field(default_factory=list, description="Clip payload（片段负载）")


class IndexUpsertResponse(BaseModel):
    ok: bool = True
    request_id: str
    indexed: int
    failed: int


class StoryboardScene(BaseModel):
    id: str
    title: str
    duration: str
    intent: str


class AgentOperation(BaseModel):
    op: str
    target_item_id: str | None = None
    new_clip_id: str | None = None
    note: str | None = None


class TimelineFilters(BaseModel):
    speed: float = 1.0
    volume_db: float = 0.0


class TimelineItem(BaseModel):
    item_id: str
    source_clip_id: str
    timeline_start_ms: int
    source_in_ms: int
    source_out_ms: int
    filters: TimelineFilters
    reasoning: str


class TimelineTrack(BaseModel):
    track_id: str
    track_type: Literal["video", "audio"]
    items: list[TimelineItem]


class Timeline(BaseModel):
    tracks: list[TimelineTrack]


class ContractAsset(BaseModel):
    asset_id: str
    file_path: str
    duration_ms: int


class ContractClip(BaseModel):
    clip_id: str
    asset_id: str
    start_ms: int
    end_ms: int
    embedding_ref: str


class EntroVideoProject(BaseModel):
    contract_version: str = CONTRACT_VERSION
    project_id: str
    user_id: str
    updated_at: str
    assets: list[ContractAsset]
    clip_pool: list[ContractClip]
    timeline: Timeline
    reasoning_summary: str


class PatchPayload(BaseModel):
    patch_version: str = CONTRACT_VERSION
    operations: list[AgentOperation]


DecisionType = Literal["UPDATE_PROJECT_CONTRACT", "APPLY_PATCH_ONLY", "ASK_USER_CLARIFICATION"]


class ChatRequest(BaseModel):
    project_id: str = Field(..., description="Project ID（项目标识）")
    session_id: str | None = Field(default=None, description="Session ID（会话标识）")
    user_id: str | None = Field(default=None, description="User ID（用户标识）")
    message: str = Field(..., description="User prompt（用户输入）")
    context: dict[str, Any] | None = Field(default=None, description="Context payload（上下文）")
    current_project: dict[str, Any] | None = Field(
        default=None, description="Current project contract（当前项目契约）"
    )


class ChatDecisionResponse(BaseModel):
    decision_type: DecisionType
    project: EntroVideoProject | None = None
    patch: PatchPayload | None = None
    project_id: str
    reasoning_summary: str
    ops: list[AgentOperation]
    storyboard_scenes: list[StoryboardScene] = Field(default_factory=list)
    meta: dict[str, Any]


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


def _json_log(event: str, **kwargs: Any) -> None:
    logger.info(json.dumps({"event": event, "ts": _now_iso(), **kwargs}, ensure_ascii=False))


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", f"req_{uuid4().hex[:12]}")


def _error_response(
    *,
    request_id: str,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, Any] | None = None,
    retryable: bool = False,
) -> JSONResponse:
    merged = {"request_id": request_id, "retryable": retryable}
    if details:
        merged.update(details)
    return JSONResponse(
        status_code=status_code,
        content=ErrorEnvelope(error=ErrorDetail(code=code, message=message, details=merged)).model_dump(),
        headers={"X-Request-ID": request_id},
    )


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
    rid = request.headers.get("x-request-id", "").strip() or f"req_{uuid4().hex[:12]}"
    request.state.request_id = rid
    started = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
    except Exception:
        latency_ms = round((time.perf_counter() - started) * 1000, 2)
        _json_log(
            "http_request",
            request_id=rid,
            method=request.method,
            path=request.url.path,
            latency_ms=latency_ms,
            status_code=500,
        )
        raise
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    _json_log(
        "http_request",
        request_id=rid,
        method=request.method,
        path=request.url.path,
        latency_ms=latency_ms,
        status_code=response.status_code,
    )
    response.headers["X-Request-ID"] = rid
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return _error_response(
        request_id=_request_id(request),
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
        retryable=exc.retryable,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    return _error_response(
        request_id=_request_id(request),
        code="SERVER_REQUEST_INVALID",
        message="Request payload is invalid.",
        status_code=422,
        details={"errors": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    _json_log("unhandled_error", request_id=_request_id(request), error_type=type(exc).__name__, message=str(exc))
    return _error_response(
        request_id=_request_id(request),
        code="SERVER_INTERNAL_ERROR",
        message="Unexpected server error.",
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
        _raise_app_error(code="SERVER_AUTH_UNAUTHORIZED", message="Missing Authorization header.", status_code=401)
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        _raise_app_error(
            code="SERVER_AUTH_UNAUTHORIZED",
            message="Authorization header must use Bearer token.",
            status_code=401,
        )
    token = authorization[len(prefix) :].strip()
    if not token:
        _raise_app_error(code="SERVER_AUTH_UNAUTHORIZED", message="Bearer token is empty.", status_code=401)
    try:
        payload = jwt.decode(
            token,
            key=_jwt_verify_key(),
            algorithms=[AUTH_JWT_ALGORITHM],
            options={"verify_aud": False},
        )
    except jwt.ExpiredSignatureError:
        _raise_app_error(code="SERVER_AUTH_UNAUTHORIZED", message="Token expired.", status_code=401)
    except jwt.InvalidTokenError:
        _raise_app_error(code="SERVER_AUTH_UNAUTHORIZED", message="Invalid token.", status_code=401)

    user_id = str(payload.get("sub", "")).strip()
    if not user_id:
        _raise_app_error(code="SERVER_AUTH_UNAUTHORIZED", message="Token claim sub is required.", status_code=401)
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


def _db_fetchone(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    db = _get_db()
    with _DB_LOCK:
        cursor = db.execute(query, params)
        return cursor.fetchone()


def _db_fetchall(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    db = _get_db()
    with _DB_LOCK:
        cursor = db.execute(query, params)
        return cursor.fetchall()


def _init_db() -> None:
    global _DB_CONN
    db_path = os.path.abspath(SERVER_DB_PATH)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS indexed_clips (
                user_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                clip_id TEXT NOT NULL,
                asset_id TEXT NOT NULL,
                start_ms INTEGER NOT NULL,
                end_ms INTEGER NOT NULL,
                score REAL NOT NULL,
                description TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, project_id, clip_id)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_indexed_clips_project ON indexed_clips(user_id, project_id);")
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_project ON jobs(user_id, project_id, updated_at DESC);")
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
            code="SERVER_QUEUE_UNAVAILABLE",
            message="Redis queue is unavailable.",
            status_code=503,
            details={"redis_url": REDIS_URL},
            retryable=True,
        )
    return _REDIS_CLIENT


def _new_job_id() -> str:
    return f"job_{uuid4().hex[:10]}"


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
            code="SERVER_JOB_NOT_FOUND",
            message="job_id not found.",
            status_code=404,
            details={"job_id": job_id},
        )
    return row


def _job_status_response(row: sqlite3.Row) -> JobStatusResponse:
    return JobStatusResponse(
        job_id=row["job_id"],
        project_id=row["project_id"],
        job_type=row["job_type"],
        status=row["status"],
        progress=float(row["progress"]),
        retryable=bool(row["retryable"]),
        error_code=row["error_code"],
        error_message=row["error_message"],
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        updated_at=row["updated_at"],
    )


def _set_job_running(job_id: str) -> None:
    _db_exec(
        "UPDATE jobs SET status = 'running', progress = 0.1, updated_at = ? WHERE job_id = ?",
        (_now_iso(), job_id),
    )


def _set_job_progress(job_id: str, progress: float) -> None:
    _db_exec(
        "UPDATE jobs SET progress = ?, updated_at = ? WHERE job_id = ?",
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


def _set_job_failed(job_id: str, *, error_code: str, error_message: str, retryable: bool) -> None:
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
            error_code="SERVER_QUEUE_ENQUEUE_FAILED",
            error_message="Failed to enqueue job.",
            retryable=True,
        )
        _raise_app_error(
            code="SERVER_QUEUE_ENQUEUE_FAILED",
            message="Failed to enqueue job.",
            status_code=503,
            details={"job_id": job_id, "reason": str(exc)},
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
        code="SERVER_JOB_TIMEOUT",
        message="Job timed out.",
        status_code=504,
        details={"job_id": job_id},
        retryable=True,
    )
    raise RuntimeError("unreachable")


def _scene(scene_id: str, title: str, duration: str, intent: str) -> StoryboardScene:
    return StoryboardScene(id=scene_id, title=title, duration=duration, intent=intent)


def _list_indexed_clips(user_id: str, project_id: str, limit: int = 8) -> list[sqlite3.Row]:
    return _db_fetchall(
        """
        SELECT clip_id, asset_id, start_ms, end_ms, score, description
        FROM indexed_clips
        WHERE user_id = ? AND project_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, project_id, limit),
    )


def _build_contract(
    *,
    user_id: str,
    project_id: str,
    reasoning_summary: str,
    clips: list[sqlite3.Row],
) -> EntroVideoProject:
    if clips:
        timeline_items = [
            TimelineItem(
                item_id=f"item_{idx + 1}",
                source_clip_id=clip["clip_id"],
                timeline_start_ms=idx * 3000,
                source_in_ms=0,
                source_out_ms=max(800, int(clip["end_ms"]) - int(clip["start_ms"])),
                filters=TimelineFilters(speed=1.0, volume_db=0.0),
                reasoning=f"Clip {clip['clip_id']} 匹配当前语义与节奏。",
            )
            for idx, clip in enumerate(clips[:4])
        ]
    else:
        timeline_items = []

    timeline = Timeline(
        tracks=[
            TimelineTrack(track_id="v1", track_type="video", items=timeline_items),
        ]
    )
    contract_assets: list[ContractAsset] = []
    clip_pool = [
        ContractClip(
            clip_id=clip["clip_id"],
            asset_id=clip["asset_id"],
            start_ms=int(clip["start_ms"]),
            end_ms=int(clip["end_ms"]),
            embedding_ref=f"vec_{clip['clip_id']}",
        )
        for clip in clips
    ]
    return EntroVideoProject(
        project_id=project_id,
        user_id=user_id,
        updated_at=_now_iso(),
        assets=contract_assets,
        clip_pool=clip_pool,
        timeline=timeline,
        reasoning_summary=reasoning_summary,
    )


def _run_index_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    user_id = payload["user_id"]
    project_id = payload["project_id"]
    clips = payload["clips"]
    indexed = 0
    failed = 0
    for clip in clips:
        try:
            _db_exec(
                """
                INSERT INTO indexed_clips (
                    user_id, project_id, clip_id, asset_id, start_ms, end_ms, score, description, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, project_id, clip_id) DO UPDATE SET
                    asset_id = excluded.asset_id,
                    start_ms = excluded.start_ms,
                    end_ms = excluded.end_ms,
                    score = excluded.score,
                    description = excluded.description
                """,
                (
                    user_id,
                    project_id,
                    clip["clip_id"],
                    clip["asset_id"],
                    int(clip["start_ms"]),
                    int(clip["end_ms"]),
                    float(clip["score"]),
                    clip["description"],
                    _now_iso(),
                ),
            )
            indexed += 1
        except Exception:
            failed += 1
    return IndexUpsertResponse(
        request_id=payload["request_id"],
        indexed=indexed,
        failed=failed,
    ).model_dump()


def _run_chat_job(job_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    user_id = payload["user_id"]
    project_id = payload["project_id"]
    message = str(payload["message"]).strip()
    has_media = bool((payload.get("context") or {}).get("has_media"))
    clip_count = int((payload.get("context") or {}).get("clip_count") or 0)
    request_id = payload["request_id"]
    latency_ms = 1200 if has_media else 600

    if not message:
        _raise_app_error(
            code="SERVER_CHAT_CONTEXT_INVALID",
            message="message is required.",
            status_code=400,
        )

    if not has_media:
        reasoning = "当前项目没有可用素材，请先上传视频再继续剪辑。"
        response = ChatDecisionResponse(
            decision_type="ASK_USER_CLARIFICATION",
            project=_build_contract(
                user_id=user_id,
                project_id=project_id,
                reasoning_summary=reasoning,
                clips=[],
            ),
            patch=PatchPayload(
                operations=[
                    AgentOperation(op="request_user_upload", note="请先上传至少一个视频素材。"),
                ]
            ),
            project_id=project_id,
            reasoning_summary=reasoning,
            ops=[
                AgentOperation(op="open_assets_panel", note="Open Assets panel"),
                AgentOperation(op="upload_videos", note="Upload local videos"),
                AgentOperation(op="retry_prompt", note="Retry the same prompt"),
            ],
            storyboard_scenes=[],
            meta={
                "request_id": request_id,
                "latency_ms": latency_ms,
                "session_id": payload.get("session_id"),
            },
        )
        return response.model_dump()

    lower = message.lower()
    if "slow" in lower or "慢" in message:
        scenes = [
            _scene("scene_1", "Calm Establishing", "6s", "Slow pan for atmosphere"),
            _scene("scene_2", "Subject Focus", "8s", "Longer hold to keep pace calm"),
            _scene("scene_3", "Breathing Detail", "5s", "Insert detail shots for rhythm"),
        ]
    else:
        scenes = [
            _scene("scene_1", "Fast Establishing", "4s", "Quick establish with movement"),
            _scene("scene_2", "Hero Reveal", "6s", "Cut to subject with strong visual anchor"),
            _scene("scene_3", "Momentum Push", "5s", "Increase cadence before transition"),
        ]

    indexed_clips = _list_indexed_clips(user_id, project_id)
    reasoning = "我已根据当前素材和你的指令生成一版可继续迭代的分镜方案。"
    contract = _build_contract(
        user_id=user_id,
        project_id=project_id,
        reasoning_summary=reasoning,
        clips=indexed_clips,
    )
    ops = [
        AgentOperation(
            op="replace_timeline_item",
            target_item_id="item_1",
            new_clip_id=indexed_clips[0]["clip_id"] if indexed_clips else None,
            note="对齐首镜头节奏与主意图。",
        ),
        AgentOperation(
            op="set_project_pacing",
            note="根据提示词设置节奏策略。",
        ),
    ]
    response = ChatDecisionResponse(
        decision_type="UPDATE_PROJECT_CONTRACT",
        project=contract,
        patch=None,
        project_id=project_id,
        reasoning_summary=reasoning,
        ops=ops,
        storyboard_scenes=scenes,
        meta={
            "request_id": request_id,
            "latency_ms": latency_ms,
            "session_id": payload.get("session_id"),
            "used_clip_count": max(clip_count, len(indexed_clips)),
            "queued_at": _now_iso(),
        },
    )
    return response.model_dump()


def _process_job(job_id: str, queue_key: str) -> None:
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
    try:
        _set_job_running(job_id)
        _set_job_progress(job_id, 0.3)
        if queue_key == SERVER_INDEX_QUEUE_KEY:
            result = _run_index_job(job_id, payload)
        elif queue_key == SERVER_CHAT_QUEUE_KEY:
            result = _run_chat_job(job_id, payload)
        else:
            _raise_app_error(
                code="SERVER_QUEUE_UNKNOWN",
                message="Unknown queue key.",
                status_code=500,
                details={"queue_key": queue_key},
            )
        _set_job_progress(job_id, 0.9)
        _set_job_success(job_id, result)
    except AppError as exc:
        _set_job_failed(
            job_id,
            error_code=exc.code,
            error_message=exc.message,
            retryable=exc.retryable,
        )
    except Exception as exc:
        _json_log("job_crash", job_id=job_id, queue_key=queue_key, reason=str(exc))
        _set_job_failed(
            job_id,
            error_code="SERVER_JOB_FAILED",
            error_message="Job failed unexpectedly.",
            retryable=True,
        )


def _worker_loop() -> None:
    _WORKER_READY.set()
    while not _WORKER_STOP.is_set():
        if _REDIS_CLIENT is None:
            time.sleep(1.0)
            continue
        handled = False
        try:
            index_item = _REDIS_CLIENT.brpop(SERVER_INDEX_QUEUE_KEY, timeout=1)
            if index_item:
                handled = True
                _, job_id = index_item
                _process_job(job_id, SERVER_INDEX_QUEUE_KEY)
        except Exception as exc:
            _json_log("worker_index_error", reason=str(exc))
            time.sleep(0.5)
        if handled:
            continue
        try:
            chat_item = _REDIS_CLIENT.brpop(SERVER_CHAT_QUEUE_KEY, timeout=1)
            if chat_item:
                _, job_id = chat_item
                _process_job(job_id, SERVER_CHAT_QUEUE_KEY)
        except Exception as exc:
            _json_log("worker_chat_error", reason=str(exc))
            time.sleep(0.5)


def _enqueue_index_job(request: IndexUpsertRequest, auth: AuthContext, req: Request) -> str:
    if not request.project_id.strip():
        _raise_app_error(
            code="SERVER_VECTOR_UPSERT_FAILED",
            message="project_id is required.",
            status_code=400,
        )
    job_id = _create_job(
        user_id=auth.user_id,
        project_id=request.project_id.strip(),
        job_type="index_upsert",
        payload={
            "request_id": _request_id(req),
            "project_id": request.project_id.strip(),
            "user_id": auth.user_id,
            "clips": [clip.model_dump() for clip in request.clips],
        },
        request_id=_request_id(req),
    )
    _enqueue_job(SERVER_INDEX_QUEUE_KEY, job_id)
    return job_id


def _enqueue_chat_job(request: ChatRequest, auth: AuthContext, req: Request) -> str:
    message = request.message.strip()
    if not message:
        _raise_app_error(
            code="SERVER_CHAT_CONTEXT_INVALID",
            message="message is required.",
            status_code=400,
        )
    job_id = _create_job(
        user_id=auth.user_id,
        project_id=request.project_id.strip(),
        job_type="chat",
        payload={
            "request_id": _request_id(req),
            "project_id": request.project_id.strip(),
            "user_id": auth.user_id,
            "session_id": request.session_id,
            "message": message,
            "context": request.context or {},
            "current_project": request.current_project or {},
        },
        request_id=_request_id(req),
    )
    _enqueue_job(SERVER_CHAT_QUEUE_KEY, job_id)
    return job_id


@app.on_event("startup")
def on_startup() -> None:
    global _WORKER_THREAD
    _init_db()
    _init_redis()
    _WORKER_STOP.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, name="server-job-worker", daemon=True)
    _WORKER_THREAD.start()
    _WORKER_READY.wait(timeout=2)
    _json_log("server_started", version=APP_VERSION, db_path=os.path.abspath(SERVER_DB_PATH), redis_url=REDIS_URL)


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
        "service": "server",
        "version": APP_VERSION,
        "queue": {
            "backend": "redis",
            "redis_url": REDIS_URL,
            "ready": redis_ok,
        },
        "storage": {
            "backend": "sqlite",
            "db_path": os.path.abspath(SERVER_DB_PATH),
        },
    }


@app.post("/api/v1/index/jobs", response_model=JobAcceptedResponse)
def create_index_job(
    request: IndexUpsertRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> JobAcceptedResponse:
    job_id = _enqueue_index_job(request, auth, req)
    return JobAcceptedResponse(
        job_id=job_id,
        status="queued",
        project_id=request.project_id,
        job_type="index_upsert",
        retryable=True,
    )


@app.post("/api/v1/chat/jobs", response_model=JobAcceptedResponse)
def create_chat_job(
    request: ChatRequest,
    req: Request,
    auth: AuthContext = Depends(get_auth_context),
) -> JobAcceptedResponse:
    job_id = _enqueue_chat_job(request, auth, req)
    return JobAcceptedResponse(
        job_id=job_id,
        status="queued",
        project_id=request.project_id,
        job_type="chat",
        retryable=True,
    )


@app.post("/api/v1/index/upsert-clips", response_model=IndexUpsertResponse)
def index_upsert(request: IndexUpsertRequest, req: Request, auth: AuthContext = Depends(get_auth_context)) -> IndexUpsertResponse:
    job_id = _enqueue_index_job(request, auth, req)
    row = _wait_job_completion(job_id=job_id, user_id=auth.user_id, timeout_sec=SERVER_JOB_WAIT_TIMEOUT_SEC)
    if row["status"] == "failed":
        _raise_app_error(
            code=row["error_code"] or "SERVER_VECTOR_UPSERT_FAILED",
            message=row["error_message"] or "Vector upsert failed.",
            status_code=400,
            details={"job_id": job_id},
            retryable=bool(row["retryable"]),
        )
    result_json = row["result_json"]
    if not result_json:
        _raise_app_error(
            code="SERVER_JOB_RESULT_MISSING",
            message="Job result is empty.",
            status_code=500,
            details={"job_id": job_id},
            retryable=True,
        )
    return IndexUpsertResponse.model_validate(json.loads(result_json))


@app.post("/api/v1/chat", response_model=ChatDecisionResponse)
def chat(request: ChatRequest, req: Request, auth: AuthContext = Depends(get_auth_context)) -> ChatDecisionResponse:
    if request.user_id and request.user_id != auth.user_id:
        _raise_app_error(
            code="SERVER_CHAT_CONTEXT_INVALID",
            message="user_id mismatch with token subject.",
            status_code=400,
        )
    job_id = _enqueue_chat_job(request, auth, req)
    row = _wait_job_completion(job_id=job_id, user_id=auth.user_id, timeout_sec=SERVER_JOB_WAIT_TIMEOUT_SEC)
    if row["status"] == "failed":
        _raise_app_error(
            code=row["error_code"] or "SERVER_CHAT_FAILED",
            message=row["error_message"] or "Chat failed.",
            status_code=400,
            details={"job_id": job_id},
            retryable=bool(row["retryable"]),
        )
    result_json = row["result_json"]
    if not result_json:
        _raise_app_error(
            code="SERVER_JOB_RESULT_MISSING",
            message="Job result is empty.",
            status_code=500,
            details={"job_id": job_id},
            retryable=True,
        )
    return ChatDecisionResponse.model_validate(json.loads(result_json))


@app.get("/api/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, auth: AuthContext = Depends(get_auth_context)) -> JobStatusResponse:
    row = _load_job(job_id, auth.user_id)
    return _job_status_response(row)


@app.post("/api/v1/jobs/{job_id}/retry", response_model=RetryJobResponse)
def retry_job(job_id: str, auth: AuthContext = Depends(get_auth_context)) -> RetryJobResponse:
    row = _load_job(job_id, auth.user_id)
    if row["status"] != "failed":
        _raise_app_error(
            code="SERVER_JOB_RETRY_INVALID_STATE",
            message="Only failed jobs can be retried.",
            status_code=409,
            details={"status": row["status"], "job_id": job_id},
        )
    if not bool(row["retryable"]):
        _raise_app_error(
            code="SERVER_JOB_NOT_RETRYABLE",
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
    queue_key = SERVER_CHAT_QUEUE_KEY if row["job_type"] == "chat" else SERVER_INDEX_QUEUE_KEY
    _enqueue_job(queue_key, job_id)
    return RetryJobResponse(
        job_id=job_id,
        status="queued",
        project_id=row["project_id"],
        job_type=row["job_type"],
    )
