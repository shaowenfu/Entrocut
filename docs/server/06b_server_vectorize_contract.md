# Server Vectorize Contract

本文档定义 `POST /v1/assets/vectorize` 的字段级契约草案。

当前阶段，它只服务一件事：

`把 Core 本地生成的 clip contact sheet 图像，通过 Server 中转为多模态 embedding 并写入 DashVector。`

---

## 1. 设计边界

当前阶段：

1. 索引单元固定为 `clip`
2. 主输入固定为 `contact sheet image_base64`
3. `Server` 负责“向量化 + 入库”的接口级原子语义
4. `Server` 不回传裸向量

当前不做：

1. 不上传原始视频
2. 不要求默认同时输入 `text + image + video`
3. 不在这个接口里做检索

---

## 2. Endpoint

```http
POST /v1/assets/vectorize
Authorization: Bearer <jwt>
Content-Type: application/json
```

---

## 3. Request Schema

```ts
interface VectorizeDoc {
  id: string; // 建议等于 clip_id
  content: {
    image_base64: string;
  };
  fields: {
    clip_id: string;
    asset_id: string;
    project_id: string;
    source_start_ms: number;
    source_end_ms: number;
    frame_count?: number | null;
  };
}

interface VectorizeRequest {
  collection_name?: string;
  partition?: string;
  model?: string; // default: qwen3-vl-embedding
  dimension?: number; // default: 1024
  docs: VectorizeDoc[];
}
```

### 3.1 字段约束

1. `docs` 非空
2. `id`、`fields.clip_id` 必须稳定可追踪
3. `content.image_base64` 必须是可解析图像
4. `source_start_ms < source_end_ms`
5. 同一请求内不允许重复 `id`

### 3.2 当前阶段建议

1. 单次请求走小批量
2. 图像统一低清 `JPEG`
3. `dimension` 对齐当前索引配置

---

## 4. Response Schema

```ts
interface VectorizeResultItem {
  id: string;
  status: "inserted";
}

interface VectorizeResponse {
  collection_name: string;
  partition: string;
  model: string;
  dimension: number;
  inserted_count: number;
  results: VectorizeResultItem[];
  usage?: {
    embedding_doc_count: number;
    dashvector_write_units?: number | null;
  };
}
```

---

## 5. Errors

```ts
type VectorizeErrorCode =
  | "INVALID_VECTORIZE_REQUEST"
  | "IMAGE_DECODE_FAILED"
  | "EMBEDDING_PROVIDER_UNAVAILABLE"
  | "VECTOR_STORE_UNAVAILABLE"
  | "VECTORIZE_WRITE_FAILED";
```

推荐语义：

1. `INVALID_VECTORIZE_REQUEST`
   - 请求体缺字段或字段非法
2. `IMAGE_DECODE_FAILED`
   - `image_base64` 非法或不可解析
3. `EMBEDDING_PROVIDER_UNAVAILABLE`
   - 阿里云 `embedding` 失败
4. `VECTOR_STORE_UNAVAILABLE`
   - `DashVector` 不可用
5. `VECTORIZE_WRITE_FAILED`
   - 向量生成成功但写入失败

---

## 6. 一句话结论

`/v1/assets/vectorize` 的当前契约，本质上是“上传 clip contact sheet，小批量向量化并原子写入索引库”的专用网关。
