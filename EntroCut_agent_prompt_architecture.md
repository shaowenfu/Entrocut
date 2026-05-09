# EntroCut Agent Prompt Architecture & Context Assembly

基于第一性原理，本项目的 Agent 提示词摒弃了传统的“全量状态倾倒”和“冗长思维链（Chain of Thought）”，转而采用**“大纲字典 + 结构化检索 + 纯动作输出”**的设计哲学。

本文档详细定义了每次发给大模型的完整 Prompt 结构、数据来源映射，以及配套的工具重构方案。

---

## 1. 提示词整体装配结构 (Prompt Layout)

每次请求大模型时，System Prompt 由以下 5 个模块严格按顺序拼接而成：

1. **系统设定与当前全局状态** (System Context & Global State)
2. **对话历史** (Chat History)
3. **当前执行过程** (Current Loop Observations)
4. **工具定义** (Available Tools)
5. **严格输出规范** (Strict JSON Output)

---

## 2. 逐块解析与生产级 Prompt 示例

### 模块 1: 系统设定与当前全局状态

**数据来源 (Data Source)**：
- **概念定义**：静态硬编码。
- **全局大纲 (TOC)**：来自 `core/main.py` 或 `store` 中的 `record["edit_draft"]`。仅提取 `Scene` 列表及其包含的 `Shot` 计数与意图，绝不暴漏具体的 `in_point/out_point` 和画面特征。
**生产级 Prompt (含示例数据)**：
```text
=== 1. 系统设定与当前全局状态 (System Context & Global State) ===
【系统术语与工作边界】
- 你是专业的视频剪辑 Agent。你的修改仅作用于结构化的 JSON 草稿，底层有物理引擎负责渲染。
- Asset (资产): 原始媒体文件（如一段 1 小时的原片）。
- Clip (片段): Asset 使用场景切分算法得到的在物理时间上的逻辑切片，包含视觉描述(visual_description)和语义标签(semantic_tags)。
- Shot (镜头): 由多个clip组成的时间线上的最小剪辑单元，包含时间切口(in/out_point)并引用 clip_id。
- Scene (场景): 多个 Shot 的逻辑组合，代表一个叙事段落，包含意图(intent)。
- EditDraft (草稿): 包含所有 Scene 顺序的全局配方，形成一个完整的视频。
- Storyline (故事线): 场景之间的叙事关系和时间线顺序，是草稿的核心骨架。

【当前全局大纲 (Global TOC)】
- 概况: 当前草稿共 3 个 Scene, 8 个 Shot。
- 骨架:
  [scene_01] 意图: "男主走进房间", 包含 shot_01, shot_02
  [scene_02] 意图: "发现桌上的信", 包含 shot_03
  [scene_03] 意图: "跑出大门", 包含 shot_04, shot_05, shot_06

【当前焦点 (Current Focus)】
- target: scene_03
- 状态说明: 用户的指令或你之前的动作主要集中于此。

注：以上仅为骨架。当你需要修改某个镜头，或想知道某个 shot/clip 的具体细节时，必须使用 `read` 工具查询明细。
```

### 模块 2: 对话历史 (Chat History)

**数据来源 (Data Source)**：
- 来自数据库或内存中的 `record["chat_turns"]`。
- **处理规则**：仅取最新 5 轮。对于 Assistant 的回复，**剥离其内部调用的冗余工具 JSON**，仅提取向用户公开的 `assistant_reply`，若调用了工具可增加中括号标记。

**生产级 Prompt (含示例数据)**：
```text
=== 2. 对话历史 (Chat History) ===
以下是你与用户最近的交流记录。请结合历史语境理解最新指令：

User: 帮我把前三个镜头连起来，做一个 15 秒的开场。
Assistant: [patch] [preview] 好的，我已经为您将开场的三个镜头按顺序排列并修剪到了 15 秒，您可以查看预览。

User: 这样好多了。现在帮我选一个适合结尾的片段。
Assistant: [retrieve] [inspect] 我觉得 clip_305 最适合用作结尾，需要我帮您加入到草稿中吗？

User: 好的，直接加在最后面吧。
```

### 模块 3: 当前执行过程 (Current Loop Observations)

**数据来源 (Data Source)**：
- 来自 `_run_chat_agent_loop` 循环内部的 `observations: list[ToolObservationModel]` 列表。
- **处理规则**：这是 Agent 的**短期工作记忆**。如果本轮尚未调用工具，则输出“暂无”。如果已调用，提取每个 `Observation` 的核心字段，并根据工具类型附带关键的结构化数据（如检索得分、修改前后的状态差）。

