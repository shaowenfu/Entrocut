# EntroCut Agent Prompt Architecture & Context Assembly

本文档定义 EntroCut 的新一代 Agent Prompt Architecture（智能体提示词架构）与 Context Assembly（上下文编排）目标规格。

核心目标不是继续维护旧的 `planner_input JSON` 架构，而是从第一性原理出发，让 Agent 每轮只看到“足够决策的骨架事实”，再通过 Tool（工具）读取细节或执行动作。

## 0. 北极星目标

EntroCut Agent 的唯一职责是：

`把用户的自然语言剪辑意图，转成可验证、可执行、可回滚的结构化剪辑动作。`

因此 Prompt（提示词）设计必须满足以下约束：

1. 不倾倒全量 `EditDraft`。
2. 不要求模型输出 Chain of Thought（思维链）。
3. 不让模型伪造 Tool（工具）执行结果。
4. 不暴露旧 Runtime State（运行态集合）作为可读业务事实。
5. 所有 Tool Input（工具输入）和 Tool Output（工具输出）都采用必填字段。
6. 每轮 Planner Decision（规划决策）只表达两类结果：继续调用一个 Tool，或给用户最终回复。
7. Context Assembly（上下文编排）集中在一个 Context Assembler（上下文编排器）中完成，避免跨文件散落规则。

## 1. 非目标

本轮重构不做以下事情：

1. 不引入多层 Prompt Builder（提示词构建器）抽象。
2. 不保留 `planner_input.current_user_request / goal / scope / memory` 旧结构。
3. 不保留 `runtime_state` 作为 Agent 可查询入口。
4. 不保留 `reasoning_summary`、`tool_input_summary`、`draft_strategy`。
5. 不保留 `clip_alias`。
6. 不在 `retrieve` 中做视觉精判。
7. 不在 `inspect` 中做剪辑决策。
8. 不在 `patch` 中执行隐式默认动作。

## 2. Prompt Layout（提示词布局）

每次请求 LLM（大语言模型）时，Context Assembler（上下文编排器）生成一份完整 Prompt（提示词）。当前阶段可以统一作为单个 System Prompt（系统提示词）发送；后续可以将静态内容拆到 System Message（系统消息），将用户输入与动态上下文拆到 User Message（用户消息）。

完整 Prompt 严格按以下 5 个模块拼接：

1. System Context & Global State（系统设定与全局状态）
2. Chat History（对话历史）
3. Current Loop Observations（当前循环观测）
4. Available Tools（可用工具）
5. Strict JSON Output（严格 JSON 输出）

模块顺序不可调整。越靠后的模块对输出格式约束越强。

## 3. 数据事实模型

Prompt 中只允许引用以下业务事实：

### 3.1 Asset（资产）

原始媒体文件。

字段来源：

```text
AssetModel.id
AssetModel.name
AssetModel.duration_ms
AssetModel.type
AssetModel.source_path
AssetModel.lifecycle_state
AssetModel.processing_stage
AssetModel.vector_index_state
```

### 3.2 Clip（片段）

由 Asset（资产）切分得到的可检索媒体片段。

字段来源：

```text
ClipModel.id
ClipModel.asset_id
ClipModel.source_start_ms
ClipModel.source_end_ms
ClipModel.visual_desc
ClipModel.visual_description
ClipModel.semantic_tags
ClipModel.thumbnail_ref
```

### 3.3 Shot（镜头）

Timeline（时间线）上的最小剪辑单元，引用一个 Clip（片段）并声明实际使用的源时间范围。

字段来源：

```text
ShotModel.id
ShotModel.clip_id
ShotModel.source_in_ms
ShotModel.source_out_ms
ShotModel.order
ShotModel.enabled
ShotModel.label
ShotModel.intent
ShotModel.locked_fields
```

### 3.4 Scene（场景）

多个 Shot（镜头）的叙事组合。

字段来源：

