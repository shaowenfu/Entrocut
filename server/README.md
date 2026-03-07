# Server Shell

`server` 当前是最小 `Cloud Orchestration Service（云端编排服务）`。

## 当前能力

1. `GET /health` 健康检查（含 `queue/storage` 状态）。
2. `POST /api/v1/index/jobs` 创建向量入库任务。
3. `POST /api/v1/chat/jobs` 创建对话编排任务。
4. `POST /api/v1/index/upsert-clips` 同步等待入库完成（兼容模式）。
5. `POST /api/v1/chat` 同步返回 `AgentDecision`。
6. `GET /api/v1/jobs/{job_id}` 查询任务状态。
7. `POST /api/v1/jobs/{job_id}/retry` 手动重试失败任务。

## 说明

## 环境变量

1. `AUTH_JWT_SECRET`：`JWT` 校验密钥（必填）。
2. `AUTH_JWT_ALGORITHM`：默认 `HS256`。
3. `REDIS_URL`：外部队列地址。
4. `SERVER_DB_PATH`：`SQLite` 文件路径。
5. `DASHSCOPE_API_KEY`：阿里云 `DashScope` API Key（开启真实 `Embedding adapter` 必填）。
6. `DASHSCOPE_EMBEDDING_MODEL`：默认 `qwen3-vl-embedding`。
7. `DASHSCOPE_WORKSPACE`：可选 `DashScope workspace`。
8. `DASHVECTOR_API_KEY`：阿里云 `DashVector` API Key（开启真实 `DashVector` 必填）。
9. `DASHVECTOR_ENDPOINT`：`DashVector endpoint`。
10. `DASHVECTOR_COLLECTION`：向量集合名。
11. `DASHVECTOR_METRIC`：默认 `cosine`。
12. `DASHVECTOR_AUTO_CREATE_COLLECTION`：默认 `true`，首次写入时自动建集合。
13. `SERVER_EMBEDDING_MAX_REQUESTS_PER_USER`：本地进程级 `embedding quota`，默认 `0` 表示不限。
14. `SERVER_VECTOR_SEARCH_MAX_REQUESTS_PER_USER`：本地进程级 `search quota`，默认 `0` 表示不限。

## 说明

1. `chat` 响应已升级为结构化 `project/patch/ops`。
2. 所有业务接口都需要 `Authorization: Bearer <token>`。
3. 错误统一返回 `ErrorEnvelope`。
4. `Embedding adapter` 现在采用“真实 provider 优先，缺配置时 `mock fallback`”策略。
5. `Vector search` 现在强制注入 `user_id` 作用域，真实 `DashVector` 同时使用 `partition + fields filter` 做双层隔离。
6. `Quota / rate limit / provider failure` 在服务层统一收敛为三类语义：
   - `SERVER_PROVIDER_QUOTA_EXCEEDED`
   - `SERVER_PROVIDER_RATE_LIMITED`
   - `SERVER_PROVIDER_UNAVAILABLE`

## 最小验证

成功路径（真实 provider）：

```bash
cd server
source venv/bin/activate
export DASHSCOPE_API_KEY='<your_dashscope_key>'
export DASHVECTOR_API_KEY='<your_dashvector_key>'
export DASHVECTOR_ENDPOINT='<your_dashvector_endpoint>'
export DASHVECTOR_COLLECTION='entrocut_phase45'
python - <<'PY'
from app.services.runtime import build_server_runtime

runtime = build_server_runtime()
embedding = runtime.embedding_proxy.embed_frame_sheet(
    'data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2w==',
    user_id='user_c_demo',
)
print('embedding_ok', embedding.ok, embedding.payload.get('provider'), embedding.payload.get('vector_dim'))

upsert = runtime.vector_search.upsert_clips(
    [
        {
            'clip_id': 'clip_001',
            'asset_id': 'asset_001',
            'start_ms': 0,
            'end_ms': 3000,
            'score': 0.92,
            'description': 'sunset beach running shot',
            'vector': embedding.payload['vector'],
        }
    ],
    user_id='user_c_demo',
    project_id='project_demo',
)
print('upsert_ok', upsert.ok, upsert.payload)

search = runtime.vector_search.semantic_search(
    'sunset running',
    top_k=3,
    filters={'user_id': 'user_c_demo', 'project_id': 'project_demo'},
)
print('search_ok', search.ok, search.payload.get('hits'))
PY
```

失败路径（本地 quota / provider 失败语义）：

```bash
cd server
source venv/bin/activate
export SERVER_VECTOR_SEARCH_MAX_REQUESTS_PER_USER=1
python - <<'PY'
from app.services.runtime import build_server_runtime

runtime = build_server_runtime()
ok_result = runtime.vector_search.semantic_search(
    'first query',
    top_k=1,
    filters={'user_id': 'quota_user', 'project_id': 'p1'},
)
failed_result = runtime.vector_search.semantic_search(
    'second query',
    top_k=1,
    filters={'user_id': 'quota_user', 'project_id': 'p1'},
)
print('first', ok_result.ok, ok_result.payload)
print('second', failed_result.ok, failed_result.payload)
PY
```

第二次调用应返回 `ok=False`，且 `error_code=SERVER_PROVIDER_QUOTA_EXCEEDED`。