**生产级 Prompt (含多种工具示例数据)**：
```text
=== 3. 当前执行过程 (Current Loop Observations) ===
为了响应用户的最新请求，你在本次思考内部已经自动执行了以下步骤：

[Step 1]
- 动作: read
- 状态: SUCCESS
- 摘要: 读取了 scene_03 的镜头明细。
- 数据: {"shots": [{"id": "shot_06", "clip_id": "clip_21"}]}

[Step 2]
- 动作: retrieve
- 状态: SUCCESS
- 摘要: 成功根据关键词 "日落 海边" 检索到候选素材。
- 数据: {
    "candidates": [
      {"clip_id": "clip_305", "match_score": 0.92, "tags": ["日落", "海边", "远景"]},
      {"clip_id": "clip_112", "match_score": 0.85, "tags": ["日落", "城市", "中景"]}
    ]
  }

[Step 3]
- 动作: patch
- 状态: SUCCESS
- 摘要: 成功将 clip_305 作为一个新的 Shot 插入到 scene_03 的末尾。
- 数据: {"new_shot_id": "shot_07", "draft_version": 4}

请基于上述结果决定下一步行动。
```

### 模块 4: 工具定义 (Available Tools)

**数据来源 (Data Source)**：
- 静态硬编码。直接提供 JSON 契约。

**生产级 Prompt (片段)**：
```text
=== 4. 工具定义 (Available Tools) ===
你拥有 5 个操作系统的核心工具。在你每一轮的回复中，当你决定采取行动时，你必须在你的 JSON 输出中提供 tool_name 和 tool_payload 字段。系统会自动拦截你的输出并执行工具。注意：你不能自己凭空编造结果，你必须通过 tool_payload 严格按下方定义的格式传入参数。
1. read 按需查询剪辑树的指定层级明细。
tool_payload 参数定义：{"target_type": "draft_tree"|"scene"|"shot"|"clip", "target_id": "string"}
2. retrieve 原理是通过多模态检索，使用文本 query 召回视频片段。作用是从整个素材库中快速找到潜在 clip。只用于粗略素材查找，后续可配合 inspect 深入理解。
tool_payload 参数定义：
{
   "query": "string"  // 必填。描述你要找什么的自然语言，例如 "海边日落，暖色调"
}
3. inspect 原理是调用 VLM（多模态大模型） 看一个已知 clip 的画面。作用是作为 Agent 的“眼睛”，输出视觉描述并绑定到对应 clip。不负责比较、排序、选择或剪辑决策。
tool_payload 参数定义：
{
   "clip_id": "string",      // 目标 clip 的真实 ID
   "inspection_goal": "string",     // 你希望视觉模型观察什么
}
4. patch 原理是把明确的剪辑决策写入 EditDraft（剪辑草案）。作用是将选中的 clip 插入草案或更新草案结构。只在已经有明确编辑决策时使用。
tool_payload 参数定义：
{
   "clip_id": "string",  // 要写入草案的 clip ID
   "intent": "string"   // 该 clip 在剪辑中的用途说明
}
5. preview 原理是根据当前 EditDraft（剪辑草案） 渲染预览文件。作用是让用户检查当前剪辑效果。只在草案已有可预览
   结构后使用。
tool_payload 参数定义：
{
   "reason": "string"  // 选填。生成预览的原因
}
```

### 模块 5: 严格输出规范 (Strict JSON Output)

**数据来源 (Data Source)**：
- 静态硬编码。**去除了易引起幻觉的 `reasoning_summary`，强制用纯净状态表述决策。同时强制 Agent 维护焦点。**

**生产级 Prompt**：
```text
=== 5. 严格输出规范 (Strict JSON Output) ===
必须且只能输出一个合法的 JSON 对象，禁止任何 Markdown 标记(如 ```json)或额外文本。如果不符合格式，系统将直接崩溃。

你的输出必须严格符合以下 TypeScript 接口定义：
interface PlannerDecision {
  // 如果需要继续执行工具获取信息或修改草稿，填 "requires_tool"
  // 如果任务已完成或需要询问用户，填 "final"
  "status": "requires_tool" | "final";
  
  // 必须与 status 匹配。若是 requires_tool 填具体的工具名；若是 final 填 null。
  "tool_name": "read" | "retrieve" | "inspect" | "patch" | "preview" | null;
  
  // 工具参数。严格参照【模块 4】定义。若 tool_name 为 null 则填 null。
  "tool_payload": object | null;
  
  // 若 status 为 "final"，这里填你要对用户说的话；否则填 null。
  "assistant_reply": string | null;
  