```text
SceneModel.id
SceneModel.shot_ids
SceneModel.order
SceneModel.enabled
SceneModel.label
SceneModel.intent
SceneModel.locked_fields
```

### 3.5 Storyline（故事线）

Storyline（故事线）不是新数据表，而是从 Scene（场景）和 Shot（镜头）派生出的叙事骨架视图。

它回答：

1. 当前视频按什么顺序讲述？
2. 每个 Scene（场景）承担什么叙事功能？
3. Scene（场景）之间是否存在明显缺口、重复或顺序问题？

Storyline（故事线）只使用以下字段派生：

```text
SceneModel.id
SceneModel.order
SceneModel.label
SceneModel.intent
SceneModel.shot_ids
ShotModel.id
ShotModel.order
ShotModel.intent
ShotModel.label
```

Storyline（故事线）不包含 `visual_description`、`source_in_ms`、`source_out_ms` 等细节。需要细节时必须调用 `read`。

## 4. Context Assembler（上下文编排器）

新的上下文编排逻辑集中在一个 Context Assembler（上下文编排器）中。它只做字符串装配和事实裁剪，不做模型推理。

建议入口：

```python
def build_agent_prompt(
    *,
    user_prompt: str,
    edit_draft: EditDraftModel,
    chat_turns: list[ChatTurnModel],
    tool_observations: list[ToolObservationModel],
    selected_scene_id: str,
    selected_shot_id: str,
) -> str:
    ...
```

所有入参都应在调用前规范化为确定值。例如无选中 Scene（场景）时传 `"none"`，无选中 Shot（镜头）时传 `"none"`。

### 4.1 编排步骤

Context Assembler（上下文编排器）按以下顺序执行：

1. 读取当前 `EditDraftModel`。
2. 生成 Global TOC（全局目录），只包含 Scene（场景）和 Shot（镜头）骨架。
3. 生成 Storyline Digest（故事线摘要），只包含叙事意图。
4. 注入 Current Focus（当前焦点），来自用户请求目标或当前选中对象。
5. 注入 Current User Request（当前用户请求）。
6. 读取最近 5 轮 Chat History（对话历史）。
7. 读取本轮 Tool Observations（工具观测）。
8. 注入 Tool Contracts（工具契约）。
9. 注入 Output Contract（输出契约）。
10. 拼接为单个 Prompt（提示词）字符串。

### 4.2 动态 Prompt 拼接伪代码

```python
def build_agent_prompt(...):
    sections = [
        render_system_context_and_global_state(
            user_prompt=user_prompt,
            edit_draft=edit_draft,
            selected_scene_id=selected_scene_id,
            selected_shot_id=selected_shot_id,
        ),
        render_chat_history(chat_turns[-10:]),
        render_current_loop_observations(tool_observations),
        render_available_tools(),
        render_strict_json_output_contract(),
    ]
    return "\n\n".join(sections)
```

这里允许拆成 5 个私有渲染函数，但不允许继续拆出多层领域抽象。编排规则必须能在一个文件内读完。

### 4.3 Global TOC（全局目录）生成规则

Global TOC（全局目录）只回答“草稿结构是什么”，不回答“画面细节是什么”。

生成字段：

```text
draft_id
draft_version
scene_count
shot_count
selected_scene_id
selected_shot_id
scenes[].id
scenes[].order
scenes[].enabled
scenes[].label
scenes[].intent
scenes[].shot_ids
shots[].id
shots[].order
shots[].clip_id
shots[].enabled
shots[].label
shots[].intent
```

禁止注入：

```text
clips[].visual_description
clips[].visual_desc
clips[].semantic_tags
shots[].source_in_ms
shots[].source_out_ms
assets[].source_path
```

这些信息必须通过 `read` 工具按需读取。

### 4.4 Chat History（对话历史）生成规则

只保留最近 5 轮用户和 Assistant（助手）公开信息。

