# 08. Implementation Plan（实现计划）

## 1. 路线总览

采用 `Contract-first` 分阶段交付，先通链路再优化体验。

## 2. Phase 划分

### Phase 0：契约冻结

目标：

1. 冻结 `EntroVideoProject v1.0`。
2. 冻结 `core/server` API 契约。

完成标准：

1. 三端模型定义一致。
2. 文档评审通过，字段无歧义。

### Phase 1：本地 Ingest 引擎

目标：

1. 打通切分、抽帧、拼图、返回 `AtomicClip`。
2. 产出可复用本地索引数据结构。

完成标准：

1. 传入本地路径可稳定返回片段 JSON。
2. 样本视频可重复得到近似切分结果。

### Phase 2：云端向量化与检索

目标：

1. 接入 `Qwen3-VL-Embedding + DashVector`。
2. 打通 `upsert` 与 `semantic retrieval`。

完成标准：

1. 检索结果只返回当前用户数据。
2. Top-N 结果含 `file_path + time_range + score`。

### Phase 3：Agent 编排

目标：

1. 实现单一 `POST /api/v1/chat` 入口。
2. 生成可执行 `EntroVideoProject`。
3. 在 `chat` 内部完成上下文工程、意图判断与逻辑路由。

完成标准：

1. 首轮 `chat` 可生成 30 秒草案。
2. 微调 `chat` 可替换指定片段并给出 `reasoning`。
3. 不新增对外 `plan/refine` API。

### Phase 4：Client 工作台联调

目标：

1. 打通启动页 + 工作台双界面。
2. 打通 `chat -> contract -> preview`。

完成标准：

1. 用户可看到契约驱动的可视化预览。
2. 对话微调后可触发重渲染。

### Phase 5：Export 与稳定性

目标：

1. 支持单默认配置导出。
2. 完成错误语义、日志、超时重试。

完成标准：

1. 导出成功率达到目标线。
2. 关键链路具备可观测性。

## 3. 并行分工建议

1. `Client`：界面框架、状态同步、Sidecar 管理。
2. `Core`：切分抽帧、渲染导出、任务状态管理。
3. `Server`：向量化检索、会话编排、契约生成。
4. `PM/Arch`：契约评审、场景验收、非目标守卫。

## 4. 风险与缓解

1. 风险：向量召回与用户意图偏差。
   1. 缓解：`chat` 响应输出检索关键词与理由，支持人工可见。
2. 风险：大素材处理耗时波动。
   1. 缓解：分批处理与进度回传。
3. 风险：三端契约漂移。
   1. 缓解：CI 加入 `Contract Compatibility Check`。