  // 给出当前任务的明确焦点及大体方向（如某个 scene_id 或 shot_id）。这有助于系统理解你的决策上下文，并在下一轮继续保持对焦。
  // 若无明确焦点或处于全局探索期，填 "none"。这将作为下一轮或下一步的上下文。
  "current_focus": string;
}
```

---

## 3. `read` 工具重构方案 (Hierarchical Query)

既然我们把传入大模型的 `EditDraft` 缩减成了大纲骨架，`read` 工具就必须承担起**“高精度显微镜”**的职责。它需要被重构为一个支持**层级化查询**的接口。

### 3.1 核心思想
`read` 工具不再一股脑返回整个庞大的系统状态，而是通过 `target_type` 和 `target_id` 精确获取所需的细粒度数据。

### 3.2 路由与输出规范

| `target_type` | `target_id` 要求 | 返回的结构化数据 (Observation Output) | 适用场景举例 |
| :--- | :--- | :--- | :--- |
| `draft_tree` | 不需要 | 完整草稿的层级树（去除非关键属性）。 | Agent 失去大局观，想看完整时间线顺序。 |
| `scene` | 必须传入 `scene_id` | 包含该 scene 的 `intent`、总时长，以及其下所有 `shot` 的列表（含每个 shot 引用的 `clip_id` 和长度）。 | 用户要求“改一下这个场景”，Agent 需要知道它现在由哪些镜头构成。 |
| `shot` | 必须传入 `shot_id` | 该 shot 的 `source_in_ms`, `source_out_ms`, 绑定的 `clip_id` 以及锁定状态。 | 用户要求“把这个镜头剪短两秒”，Agent 需要知道当前出入点是多少。 |
| `clip` | 必须传入 `clip_id` | 该 clip 对应的原视频信息，极其重要的 `visual_description` (画面详述)，以及 `semantic_tags`。 | Agent 在 `patch` 之前，想确认这个 clip 的画面内容是否真的符合要求。 |

### 3.3 示例执行流
1. 用户输入：“把开头换成一个大海的镜头”。
2. Agent 看到 **大纲**：开场是 `scene_01`。
3. Agent 看到 **焦点**：用户未选中，自行推断修改目标是 `scene_01` 的第一个 shot。
4. Agent 思考：我需要先知道 `scene_01` 目前有什么。
   - 输出：`{"status": "requires_tool", "tool_name": "read", "tool_payload": {"target_type": "scene", "target_id": "scene_01"}, "assistant_reply": null}`
5. 系统执行返回 Observation：`{"shots": [{"id": "shot_01", "clip_id": "clip_22"}]}`
6. Agent 收到反馈，继续思考：找素材。
   - 输出：`{"status": "requires_tool", "tool_name": "retrieve", "tool_payload": {"query": "大海"}, "assistant_reply": null}`
7. 系统执行返回 Observation：找到 `clip_88`。
8. Agent 继续思考：用 `patch` 替换 `shot_01` 的素材。
   - 输出：`{"status": "requires_tool", "tool_name": "patch", "tool_payload": {"action": "replace", "target_id": "shot_01", "clip_id": "clip_88"}, "assistant_reply": null}`
9. Agent 返回给用户：
   - 输出：`{"status": "final", "tool_name": null, "tool_payload": null, "assistant_reply": "我已经把开场替换成了大海的镜头，您可以预览一下效果。", "current_focus": "shot_01"}`

---

## 4. 工具实现的改进思路

基于以上规范，各工具的内部实现逻辑需要进行如下强化：

### 4.1 Patch 工具
**改进点：引入精准的作用域与占位符规范**
- **统一 Action 接口**：目前的 Patch Payload 已经被强制规范为包含 `action`, `target_id`, `clip_id` 和 `index`。
- **插入与删除逻辑**：
  - 当 action 为 `insert` 时，`target_id` 指向 Scene ID，`index` 决定在哪个位置插入新的 Shot。
  - 当 action 为 `remove` 时，`target_id` 指向 Shot ID 或 Scene ID 即可，`clip_id` 和 `index` 传入 "none" / -1。
- **实现建议**：后端接收到 Payload 后，需做前置校验（如 `index` 是否越界、引用的 `clip_id` 是否真实存在）。

### 4.2 Retrieve 工具
**改进点：丰富观测上下文**
- **返回结果冗余压缩**：不能直接把 DashVector 返回的 Raw JSON 丢进 Prompt。
- **实现建议**：后端组装 Observation 时。每个候选强制拼装出结构：`[{"clip_id": "xxx", "match_score": 0.95, "tags": [...]}]`，这样 Agent 就能直观感受到搜索匹配度。
