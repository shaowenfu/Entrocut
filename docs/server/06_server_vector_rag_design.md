# Server Vector & RAG Design（向量化与检索落地方案）

本文档定义 `Server` 侧 `/v1/assets/vectorize` 与 `/v1/assets/retrieval` 的落地方案。目标是让 `Server` 负责：

1. 使用 `DashScope MultiModalEmbedding（百炼多模态融合向量接口）` 生成向量
2. 使用 `DashVector Python SDK（DashVector Python SDK）` 写入和检索向量
3. 对 `Core / Client` 暴露尽量稳定、尽量接近官方语义的 `REST API`

如果要看 `retrieve / inspect` 在当前架构下的整体云端网关方案，请继续阅读：

- [06a_server_retrieve_inspect_gateway_design.md](./06a_server_retrieve_inspect_gateway_design.md)

## 1. 设计结论

### 1.1 第一阶段能力边界

第一阶段 `/v1/assets/vectorize` 必须直接落 `multimodal fused embedding（多模态融合向量）`，不走 `OpenAI-compatible`。

原因：
1. 你的业务目标本身就是跨模态检索，单独文本向量先落会把接口方向做偏
2. [vectorize.md](/home/sherwen/MyProjects/Entrocut_server/docs/reference/vectorize.md) 已明确说明：`多模态融合向量` 不支持 `OpenAI-compatible`
3. 既然产品要求是“文搜图、图搜图、文搜视频、跨模态检索”，那 `/v1/assets/vectorize` 的第一性目标就应该是把 `text/image/video` 融成一个向量

因此第一阶段建议：
1. `/v1/assets/vectorize` 当前主输入固定为 `Core` 生成的 `clip contact sheet image`
2. 融合模型默认使用 `qwen3-vl-embedding`
3. `/v1/assets/retrieval` phase 1 只支持基于 `planner` 生成的 `query_text` 做纯向量召回；`query_image / query_video` 与辅助通道后续再扩

### 1.2 与官方接口的对齐策略

我们不直接把 `DashVector SDK` 的 `Collection.insert/query` 原样暴露给外部，而是采用“外部轻量 REST + 内部官方对象语义”：

1. 外部接口保持 `RESTful（REST 风格）`
2. 字段命名尽量对齐 `DashVector` 官方概念：
   - `collection_name`
   - `partition`
   - `docs`
   - `topk`
   - `filter`
   - `include_vector`
   - `output_fields`
3. 内部实现直接映射到：
   - `collection.insert(...)`
   - `collection.query(...)`

这样做的好处是：
1. 外部契约稳定，不把 `Python SDK` 细节泄露给 `Core`
2. 内部实现和官方文档一一对应，开发与排障成本最低

## 2. 官方资料依据

### 2.1 DashScope MultiModalEmbedding（百炼多模态融合向量）

参考：
- [vectorize.md](/home/sherwen/MyProjects/Entrocut_server/docs/reference/vectorize.md)

关键结论：
1. `多模态融合向量` 不支持 `OpenAI-compatible`
2. 官方建议通过 `DashScope SDK / API` 调 `MultiModalEmbedding.call(...)`
3. 模型建议为 `qwen3-vl-embedding`
4. 单个输入对象可同时携带：
   - `text`
   - `image`
   - `video`
5. 当三者放在同一个对象里时，返回一个融合向量

但当前项目的 `phase 1` 并不直接使用这三者全开能力，而是收敛为：

1. 由 `Core` 本地抽帧并拼成 `contact sheet`
2. `Server` 只接收 `image_base64`
3. 先把检索主链跑稳，再考虑未来扩成更宽输入

### 2.2 DashVector SDK（插入与检索）

参考官方文档：
- 安装 SDK：<https://help.aliyun.com/zh/document_detail/2510231.html?spm=a2c4g.11186623.0.preDoc.38dd75f9BOld9h>
- 创建 `Client`：<https://help.aliyun.com/zh/document_detail/2510240.html?spm=a2c4g.11186623.help-menu-2510217.d_3_1_0.70263b29BAnvBx&scm=20140722.H_2510240._.OR_help-T_cn~zh-V_1>
- 插入 `Doc`：<https://help.aliyun.com/zh/document_detail/2510249.html?spm=a2c4g.11186623.help-menu-2510217.d_3_1_2_0.2a6f3b29QmCyVO&scm=20140722.H_2510249._.OR_help-T_cn~zh-V_1>
- 检索 `Doc`：<https://help.aliyun.com/zh/document_detail/2510250.html?spm=a2c4g.11186623.help-menu-2510217.d_3_1_2_1.3aac61986o2XFQ&scm=20140722.H_2510250._.OR_help-T_cn~zh-V_1>

