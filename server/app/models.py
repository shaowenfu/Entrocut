from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class RuntimeCapabilitiesResponse(BaseModel):
    service: str
    version: str
    phase: str
    mode: str
    retained_surfaces: list[str]


class LoginSessionCreateRequest(BaseModel):
    provider: Literal["google", "github"] = "google"
    client_redirect_uri: str | None = None


class LoginSessionCreateResponse(BaseModel):
    login_session_id: str
    authorize_url: str
    expires_in: int


class UserProfile(BaseModel):
    id: str
    email: str | None = None
    display_name: str | None = None
    avatar_url: str | None = None
    status: str
    plan: str = "free"
    quota_status: str = "healthy"
    quota_total: int | None = None
    remaining_quota: int | None = None


class TokenBundle(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"


class LoginSessionResult(BaseModel):
    access_token: str
    refresh_token: str
    expires_in: int
    token_type: str = "Bearer"
    user: UserProfile


class LoginSessionStatusResponse(BaseModel):
    login_session_id: str
    provider: str
    status: Literal["pending", "authenticated", "failed", "consumed", "expired"]
    result: LoginSessionResult | None = None
    error: dict[str, Any] | None = None


class StagingBootstrapLoginSessionRequest(BaseModel):
    login_session_id: str = Field(min_length=8)
    provider: Literal["google", "github"] = "google"
    email: str | None = None
    display_name: str | None = None


class StagingBootstrapLoginSessionResponse(BaseModel):
    login_session_id: str
    status: Literal["authenticated"]
    user: UserProfile


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class RefreshTokenResponse(TokenBundle):
    pass


class MeResponse(BaseModel):
    user: UserProfile


class LogoutResponse(BaseModel):
    status: str = "ok"


class UserProfileResponse(BaseModel):
    user: UserProfile


class UserUsageSnapshot(BaseModel):
    remaining_quota: int | None = None
    quota_total: int | None = None
    quota_status: str = "healthy"
    consumed_tokens_today: int = 0
    consumed_tokens_this_month: int = 0
    request_count_today: int = 0
    request_count_this_month: int = 0
    membership_plan: str = "free"
    subscription_status: str = "active"
    rate_limit_requests_per_minute: int
    rate_limit_tokens_per_minute: int


class UserUsageResponse(BaseModel):
    user_id: str
    usage: UserUsageSnapshot


# ============ Vector Models ============


class AssetReference(BaseModel):
    """Asset 引用，支持多种输入类型"""

    type: Literal["image_url", "video_url", "text"]
    content: str = Field(..., description="图片 URL 或文本内容")
    mime_type: str | None = Field(default=None, description="可选的 MIME 类型提示")


class VectorizeRequest(BaseModel):
    """向量化请求"""

    asset_id: str = Field(..., description="Asset 唯一标识符")
    references: list[AssetReference] = Field(..., min_length=1, description="Asset 引用列表")
    metadata: dict[str, Any] | None = Field(default=None, description="可选的元数据")


class AssetVector(BaseModel):
    """单个 Asset 的向量结果"""

    asset_id: str
    vector: list[float]
    dimension: int


class VectorizeResponse(BaseModel):
    """向量化响应"""

    status: Literal["success", "partial_success", "failed"] = "success"
    vectors: list[AssetVector]
    message: str | None = None


# ============ Retrieval Models ============


class AssetRetrievalRequest(BaseModel):
    """资产检索请求"""

    collection_name: str = "entrocut_assets"
    partition: str = "default"
    model: str = "qwen3-vl-embedding"
    dimension: int = 1024
    query_text: str = Field(..., min_length=1, max_length=2000)
    topk: int = Field(default=8, ge=1, le=100)
    filter: str | None = Field(default=None, alias="filter")
    include_vector: bool = False
    output_fields: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class RetrievalMatch(BaseModel):
    """单个匹配结果"""

    id: str
    score: float
    vector: list[float] | None = None
    fields: dict[str, Any]


class RetrievalQuery(BaseModel):
    """检索查询信息（响应中回显）"""

    query_text: str
    topk: int
    filter: str | None = Field(default=None, alias="filter")

    model_config = {"populate_by_name": True}


class AssetRetrievalResponse(BaseModel):
    """资产检索响应"""

    collection_name: str
    partition: str
    query: RetrievalQuery
    matches: list[RetrievalMatch]
    usage: dict[str, int]