User（用户）轮次：

```text
User: <content>
```

Assistant（助手）轮次：

```text
Assistant: [tool: patch, preview] <assistant_reply>
```

历史数据迁移时应一次性补齐 `assistant_reply`。Prompt（提示词）运行时不得再读取旧推理摘要字段。

### 4.5 Current Loop Observations（当前循环观测）生成规则

Tool Observation（工具观测）是本轮 Agent Loop（智能体循环）的短期记忆。它只来自真实 Tool（工具）执行结果。

每条 Observation（观测）统一渲染：

```text
[Step N]
- tool_name: <read|retrieve|inspect|patch|preview>
- success: <true|false>
- summary: <summary>
- output: <compressed_json>
```

`output` 必须经过压缩，不允许直接塞入原始服务响应。

## 5. Production Static Prompt（生产级静态提示词）

以下内容属于静态 Prompt（提示词），可以长期放在 System Message（系统消息）中。

```text
你是 EntroCut Editing Agent（剪辑智能体）。

你的任务是把用户的自然语言剪辑意图转成结构化剪辑动作。你只修改 EditDraft（剪辑草稿），不直接处理底层媒体文件，不伪造渲染结果，不伪造视觉观察结果。

核心术语：
- Asset（资产）：原始媒体文件。
- Clip（片段）：Asset（资产）经过切分和索引得到的候选媒体片段。
- Shot（镜头）：Timeline（时间线）上的最小剪辑单元，引用一个 Clip（片段）并声明实际使用的源时间范围。
- Scene（场景）：多个 Shot（镜头）的叙事组合。
- Storyline（故事线）：Scene（场景）之间的叙事顺序与意图骨架。
- EditDraft（剪辑草稿）：当前项目的结构化剪辑配方。

决策原则：
1. 当前用户请求优先于历史对话。
2. Global TOC（全局目录）只提供结构骨架；涉及画面、时间切口、标签、素材细节时，必须调用 read。
3. 需要找新素材时调用 retrieve。
4. 需要确认一个已知 Clip（片段）的画面内容时调用 inspect。
5. 已有明确剪辑决策时调用 patch。
6. 需要让用户检查效果时调用 preview。
7. 不要猜测 Tool（工具）结果。
8. 不要输出 Markdown（标记语言）。
9. 不要输出解释性推理过程。
10. 每轮只能请求一个 Tool（工具）或给出一个 final（最终）回复。
```

## 6. Production Dynamic Prompt（生产级动态提示词）

以下模板由 Context Assembler（上下文编排器）每轮动态生成。

```text
=== 1. System Context & Global State（系统设定与全局状态） ===

Current User Request（当前用户请求）:
<user_prompt>

Current Focus（当前焦点）:
- selected_scene_id: <scene_id_or_none>
- selected_shot_id: <shot_id_or_none>

Global TOC（全局目录）:
- draft_id: <draft_id>
- draft_version: <version>
- scene_count: <scene_count>
- shot_count: <shot_count>
- scenes:
  - scene_id: <scene_id>
    order: <order>
    enabled: <true|false>
    label: <label_or_empty>
    intent: <intent_or_empty>
    shot_ids: [<shot_id>, ...]

Storyline Digest（故事线摘要）:
- scene_id: <scene_id>
  narrative_position: <order>
  intent: <intent_or_empty>
  shots:
    - shot_id: <shot_id>
      intent: <intent_or_empty>

=== 2. Chat History（对话历史） ===
<latest_5_rounds_or_empty>

=== 3. Current Loop Observations（当前循环观测） ===
<tool_observations_or_empty>

=== 4. Available Tools（可用工具） ===
<tool_contracts>

=== 5. Strict JSON Output（严格 JSON 输出） ===
<output_contract>
```

## 7. PlannerDecisionModel（规划决策模型）

新的 PlannerDecisionModel（规划决策模型）只保留决策执行所需字段。

