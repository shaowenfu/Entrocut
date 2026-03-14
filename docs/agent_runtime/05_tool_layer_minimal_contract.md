# Tool Layer Minimal Contract

本文档定义当前项目 `editing agent（剪辑智能体）` 的最小 `Tool Layer（工具层）` 契约。

目标不是罗列所有底层媒体处理能力，而是固定：

1. `Planner Layer（规划层）` 可以调用哪些高层工具
2. 每类工具的职责、输入、输出和错误边界是什么
3. 这些工具如何共同支撑从对话到粗剪结果的最小闭环

本文档只定义最小 `tool contract（工具契约）`，不展开底层实现、模型选择、`ffmpeg` 参数或检索算法细节。

---

## 1. 第一性原理

从第一性原理看，无论是人类剪辑师还是 `editing agent`，要把意图落成视频结果，底层都要完成 5 件事：

1. 知道当前手里有什么
2. 找到可能有用的素材
3. 判断候选里哪个更合适
4. 把决定写进当前草案
5. 把当前草案变成可审阅结果

这 5 件事直接推出当前阶段的最小工具集合：

1. `read`
2. `retrieve`
3. `inspect`
4. `patch`
5. `preview`

这不是任意选择，而是由 `chat-to-cut（对话到剪辑）` 的最小执行闭环强制决定的。

---

## 2. 设计目标

当前 `Tool Layer` 只服务 4 件事：

1. 让 `planner action` 有稳定落地入口
2. 让 `runtimeState` 有稳定回写来源
3. 让高层规划和底层执行解耦
4. 让当前系统先完成粗剪闭环，而不是提前暴露所有媒体原语

它不负责：

1. 暴露所有底层 `ffmpeg` 操作
2. 暴露所有索引细节和向量库实现
3. 让模型直接操作文件系统级媒体命令
4. 承载长期偏好记忆或会话管理

---

## 3. 为什么只收敛到这 5 类

当前阶段，最重要的不是工具多，而是：

1. 高层语义清楚
2. 输入输出稳定
3. 错误语义明确
4. 足够支撑粗剪主链路

因此，`Planner Layer` 面向的工具不应该是：

1. `ffmpeg_trim`
2. `ffmpeg_concat`
3. `vector_search`
4. `extract_frames`
5. `vlm_compare`

这些都是工具内部能力，而不是 `planner` 级工具。

对 `planner` 来说，更稳定的抽象是：

1. `read`
2. `retrieve`
3. `inspect`
4. `patch`
5. `preview`

它们分别对应：

1. 读当前事实
2. 找候选
3. 判候选
4. 改草案
5. 看结果

---

## 4. 五类最小工具

### 4.1 `read`

作用：

读取当前执行动作所需的结构化事实。

它服务的不是项目原始数据库，而是当前工作上下文。

最小输入：

1. 当前 `project/session` 标识
2. 读取目标类型

最小输出：

1. `EditDraft`
2. 当前选区
3. 当前候选池
4. 当前目标与约束
5. 当前预览版本

错误语义：

1. `NOT_FOUND`
2. `STALE_STATE`
3. `INVALID_SCOPE`

为什么必要：

没有 `read`，其它工具都容易基于过期或不完整事实执行。

---

### 4.2 `retrieve`

作用：

根据当前编辑意图，从素材池中做纯多模态 `embedding` 候选召回。

它回答的是：

`下一步可能用什么素材。`

最小输入：

1. `retrieval request`
2. 当前作用域
3. 当前素材池或可检索范围
4. 单次 `embedding query`

最小输出：

1. 候选 `clips/segments`
2. `embedding` 相似度或排序信息
3. 当前召回是否充分
4. 召回失败原因或不足原因

错误语义：

1. `RETRIEVAL_INPUT_INVALID`
2. `NO_SEARCH_SPACE`
3. `RETRIEVAL_FAILED`
4. `CANDIDATES_INSUFFICIENT`

为什么必要：

没有 `retrieve`，agent 只能在现有草案里局部挪动，无法真正找新素材或替换素材。

当前阶段说明：

1. `retrieve` 只负责高召回初筛
2. phase 1 只走纯多模态 `embedding` 主召回
3. `ASR/OCR / tags / shot stats` 暂不进入默认召回主链
4. 精确判断延后给 `inspect`

---

### 4.3 `inspect`

作用：

对少量候选做更深判断、比较、消歧和重排。

它回答的是：

`这些候选里谁最适合当前目标。`

最小输入：

1. 候选列表
2. 当前比较问题或选择标准
3. 当前作用域和意图

最小输出：

1. 重排后的候选
2. 最优候选或建议集合
3. 判断理由摘要
4. 是否仍需进一步视觉理解

错误语义：

1. `NO_CANDIDATES`
2. `INSPECTION_INPUT_INVALID`
3. `VISUAL_REASONING_FAILED`
4. `DECISION_INCONCLUSIVE`

为什么必要：

`retrieve` 解决“找得到”，`inspect` 才解决“选得准”。

---

### 4.4 `patch`

作用：

对当前 `EditDraft` 施加一次增量修改。

