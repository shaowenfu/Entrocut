# 2026-05-06 Inspect Describe Mode 落地日记

## 背景

本轮工作从 `docs/tasks/2026-05-06_inspect_describe_mode_minimal_plan.md` 开始。

原来的 `Inspect` 更像 `Retrieval` 之后的候选精筛器：先召回多个候选，再让视觉模型帮忙比较、选择或排序。这个定位对“从素材池找片段”是够用的，但不符合当前 `Agent` 的真实工作方式。

新的判断是：

`主 Agent 是文本模型，像一个盲人剪辑师；Inspect 应该成为它随时调用的眼睛。`

因此，`Retrieval` 和 `Inspect` 的边界重新收敛为：

1. `Retrieval` 负责找可能相关的 `clip`
2. `Inspect describe` 负责看懂已知 `clip`
3. 当用户指定某个 `clip` 或 `Agent` 对视觉细节不确定时，`Inspect` 可以不经过新的 retrieval 步骤直接调用
4. `Agent` 需要自己组织面向视觉模型的 task-specific question，由 server 叠加稳定 `system prompt`

## 实施内容

### 1. Server Inspect Contract

server 继续复用现有接口：

```http
POST /v1/tools/inspect
```

没有新增 `/v1/tools/describe`，避免把同一类视觉工具拆成两个重复网关。

本轮完成：

1. `InspectMode` 新增 `describe`
2. `InspectRequest.question` 改为可选，但旧 `verify / compare / choose / rank` 仍要求 `question`
3. 新增 `InspectDescription`
4. `InspectResponse` 新增 `descriptions`
5. `describe` 模式第一版限制 exactly one candidate
6. `describe` 模式允许使用 server 默认 question
7. provider 返回会归一化并校验 `description.clip_id` 必须属于请求候选

关键边界：

1. 不上传原始视频
2. 不做长视频理解
3. 不让 `describe` 负责多候选比较
4. 不生成 `EditDraftPatch`
5. 不放松旧 mode 的响应约束

### 2. Core Context Engineering

`core/context.py` 中的 tool 描述从“候选判优”改成“双职责”：

1. 深入理解已知 `clip`
2. 对少量候选进行比较、消歧与质量判断

`Planner System Prompt` 也同步更新：

1. `retrieve` 用于找候选
2. `inspect` 用于理解已知 `clip` 或判断小候选集
3. 用户指定 `clip` 或视觉细节不确定时，`inspect` 可以不重复 retrieval
4. 请求 `inspect` 时应提供 JSON `tool_input_summary`，包含 `mode`、`clip_id` 和 task-specific `question`

### 3. Core Inspect Execution

原来的 `core/inspection.py` 只基于 `clip.visual_desc` 返回本地摘要，不是真正的视觉理解。

本轮新增 `describe_clip_with_server(...)`：

1. 根据 `clip.asset_id` 找到本地 `AssetModel.source_path`
2. 复用现有 `extract_and_stitch_frames(...)` 抽取 stitched keyframes
3. 组装 `InspectCandidate.frames`
4. 调用 server `/v1/tools/inspect`
5. 把 server `descriptions[0].description` 写入 `inspection_summary`

第一版复用 stitched keyframes 是有意识的 `KISS` 选择。它不是最终形态，但可以最小成本跑通：

`Agent -> Core -> Server -> VLM -> ToolObservation -> Agent`

后续如果视觉效果不够，再把 evidence resolver 拆成多张 ordered frames。

### 4. Server / Core 联调修复

在本轮前置排查中，还修正了两类 server/core 契约问题：

1. `core/config.py` 加载 `core/.env`，避免 Debug Core 忽略 `SERVER_BASE_URL`
2. `client/main/coreSupervisor.ts` 将 `VITE_SERVER_BASE_URL` 映射为托管 Core 子进程需要的 `SERVER_BASE_URL`
3. core vectorize 测试中的 dummy base64 改成真实 JPEG base64，避免测试契约和 DashScope 实际约束脱节
4. chat 请求继续确认不发送非法 `stream_options`

这些改动让 `client -> local core -> server/cloud` 的地址配置和核心接口契约保持一致。

## 验证结果

用户手动执行并确认：

```bash
cd server
source venv/bin/activate
pytest -q tests/test_inspect_routes.py
```

结果：

```text
10 passed in 1.63s
```

用户随后执行：

```bash
cd core
source venv/bin/activate
pytest -q
```

结果：

```text
40 passed, 1 warning in 11.59s
```

中间发现 `core/tests/test_context_engineering.py` 在 `core/` 目录内执行时无法导入 `core.context`。已修复为兼容仓库根目录和 `core/` 目录两种执行方式。

## 后续关注

1. 真实视觉质量取决于 stitched keyframes 是否足够表达时间变化。
2. 如果 `describe` 效果不稳定，下一步应实现 thin evidence resolver，输出多张 ordered frames，而不是单张 stitched image。
3. `Inspect` 的 UI artifact 后续也要从“候选判定报告”扩展成“视觉描述报告”。
4. server contract 已支持 `describe`，但 `/docs` 里仍需要用真实 JPEG base64 手动验证一次 provider 实际响应质量。