必须删除：

```text
reasoning_summary
tool_input_summary
draft_strategy
```

目标模型：

```ts
type PlannerStatus = "requires_tool" | "final";
type ToolName = "read" | "retrieve" | "inspect" | "patch" | "preview";
type FocusTargetType = "project" | "scene" | "shot" | "clip";

interface PlannerFocus {
  target_type: FocusTargetType;
  target_id: string;
}

interface PlannerDecision {
  status: PlannerStatus;
  tool_name: ToolName | null;
  tool_input: object | null;
  assistant_reply: string | null;
  current_focus: PlannerFocus;
}
```

字段语义：

| 字段 | 规则 |
| :--- | :--- |
| `status` | 需要调用 Tool（工具）时为 `requires_tool`；任务完成或需要询问用户时为 `final`。 |
| `tool_name` | `status` 为 `requires_tool` 时必须是一个 ToolName（工具名）；`status` 为 `final` 时必须为 `null`。 |
| `tool_input` | `status` 为 `requires_tool` 时必须符合对应 Tool Input（工具输入）；`status` 为 `final` 时必须为 `null`。 |
| `assistant_reply` | `status` 为 `final` 时必须是给用户看的中文回复；`status` 为 `requires_tool` 时必须为 `null`。 |
| `current_focus` | 始终必填。无具体对象时使用 `{"target_type":"project","target_id":"project"}`。 |

## 8. Tool Contracts（工具契约）

所有 Tool Input（工具输入）和 Tool Output（工具输出）字段都必须必填。没有信息时使用明确空值语义，例如 `"none"`、`[]`、`0`、`false`，不要省略字段。

### 8.1 read

职责：按层级读取业务事实。

不读取 Runtime State（运行态集合），不读取 Tool Capability（工具能力），不返回原始全量草稿。

Input（输入）：

```ts
type ReadTargetType = "draft_tree" | "storyline" | "scene" | "shot" | "clip";

interface ReadInput {
  target_type: ReadTargetType;
  target_id: string;
}
```

`target_id` 规则：

| `target_type` | `target_id` |
| :--- | :--- |
| `draft_tree` | 固定传 `"root"` |
| `storyline` | 固定传 `"root"` |
| `scene` | 真实 `scene_id` |
| `shot` | 真实 `shot_id` |
| `clip` | 真实 `clip_id` |

Output（输出）：

```ts
interface ReadOutput {
  target_type: ReadTargetType;
  target_id: string;
  data: object;
}
```

`data` 结构由 `target_type` 决定：

```ts
interface DraftTreeData {
  draft_id: string;
  draft_version: number;
  scenes: Array<{
    scene_id: string;
    order: number;
    enabled: boolean;
    label: string;
    intent: string;
    shot_ids: string[];
  }>;
  shots: Array<{
    shot_id: string;
    order: number;
    enabled: boolean;
    clip_id: string;
    label: string;
    intent: string;
  }>;
}

interface StorylineData {
  scenes: Array<{
    scene_id: string;
    order: number;
    label: string;
    intent: string;
    shot_intents: Array<{
      shot_id: string;
      order: number;
      label: string;
      intent: string;
    }>;
  }>;
}

interface SceneData {
  scene_id: string;
  order: number;
  enabled: boolean;
  label: string;
  intent: string;
  duration_ms: number;
  shots: Array<{
    shot_id: string;
    order: number;
    clip_id: string;
    duration_ms: number;
    label: string;
    intent: string;
  }>;
}

interface ShotData {
  shot_id: string;
  clip_id: string;
  source_in_ms: number;
  source_out_ms: number;
  duration_ms: number;
  order: number;
  enabled: boolean;
  label: string;
  intent: string;
  locked_fields: string[];
}

interface ClipData {
  clip_id: string;
  asset_id: string;
  source_start_ms: number;
  source_end_ms: number;
  duration_ms: number;
  visual_desc: string;
  visual_description: string;
  semantic_tags: string[];
  thumbnail_ref: string;
}
```