它回答的是：

`现在具体怎么改草案。`

最小输入：

1. 当前 `EditDraft`
2. `EditDraftPatch`
3. 当前版本号

最小输出：

1. 新的 `EditDraft`
2. 新版本号
3. 变更摘要

错误语义：

1. `PATCH_INVALID`
2. `PATCH_TARGET_NOT_FOUND`
3. `PATCH_CONFLICT`
4. `PATCH_NOT_APPLICABLE`

为什么必要：

没有 `patch`，agent 永远只能提建议，不能真正推进草案。

---

### 4.5 `preview`

作用：

把当前草案转成用户可审阅的预览结果。

它回答的是：

`改完之后现在看起来怎么样。`

最小输入：

1. 当前 `EditDraft`
2. 目标预览范围
3. 预览质量或格式选项

最小输出：

1. 预览结果引用
2. 预览对应的草案版本
3. 预览时长、状态和可用性信息

错误语义：

1. `PREVIEW_INPUT_INVALID`
2. `PREVIEW_RENDER_FAILED`
3. `PREVIEW_ASSET_MISSING`
4. `PREVIEW_VERSION_MISMATCH`

为什么必要：

没有 `preview`，用户无法基于结果继续反馈，系统也无法形成真正的 `human-in-the-loop（人类在环）` 闭环。

---

## 5. 工具层的最小执行链

这 5 类工具串起来，就是当前阶段的最小执行链：

1. `read`
   - 读当前状态与草案
2. `retrieve`
   - 找候选素材
3. `inspect`
   - 判断候选
4. `patch`
   - 修改草案
5. `preview`
   - 生成结果

也就是：

`read -> retrieve -> inspect -> patch -> preview`

注意，这不是所有交互都必须经过的固定流水线。

更准确地说：

1. 当只是聊天讨论时，可能只用 `read`
2. 当只是局部 trim 时，可能 `read -> patch -> preview`
3. 当需要补素材时，才走完整主链

因此，这条链是：

`最小完备执行链`

不是：

`唯一合法执行路径`

---

## 6. 高层工具与底层能力的关系

为了避免过早暴露实现细节，必须区分：

### 6.1 Planner-facing tools（面向规划器的工具）

这就是本文档定义的 5 类工具：

1. `read`
2. `retrieve`
3. `inspect`
4. `patch`
5. `preview`

### 6.2 Execution backend capabilities（执行后端能力）

这些是工具内部实现可能调用的能力：

1. 多模态 `embedding` 检索
2. 多模态候选比较
3. `ffmpeg trim/concat/render`
4. 缩略图和关键帧生成
5. 预览缓存

补充说明：

1. `ASR/OCR` 未来可以作为辅助通道接入
2. 但当前不进入 `retrieve` 默认主路径，避免把工具契约绑死在暂不稳定的多信号融合策略上

这样分层的好处是：

1. `planner` 保持简洁
2. 工具契约保持稳定
3. 后端实现可以替换
4. 系统不会因为底层能力暴露过多而失控

---

## 7. 与其它层的关系

### 7.1 和 `Planner Layer` 的关系

`planner` 不直接操作底层媒体能力，而是选择并调用高层工具。

### 7.2 和 `State Layer` 的关系

工具执行前读取 `runtimeState`，执行后把结果回写：

1. `retrieve / inspect` 主要回写 `Retrieval State`
2. `patch` 主要回写 `Draft State`
3. `preview` 主要回写 `Draft State / Execution State`

### 7.3 和 `planner action schema` 的关系

动作层决定“调哪类工具”，工具层负责“把动作落成结果”。

例如：

1. `create_retrieval_request`
   - 进入 `retrieve`
2. `inspect_candidates`
   - 进入 `inspect`
3. `apply_patch`
   - 进入 `patch`
4. `render_preview`
   - 进入 `preview`

---

## 8. 当前阶段的必要性与充分性

### 8.1 必要性

没有这 5 类工具，系统就无法完成：

1. 找素材
2. 选素材
3. 改草案
4. 看结果

也就不可能形成真正工作的 `editing agent`。

### 8.2 充分性

只要这 5 类工具的契约稳定，当前阶段就已经足够支撑：

1. 全局粗剪
2. 局部替换
3. 局部 trim
4. 局部补素材
5. 预览迭代

不需要一开始就把：

1. 字幕
2. 调色
3. 特效
4. 音乐混音
5. 复杂时间轴轨道编辑

提升为一等工具。

---

## 9. 当前阶段的非目标

本文档明确不展开以下内容：

1. 各工具的字段级 schema
2. 多工具编排策略
3. 工具重试与幂等机制
4. 并发执行与任务队列
5. 具体底层实现选型
6. 导出级 `render` 契约

这些属于下一阶段细化工作。

---

## 10. 一句话结论

从第一性原理出发，当前 `Tool Layer` 的最小完备契约应当只包含：

`read / retrieve / inspect / patch / preview`

因为一个剪辑师要把脑内意图落成视频结果，最核心的外部操作也只有：

`读当前事实 -> 找候选 -> 判候选 -> 改草案 -> 看结果。`
