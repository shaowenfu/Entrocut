# 2026-05-09 Inspect 与工具接口契约收敛日记

今天的核心工作是把面向 `Agent` 的工具契约继续往单一职责方向收敛。

前一轮我们已经把 `Inspect` 提升成 `Agent` 的“眼睛”，但实现里仍保留了历史上的 `verify / compare / choose / rank` 语义。这会让边界变混：视觉模型既在“看”，又在替主 `Agent` 做比较和决策。今天把这条边界彻底切清楚：

`Inspect 只负责描述画面，比较、排序、选择和剪辑决策全部交给主 Agent。`

## 1. Inspect Contract 收敛

`server /v1/tools/inspect` 已改成单一图片描述接口。

请求体只保留：

```json
{
  "clip_id": "clip_xxx",
  "prompt": "请描述这个 clip 中可见的主体、动作、场景和镜头信息。",
  "image_base64": "..."
}
```

响应体只保留：

```json
{
  "clip_id": "clip_xxx",
  "description": "...",
  "uncertainty": null,
  "model": "gemini-3.1-flash-lite-preview"
}
```

删除的历史字段包括：

1. `mode`
2. `candidates`
3. `criteria`
4. `ranking`
5. `selected_clip_id`
6. `candidate_judgments`
7. `descriptions[]`

这次调整后，`Inspect` 的定位更稳定：它是 `VLM（多模态大模型）` 网关，不是候选判断器。

## 2. Core Agent 调用同步

`core` 侧同步调整了 `inspect` 工具调用：

1. `core/agent_runtime/inspection.py` 只向 server 发送 `clip_id + prompt + image_base64`
2. `core/agent_runtime/agent.py` 不再识别 `inspect mode`
3. `inspect` 工具返回后，会把 `description` 写回对应 `clip`
4. `clip` 新增：
   - `visual_description`
   - `visual_description_updated_at`
5. 同一个 `clip` 多次 `inspect` 时，直接用字符串拼接：

```text
旧描述

新描述
```

这里刻意没有引入数组、history 表或额外对象，符合当前阶段的 `KISS（保持简单）` 原则。

## 3. Vector API 参数收敛

`server` 侧向量接口删除了不应该暴露给外部调用方的底层参数。

`/v1/assets/vectorize` 不再接受：

1. `collection_name`
2. `partition`
3. `model`
4. `dimension`

`/v1/assets/retrieval` 不再接受：

1. `collection_name`
2. `partition`
3. `model`
4. `dimension`
5. `topk`
6. `include_vector`
7. `output_fields`

`/v1/assets/vector-index-state` 不再接受：

1. `collection_name`
2. `partition`

这些参数全部改由 `server Settings（服务端配置）` 控制。这样外部 API 表达的是业务动作，而不是泄露 `DashVector（向量数据库）` 的实现细节。

## 4. Chat API Schema 收紧

为了减少 `/docs` 面板中的误导性 `additionalProp`，`/v1/chat/completions` 的 `Pydantic schema（数据模型）` 也做了收紧：

1. `ChatMessage` 禁止额外字段
2. `ChatCompletionsRequest` 禁止额外字段
3. `stream_options` 不再暴露给外部请求体
4. `core` 不再主动传 `temperature / max_tokens`

后续如果确实要开放采样参数，应作为明确产品能力重新设计，而不是通过任意 JSON 字段透传。

## 5. 文档与测试

同步更新了：

1. `docs/agent_runtime/08_inspect_tool_contract.md`
2. `docs/server/06b_server_vectorize_contract.md`
3. `docs/server/06c_server_retrieval_contract.md`
4. `docs/server/06d_server_inspect_contract.md`
5. `docs/server/04_server_openai_compatible_contract.md`
6. `server/README.md`

测试侧同步更新了 server 和 core 的契约断言。

用户手动测试结果：

```bash
cd core
source venv/bin/activate
pytest -q tests/test_context_engineering.py tests/test_server_toolchain_integration.py
```

结果：`34 passed, 226 warnings`

第一次完整回归发现两个问题：

1. `server` 中非法 `image_base64` 被 `Pydantic` 的 `min_length` 提前拦截，返回了 `INVALID_INSPECT_REQUEST`
2. `core` 完整测试集里重载 store 时使用了测试文件自己的临时目录，而不是全局 `store.app_data_root`

修复后已单独验证失败用例：

```bash
cd server
source venv/bin/activate
pytest -q tests/test_inspect_routes.py::test_inspect_rejects_invalid_image_base64
```

结果：`1 passed`

```bash
cd core
source venv/bin/activate
pytest -q tests/test_server_toolchain_integration.py::CoreChatPlannerSkeletonTest::test_startup_expires_orphaned_running_media_task
```

结果：`1 passed`

## 6. 后续注意

1. `Inspect` 现在是图片描述工具，不应该再往里面塞候选选择逻辑
2. `Retrieval` 只做粗召回，不能承担视觉细节判断
3. `Agent` prompt 必须明确：看到 `Inspect` 描述后，由主 `Agent` 自己比较、判断和决策
4. 如果未来要开放 `topk / max_tokens / temperature`，必须作为稳定产品参数重新设计，而不是恢复任意字段透传