关键结论：
1. `dashvector.Client(api_key, endpoint, protocol, timeout)` 是入口
2. `Collection.insert(docs, partition=None, async_req=False)` 负责写入
3. `Collection.query(vector=None, id=None, topk=10, filter=None, include_vector=False, partition=None, output_fields=None, ...)` 负责检索
4. `insert` 默认不会覆盖同 `id` 的已有 `Doc`
5. `query` 官方核心参数是 `vector / id / topk / filter / include_vector / output_fields`

## 3. Server 侧职责边界

`Server` 在这条链路里只做四件事：

1. 校验 `JWT`
2. 调 `DashScope embeddings`
3. 调 `DashVector`
4. 统一错误语义、审计字段、额度扣费

`Server` 不做的事：
1. 不把原始向量回传给 `Client/Core` 作为默认行为
2. 不让 `Client/Core` 直接持有 `DashVector API Key`
3. 不在 phase 1 里同时兼容文本、图像、视频三套向量化逻辑

## 4. 配置设计

建议新增环境变量：

```env
# DashScope multimodal embedding
DASHSCOPE_API_KEY=
DASHSCOPE_MULTIMODAL_EMBEDDING_MODEL=qwen3-vl-embedding
DASHSCOPE_MULTIMODAL_DIMENSION=1024

# DashVector
DASHVECTOR_API_KEY=
DASHVECTOR_ENDPOINT=
DASHVECTOR_COLLECTION_NAME=entrocut_assets
DASHVECTOR_PARTITION=default
DASHVECTOR_TIMEOUT_SECONDS=10
DASHVECTOR_PROTOCOL=grpc
```

说明：
1. `DASHVECTOR_COLLECTION_NAME` 设为默认值，但接口允许显式覆盖
2. `DASHVECTOR_PROTOCOL` 默认 `grpc`，与官方建议一致
3. `DASHVECTOR_ENDPOINT` 由控制台 `Cluster Endpoint` 提供

## 5. 接口方案

## 5.1 `POST /v1/assets/vectorize`

### 目标

接收一批候选 `clip` 的 `contact sheet image`，先生成 `fused embedding（融合向量）`，再原子写入 `DashVector`。

### 为什么不用“只返回向量给 Core”

因为这会破坏边界：
1. 向量属于高价值中间产物，不应回流到本地
2. 让 `Server` 负责“生成 + 入库”才是完整的安全闭环

### 请求体

```json
{
  "collection_name": "entrocut_assets",
  "partition": "default",
  "model": "qwen3-vl-embedding",
  "dimension": 1024,
  "docs": [
    {
      "id": "clip_001",
      "content": {
        "image_base64": "..."
      },
      "fields": {
        "clip_id": "clip_001",
        "asset_id": "asset_001",
        "project_id": "proj_001",
        "scene_id": "scene_001",
        "media_type": "video",
        "source": "core"
      }
    }
  ]
}
```

### 字段设计

#### 顶层字段

1. `collection_name: str`
   - 对齐官方 `Collection`
   - 可选，默认取服务配置

2. `partition: str`
   - 对齐官方 `partition`
   - 可选，默认取服务配置

3. `model: str`
   - 对齐 `DashScope MultiModalEmbedding` 的 `model`
   - 默认 `qwen3-vl-embedding`

4. `dimension: int`
   - 对齐官方可选维度参数
   - 支持 `2560, 2048, 1536, 1024, 768, 512, 256`
   - 默认取服务配置

5. `docs: List[VectorizeDoc]`
   - 与 `DashVector insert docs` 概念直接对齐

#### `VectorizeDoc`

1. `id: str`
   - 建议必填
   - 不建议依赖 `DashVector` 自动生成 `id`
   - 因为业务系统必须能稳定追踪候选 `clip`

2. `content: object`
   - phase 1 必填
   - 当前最小输入固定为 `image_base64`
   - 表示由 `Core` 本地生成的 `clip contact sheet`

3. `content.image_base64: str`

6. `fields: object`
   - 直接映射到 `DashVector Doc.fields`
   - 值类型需遵循官方约束

### 处理流程

1. 校验 `JWT`
2. 校验 `docs` 非空，且每个 `doc.id / doc.content.image_base64` 合法
3. 批量调用 `dashscope.MultiModalEmbedding.call(...)`
4. 将结果映射成 `DashVector Doc(id, vector, fields)`
5. 调 `collection.insert(docs=..., partition=...)`
6. 若全部成功，返回写入结果摘要
7. 若 `embedding` 成功但 `insert` 失败，整个请求按失败返回，不返回部分成功

### 原子性策略