### 8.2 retrieve

职责：从素材池召回候选 Clip（片段）。

`retrieve` 只做粗召回，不做最终选择。

Input（输入）：

```ts
interface RetrieveInput {
  query: string;
}
```

Output（输出）：

```ts
interface RetrieveOutput {
  query: string;
  candidates: Array<{
    clip_id: string;
    asset_id: string;
    score: number;
    source_start_ms: number;
    source_end_ms: number;
    visual_desc: string;
    semantic_tags: string[];
  }>;
}
```

### 8.3 inspect

职责：调用 VLM（多模态大模型）观察一个已知 Clip（片段）。

`inspect` 不负责比较、排序、选择或生成 Patch（补丁）。

Input（输入）：

```ts
interface InspectInput {
  clip_id: string;
  inspection_goal: string;
}
```

Output（输出）：

```ts
interface InspectOutput {
  clip_id: string;
  inspection_goal: string;
  visual_description: string;
  uncertainty: string;
  evidence_frame_count: number;
}
```

### 8.4 patch

职责：把明确剪辑决策写入 EditDraft（剪辑草稿）。

本阶段只支持三种能力：

1. `insert_shot`
2. `replace_shot`
3. `delete_shot`

Input（输入）：

```ts
type PatchOperation =
  | {
      op: "insert_shot";
      scene_id: string;
      index: number;
      clip_id: string;
      source_in_ms: number;
      source_out_ms: number;
      intent: string;
    }
  | {
      op: "replace_shot";
      shot_id: string;
      clip_id: string;
      source_in_ms: number;
      source_out_ms: number;
      intent: string;
    }
  | {
      op: "delete_shot";
      shot_id: string;
      deletion_reason: string;
    };

interface PatchInput {
  operations: PatchOperation[];
}
```

Patch（补丁）规则：

1. `operations` 至少包含 1 个操作。
2. 不知道 `source_in_ms` / `source_out_ms` 时，先调用 `read` 或 `inspect`，不要编造。
3. `scene_id`、`shot_id`、`clip_id` 必须是真实 ID；当草稿没有任何 Scene（场景）时，`insert_shot.scene_id` 传 `"root"`，系统创建默认 Scene（场景）后插入 Shot（镜头）。
4. `delete_shot` 只删除 Shot（镜头），不删除 Clip（片段）或 Asset（资产）。
5. `replace_shot` 保持原 Shot（镜头）的 Timeline（时间线）位置，只替换引用与源时间范围。

Output（输出）：

```ts
interface PatchOutput {
  draft_id: string;
  draft_version: number;
  applied_operations: Array<{
    op: "insert_shot" | "replace_shot" | "delete_shot";
    target_id: string;
    result: "applied";
  }>;
}
```

### 8.5 preview

职责：根据当前 EditDraft（剪辑草稿）生成预览。

Input（输入）：

```ts
interface PreviewInput {
  reason: string;
}
```

Output（输出）：

```ts
interface PreviewOutput {
  draft_id: string;
  draft_version: number;
  output_url: string;
  duration_ms: number;
}
```

## 9. Available Tools（可用工具）动态渲染

Tool Contract（工具契约）始终完整注入。该模块必须解释每个 Tool（工具）的作用、工作原理、调用时机和禁止调用场景。

不要在 Prompt（提示词）中注入 `enabled / disabled`、`can_retrieve`、`can_patch` 等能力布尔值；这些是程序侧 Gate（门控）逻辑，不是 Agent 的业务上下文。若程序侧能力不足，应在执行前由后端拦截并返回稳定错误，或在 UI（用户界面）侧阻止发起对应任务。

## 10. 严格输出规范

每次 LLM（大语言模型）必须只输出一个合法 JSON Object（JSON 对象）。

禁止：

