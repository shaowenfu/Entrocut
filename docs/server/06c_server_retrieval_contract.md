# Server Retrieval Contract

本文档定义 `POST /v1/assets/retrieval` 的字段级契约草案。

当前阶段，它只服务一件事：

`把 planner 生成的主 query_text 转成查询向量，并在 DashVector 中执行一次纯向量召回。`

---

## 1. 设计边界

当前阶段：

1. 主查询固定为 `query_text`
2. 检索对象固定为 `clip`
3. 只做一次主召回
4. 只返回候选，不做精判

当前不做：

1. 不支持 `query_image`
2. 不支持 `query_video`
3. 不做多 query 合并
4. 不做服务端 rerank
5. 不做 `inspect` 级判断

---

## 2. Endpoint

```http
POST /v1/assets/retrieval
Authorization: Bearer <jwt>
Content-Type: application/json
```

---

## 3. Request Schema

```ts
interface RetrievalRequest {
  query_text: string;
  filter?: string | null;
}
```

### 3.1 字段约束

1. `query_text` 非空
2. `filter` 只表达搜索空间边界
3. 不接受 `collection_name / partition / model / dimension / topk / include_vector / output_fields`
4. 召回数量、输出字段和向量库配置全部来自 server config

### 3.2 当前阶段建议

1. `query_text` 应来自 `retrieval hypothesis` 改写
2. `filter` 只用于业务域过滤，例如 project 和 asset 状态
3. `include_vector` 固定为 false，裸向量不回传

---

## 4. Response Schema

```ts
interface RetrievalMatch {
  id: string; // clip_id
  score: number;
  fields: {
    clip_id: string;
    asset_id: string;
    project_id?: string;
    source_start_ms?: number;
    source_end_ms?: number;
  };
}

interface RetrievalResponse {
  query: {
    query_text: string;
    topk: number;
    filter?: string | null;
  };
  matches: RetrievalMatch[];
  usage?: {
    embedding_query_count: number;
    dashvector_read_units?: number | null;
  };
}
```

---

## 5. Errors

```ts
type RetrievalErrorCode =
  | "INVALID_RETRIEVAL_REQUEST"
  | "QUERY_EMBEDDING_FAILED"
  | "VECTOR_STORE_UNAVAILABLE"
  | "RETRIEVAL_FAILED";
```

推荐语义：

1. `INVALID_RETRIEVAL_REQUEST`
   - 请求体不合法
2. `QUERY_EMBEDDING_FAILED`
   - 查询向量生成失败
3. `VECTOR_STORE_UNAVAILABLE`
   - `DashVector` 不可用
4. `RETRIEVAL_FAILED`
   - 查询过程失败

---

## 6. 一句话结论

`/v1/assets/retrieval` 的当前契约，本质上是“接收一个主 query_text，做一次纯向量召回，把 clip 候选池返回给 Core”。