严格事务意义上，跨 `DashScope + DashVector` 做不到数据库事务；这里采用“接口级原子语义”：

1. 对调用方来说，只暴露 `success` 或 `failed`
2. 不把“embedding 已成功但 insert 失败”的半状态暴露给 `Core`
3. 失败时记录结构化日志，必要时由后台补偿任务清理或重试

这已经满足你要的“先向量化再插入，失败要明确报错”的目标。

### 响应体

```json
{
  "collection_name": "entrocut_assets",
  "partition": "default",
  "model": "qwen3-vl-embedding",
  "dimension": 1024,
  "inserted_count": 1,
  "results": [
    {
      "id": "asset_001",
      "status": "inserted"
    }
  ],
  "usage": {
    "embedding_doc_count": 1,
    "dashvector_write_units": 1
  }
}
```

### 与官方语义的对应

1. `docs` 对应 `Collection.insert(docs=...)`
2. `partition` 对应 `Collection.insert(..., partition=...)`
3. `fields` 对应 `Doc.fields`
4. `results` 对应官方 `DashVectorResponse.output`
5. `usage.dashvector_write_units` 对应官方 `usage`

## 5.2 `POST /v1/assets/retrieval`

### 目标

根据上游 `planner` 生成的主 `query_text` 生成查询向量，再在 `DashVector` 中执行一次纯向量相似性检索。

### 请求体

```json
{
  "collection_name": "entrocut_assets",
  "partition": "default",
  "model": "qwen3-vl-embedding",
  "dimension": 1024,
  "query_text": "滑雪跃起的动作",
  "topk": 8,
  "filter": "project_id = 'proj_001'",
  "include_vector": false,
  "output_fields": ["clip_id", "asset_id", "project_id", "scene_id", "media_type"]
}
```

### 字段设计

1. `collection_name: str`
   - 对齐官方 `Collection`

2. `partition: str`
   - 对齐官方 `partition`

3. `model: str`
   - 用于生成查询向量

4. `dimension: int`
   - 与向量入库时保持一致

5. `query_text: str`
   - phase 1 唯一主查询入口
   - 来源应是 `retrieval hypothesis` 改写后的可搜索自然语言

6. `topk: int`
   - 直接对齐官方 `topk`
   - 当前只表示单次主召回返回上限

7. `filter: str`
   - 直接对齐官方 `filter`
   - 语法按 `DashVector` 官方过滤表达式处理
   - 当前只应用于搜索空间边界，不承担语义替代职责

8. `include_vector: bool`
   - 直接对齐官方 `include_vector`
   - 默认 `false`

9. `output_fields: List[str]`
   - 直接对齐官方 `output_fields`

### 处理流程

1. 校验 `JWT`
2. 校验 `query_text`、`topk`
3. 调 `DashScope MultiModalEmbedding` 生成查询向量
4. 调 `collection.query(vector=..., topk=..., filter=..., include_vector=..., output_fields=..., partition=...)`
5. 对结果做最小归一化并返回

当前阶段不做：

1. 不做 `ASR/OCR` 辅助通道融合
2. 不做多 query 合并
3. 不做服务端 rerank
4. 不做 `inspect` 级精判

### 响应体

```json
{
  "collection_name": "entrocut_assets",
  "partition": "default",
  "query": {
    "query_text": "滑雪跃起的动作",
    "topk": 8,
    "filter": "project_id = 'proj_001'"
  },
  "matches": [
    {
      "id": "clip_001",
      "score": 0.9231,
      "fields": {
        "clip_id": "clip_001",
        "asset_id": "asset_001",
        "project_id": "proj_001",
        "scene_id": "scene_001",
        "media_type": "video"
      }
    }
  ],
  "usage": {
    "embedding_query_count": 1,
    "dashvector_read_units": 1
  }
}
```

### 与官方语义的对应

1. `query_text` 是 `Server` 为了易用性增加的一层包装
2. 一旦拿到查询向量，内部就是官方 `Collection.query(vector=...)`
3. `topk / filter / include_vector / output_fields / partition` 全部直接映射

## 6. Python 实现建议

## 6.1 模块拆分

建议新增：

1. `server/app/vector_service.py`
   - `DashScopeMultiModalEmbeddingClient`
   - `DashVectorStore`
   - `VectorService`

2. `server/app/vector_models.py`
   - 请求/响应 `Pydantic models`

3. `server/tests/test_vector_service.py`
   - 单元测试

4. `server/tests/test_vector_routes.py`
   - 路由测试

## 6.2 `DashScopeMultiModalEmbeddingClient`

建议职责：
1. 只负责调 `dashscope.MultiModalEmbedding.call(...)`
2. 不关心 `DashVector`
3. 提供：
   - `embed_contents(contents: list[dict[str, str]], model: str, dimension: int | None) -> list[list[float]]`