1. Markdown（标记语言）。
2. Code Fence（代码围栏）。
3. 额外解释文本。
4. Chain of Thought（思维链）。
5. 缺字段。
6. 多 Tool（工具）调用。
7. 字符串化 JSON。

输出示例：调用 `read`。

```json
{
  "status": "requires_tool",
  "tool_name": "read",
  "tool_input": {
    "target_type": "scene",
    "target_id": "scene_01"
  },
  "assistant_reply": null,
  "current_focus": {
    "target_type": "scene",
    "target_id": "scene_01"
  }
}
```

输出示例：调用 `patch`。

```json
{
  "status": "requires_tool",
  "tool_name": "patch",
  "tool_input": {
    "operations": [
      {
        "op": "replace_shot",
        "shot_id": "shot_01",
        "clip_id": "clip_88",
        "source_in_ms": 0,
        "source_out_ms": 4000,
        "intent": "用大海镜头替换开场，建立开阔氛围"
      }
    ]
  },
  "assistant_reply": null,
  "current_focus": {
    "target_type": "shot",
    "target_id": "shot_01"
  }
}
```

输出示例：最终回复。

```json
{
  "status": "final",
  "tool_name": null,
  "tool_input": null,
  "assistant_reply": "我已经把开场替换成大海镜头，并保持了原来的开场位置。你现在可以预览效果。",
  "current_focus": {
    "target_type": "shot",
    "target_id": "shot_01"
  }
}
```

## 11. 推荐执行流

### 11.1 替换开场镜头

1. 用户：“把开头换成一个大海的镜头。”
2. Prompt（提示词）中只有 Global TOC（全局目录），没有第一个 Shot（镜头）的时间细节。
3. Agent 调用 `read(scene_01)`。
4. Agent 调用 `retrieve("大海 开阔 开场")`。
5. Agent 调用 `inspect(clip_id, "判断该片段是否适合作为开场大海镜头，关注主体、景别、稳定性、情绪")`。
6. Agent 调用 `patch(replace_shot)`。
7. Agent 返回 `final`。

### 11.2 新增结尾镜头

1. 用户：“最后加一个日落收尾。”
2. Agent 调用 `read(storyline, root)` 理解结尾叙事位置。
3. Agent 调用 `retrieve("日落 收尾 安静 远景")`。
4. Agent 调用 `inspect` 确认画面。
5. Agent 调用 `patch(insert_shot)` 插入最后一个 Scene（场景）的末尾。
6. Agent 返回 `final`。

### 11.3 删除重复镜头

1. 用户：“删掉中间重复的镜头。”
2. Agent 调用 `read(storyline, root)` 找到可能重复的叙事段。
3. Agent 调用 `read(scene_id)` 查看该段 Shot（镜头）列表。
4. Agent 调用 `read(shot_id)` 确认目标 Shot（镜头）。
5. Agent 调用 `patch(delete_shot)`。
6. Agent 返回 `final`。

## 12. 迁移判断标准

完成重构后，应满足：

1. Planner Request（规划请求）不再包含旧 `planner_input JSON`。
2. Prompt（提示词）由单个 Context Assembler（上下文编排器）集中生成。
3. `PlannerDecisionModel` 不再包含 `reasoning_summary`、`tool_input_summary`、`draft_strategy`。
4. `inspect` 不再接受 `clip_alias`、`question`、`task_summary`。
5. `patch` 支持 `insert_shot`、`replace_shot`、`delete_shot`。
6. `read` 支持 `draft_tree`、`storyline`、`scene`、`shot`、`clip`。
7. `runtime_state` 不再作为 Agent Prompt（智能体提示词）或 Tool（工具）的业务上下文来源。
8. 所有 Tool Input（工具输入）和 Tool Output（工具输出）都有确定字段。
9. 测试覆盖 Prompt（提示词）装配、Tool Contract（工具契约）、Planner Decision（规划决策）解析和旧字段清理。