建议调用方式：

```python
import dashscope

resp = dashscope.MultiModalEmbedding.call(
    api_key=settings.dashscope_api_key,
    model="qwen3-vl-embedding",
    input=[
        {
            "text": "这是一段测试文本",
            "image": "https://example.com/a.jpg",
            "video": "https://example.com/b.mp4"
        }
    ],
    dimension=1024,
)
```

说明：
1. 这样最贴近阿里官方 `MultiModalEmbedding` 设计
2. 也便于未来替换成别的 `embedding provider`

## 6.3 `DashVectorStore`

建议职责：
1. 持有 `dashvector.Client`
2. 提供：
   - `insert_docs(...)`
   - `query_docs(...)`

建议初始化：

```python
import dashvector

client = dashvector.Client(
    api_key=settings.dashvector_api_key,
    endpoint=settings.dashvector_endpoint,
    timeout=settings.dashvector_timeout_seconds,
)
collection = client.get(name=collection_name)
```

说明：
1. `protocol` 默认走 `GRPC`
2. 若部署环境网络限制 `GRPC`，再退到 `HTTP`

## 6.4 `VectorService`

建议提供两个入口：

1. `vectorize_docs(request, user)`
2. `retrieve_docs(request, user)`

### `vectorize_docs`

1. 先抽出 `input_text`
2. 批量 `multimodal embed`
3. 组装 `Doc(id, vector, fields)`
4. 调 `collection.insert`
5. 统一转成对外响应

### `retrieve_docs`

1. 先 `embed query_text`
2. 调 `collection.query`
3. 统一转成 `matches`

## 7. 错误语义

建议新增以下错误码：

| HTTP | code | 语义 |
| --- | --- | --- |
| `422` | `INVALID_VECTORIZE_REQUEST` | `vectorize` 请求体不合法 |
| `422` | `INVALID_RETRIEVAL_REQUEST` | `retrieval` 请求体不合法 |
| `422` | `INVALID_MULTIMODAL_CONTENT` | 多模态内容为空或格式非法 |
| `502` | `EMBEDDING_PROVIDER_UNAVAILABLE` | `DashScope MultiModalEmbedding` 失败 |
| `502` | `VECTOR_STORE_UNAVAILABLE` | `DashVector` 失败 |
| `409` | `VECTOR_DOC_CONFLICT` | 文档主键冲突，且本次不允许覆盖 |

说明：
1. 根据官方文档，`insert` 对已存在 `id` 默认不会覆盖，因此冲突必须明确表达
2. 不要把底层 SDK 原始报错直接泄露给外部，只保留必要上下文

## 8. 推荐数据约定

建议 `fields` 至少统一这些键：

```json
{
  "asset_id": "asset_001",
  "project_id": "proj_001",
  "scene_id": "scene_001",
  "shot_id": "shot_001",
  "media_type": "video",
  "source": "core",
  "created_by": "user_001"
}
```

好处：
1. `filter` 能直接按 `project_id / scene_id / media_type` 检索
2. 以后补 `RAG`、审计、清理任务都更顺手

## 9. 回归测试建议

至少覆盖：

1. 未登录访问 `/v1/assets/vectorize` 返回 `401`
2. 未登录访问 `/v1/assets/retrieval` 返回 `401`
3. `vectorize` 成功时会调用一次 `embed` 和一次 `insert`
4. `retrieval` 成功时会调用一次 `embed` 和一次 `query`
5. `DashScope MultiModalEmbedding` 失败时返回 `502 EMBEDDING_PROVIDER_UNAVAILABLE`
6. `DashVector` 失败时返回 `502 VECTOR_STORE_UNAVAILABLE`
7. `include_vector=false` 时默认不回传向量
8. `filter / topk / output_fields / partition` 会透传到 `DashVector query`

## 10. 建议的落地顺序

1. 先加配置与 `Pydantic models`
2. 实现 `DashScopeMultiModalEmbeddingClient`
3. 实现 `DashVectorStore`
4. 落 `/v1/assets/vectorize`
5. 落 `/v1/assets/retrieval`
6. 补路由测试与服务测试
7. 最后再扩 `query_image / query_video`

## 11. 非目标

当前方案明确不做：

1. 不做 `hybrid sparse+dense retrieval（稀疏+稠密混合检索）`
2. 不做 `query_image / query_video` 检索输入
3. 不做 `rerank（重排序）`
4. 不做 `multi-vector collection（多向量集合）`
5. 不做 `upsert（覆盖式写入）`

这些都能以后加，但现在加只会把接口和实现都搞复杂。
