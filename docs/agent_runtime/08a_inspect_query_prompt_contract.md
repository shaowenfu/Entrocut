# Inspect Query / Prompt Contract

本文档定义 `inspect` 工具内部面向 `VLM（多模态大模型）` 的 `query / prompt contract（问题与提示词契约）`。

它回答的问题不是：

`怎么让模型自由描述看到了什么`

而是：

`planner（大脑）` 应该怎样向 `inspect（眼睛）` 提问，`inspect` 又应该怎样把视觉判断稳定回传给 `planner`。

---

## 1. 第一性原理

`inspect` 的职责不是全量理解视频，也不是替 `planner` 做完整编排。

它只负责一件事：

`围绕当前检索假设，对少量候选做局部视觉判定。`

所以它的输入不应该是开放式“你看到了什么”，而应该是：

1. 当前要解决的局部编辑问题
2. 当前候选为什么会被召回
3. 这次具体要比较、验证还是选择什么
4. 结果要以什么结构返回

一句话：

`inspect` 是问题驱动的视觉判定器，不是自由描述器。

---

## 2. 为什么需要单独定义 Query / Prompt Contract

如果不单独定义，系统通常会退化成两种坏形态：

1. `planner` 发出过宽问题
   - “你看到了什么”
   - “这个视频怎么样”
   - 结果是输出发散、成本高、信息密度低

2. `inspect` 返回自由文本
   - `planner` 很难把结果继续映射成 `patch`
   - 结果难缓存、难比对、难回放

因此必须把这层关系固定成：

`inspection hypothesis -> inspection question -> structured observation`

---

## 3. 设计目标

当前阶段，`inspect query / prompt contract` 只追求 4 件事：

1. 让 `planner` 能稳定提问
2. 让 `inspect` 能稳定回答
3. 让回答能继续进入 `PlannerOutput / EditDraftPatch`
4. 让这套机制支持并行、多候选、小步快跑

它不负责：

1. 承载完整视频理解
2. 生成长篇画面描述
3. 替代 `retrieve`
4. 承载开放式创作讨论

---

## 4. 核心原则

### 4.1 问题驱动，不做自由描述

默认不要问：

1. “你看到了什么”
2. “这个视频怎么样”
3. “整体感觉如何”

优先问：

1. `verify（验证）`
2. `compare（比较）`
3. `choose（选择）`
4. `rank（排序）`

### 4.2 围绕检索假设提问

`inspect` 的问题必须显式绑定当前 `retrieval hypothesis（检索假设）`。

例如：

1. 当前缺口：旅行视频开头
2. 当前假设：出发前整理行李 / 走向车站
3. 当前问题：哪个候选更像“旅程开始”，而不是“旅途中间”

### 4.3 面向决策，不面向散文

`inspect` 的输出必须服务后续动作：

1. 进入候选重排
2. 进入最终选择
3. 进入 `patch`
4. 进入下一轮更细问题

所以输出必须结构化、短、可验证。

### 4.4 少量候选优先于大规模候选

`inspect` 应处理小规模候选集。

推荐：

1. `compare`: 2 个
2. `choose`: 3~5 个
3. `rank`: 最多 5~8 个
4. `verify`: 1 个

超过这个规模，先回到 `retrieve` 或候选池压缩，不要把 `inspect` 变成大规模看片工具。

---

## 5. 四类标准问题

### 5.1 `verify`

作用：

验证单个候选是否满足某个明确假设。

适用场景：

1. 判断是否包含某个动作
2. 判断是否更像开头/结尾/转场
3. 判断是否存在某个视觉问题

示例：

`这个候选是否包含明确的“准备出门 / 收拾行李”动作？`

### 5.2 `compare`

作用：

比较两个候选在某个具体维度上的优劣。

适用场景：

1. A 和 B 哪个更像“旅程开始”
2. A 和 B 哪个更适合替换当前 `shot`
3. A 和 B 哪个构图更干净

示例：

`比较 clip_a 和 clip_b，哪个更适合作为旅行视频开头的出发镜头？`

### 5.3 `choose`

作用：

从一小组候选里选出最优项。

适用场景：

1. 候选数不多，但需要直接落草案
2. `planner` 不想再做额外轮次比较

示例：

`在这 4 个候选里，选出最适合当前 opening scene 的一个。`

### 5.4 `rank`

作用：

对候选按某个标准排序，保留后续决策空间。

适用场景：

1. 需要把候选压缩成 top-3
2. 暂时不想直接选唯一结果

示例：

`按“更有出发感”对这 5 个候选排序。`

---

## 6. 标准输入结构

`inspect` 面向 `VLM` 的问题，不应只是一个 `question: string`。

推荐最小结构：

```ts
type InspectionQuestionType = "verify" | "compare" | "choose" | "rank";

interface InspectionHypothesis {
  summary: string;
  target_gap?: string | null;
}

interface InspectionCriterion {
  name: string;
  description: string;
}

interface InspectPromptContract {
  question_type: InspectionQuestionType;
  task_summary: string;
  hypothesis: InspectionHypothesis;
  question: string;
  criteria: InspectionCriterion[];
  candidates: Array<{
    clip_id: string;
    asset_id: string;
    summary?: string | null;
    frame_refs?: string[];
  }>;
  output_schema: "inspection_observation_v1";
}
```

### 6.1 字段说明

1. `question_type`
   - 限定问题类型，避免开放式漂移

2. `task_summary`
   - 当前局部任务摘要
   - 例如：`为 opening scene 找一个更有出发感的镜头`

3. `hypothesis`
   - 当前检索假设
   - 例如：`旅程开始通常表现为收拾行李、走向车站、交通工具启动`

4. `question`
   - 当前要模型回答的具体问题

5. `criteria`
   - 当前判定标准
   - 不要太多，建议 1~3 条

6. `candidates`
   - 候选引用和必要证据

7. `output_schema`
   - 明确要求按固定结构返回

---

## 7. 标准输出结构

推荐输出不要超过这个粒度：

```ts
interface InspectionObservation {
  question_type: "verify" | "compare" | "choose" | "rank";
  selected_clip_id?: string | null;
  ranking?: string[];
  candidate_judgments: Array<{
    clip_id: string;
    verdict: "match" | "partial_match" | "mismatch";
    confidence?: number | null;
    short_reason: string;
  }>;
  uncertainty?: string | null;
}
```

### 7.1 为什么这样设计

1. `selected_clip_id`
   - 让 `planner` 可以直接进入下一步 `patch`

2. `ranking`
   - 保留后续继续筛选空间

3. `candidate_judgments`
   - 每个候选都必须有局部判定，方便回放和缓存

4. `short_reason`
   - 只保留决策理由，不要长篇视觉描述

5. `uncertainty`
   - 明确告诉 `planner` 当前还不确定什么

---

## 8. Prompt 组织原则

### 8.1 先给任务，再给候选

正确顺序：

1. 当前任务是什么
2. 当前假设是什么
3. 当前问题是什么
4. 当前标准是什么
5. 再给候选材料
6. 最后强调输出 schema

### 8.2 标准要短，不要多

不要给 7~8 条标准。

当前阶段建议只给：

1. 最关键的目标标准
2. 1~2 条辅助标准

否则 `inspect` 会过拟合提示词，而不是稳定判断。

### 8.3 候选材料只给必要证据

不要把整段素材、全量聊天历史、整份 `EditDraft` 都塞进 `inspect`。

只给：

1. 当前候选的关键帧
2. 候选摘要
3. 当前假设与判定标准

### 8.4 输出必须强约束

明确要求：

1. 只返回 JSON
2. 不要 markdown
3. 不要额外解释
4. 不要输出 schema 之外字段

---

## 9. 示例

### 9.1 `choose`

```json
{
  "question_type": "choose",
  "task_summary": "为旅行视频 opening scene 选一个更有出发感的镜头",
  "hypothesis": {
    "summary": "旅程开始通常表现为整理行李、离开住处、走向车站或交通工具启动",
    "target_gap": "opening scene"
  },
  "question": "在以下候选中，选出最适合作为旅行视频开头的出发镜头。",
  "criteria": [
    {
      "name": "departure_feel",
      "description": "候选是否明确传达旅程刚开始的感觉，而不是旅途中段。"
    },
    {
      "name": "visual_clarity",
      "description": "主体动作是否清楚，画面是否足够容易被快速理解。"
    }
  ],
  "candidates": [
    {
      "clip_id": "clip_12",
      "asset_id": "asset_a",
      "summary": "人物在床边整理背包",
      "frame_refs": ["frame://clip_12/1", "frame://clip_12/2"]
    },
    {
      "clip_id": "clip_31",
      "asset_id": "asset_b",
      "summary": "列车窗外快速移动的风景",
      "frame_refs": ["frame://clip_31/1", "frame://clip_31/2"]
    }
  ],
  "output_schema": "inspection_observation_v1"
}
```

### 9.2 `verify`

```json
{
  "question_type": "verify",
  "task_summary": "验证候选是否满足开头需要的准备出发动作",
  "hypothesis": {
    "summary": "当前缺少一个明确表现出发前准备状态的镜头"
  },
  "question": "这个候选是否包含明确的收拾行李或准备出门动作？",
  "criteria": [
    {
      "name": "pre_departure_action",
      "description": "是否存在可见且明确的准备出门动作。"
    }
  ],
  "candidates": [
    {
      "clip_id": "clip_8",
      "asset_id": "asset_c",
      "summary": "人物站在门边穿外套",
      "frame_refs": ["frame://clip_8/1", "frame://clip_8/2"]
    }
  ],
  "output_schema": "inspection_observation_v1"
}
```

---

## 10. 与其它层的关系

### 10.1 与 `retrieval hypothesis`

`inspect question` 不是凭空生成的，而是对当前检索假设的判定化表达。

也就是：

`retrieval hypothesis -> inspection question`

### 10.2 与 `InspectToolRequest`

`InspectToolRequest` 是外层工具契约。  
本文档定义的是它内部真正送入 `VLM` 的问题结构。

### 10.3 与 `PlannerOutput`

`inspect` 返回的 `InspectionObservation` 不是最终动作。  
它会被 `planner` 继续吸收，再决定：

1. `apply_patch`
2. 继续 `inspect`
3. 回到 `retrieve`
4. 向用户澄清

---

## 11. 当前阶段的非目标

1. 不做开放式“你看到了什么”视觉描述
2. 不让 `inspect` 替代 `retrieve`
3. 不让 `inspect` 处理大规模候选池
4. 不让 `inspect` 直接生成 `EditDraftPatch`
5. 不让 `inspect` 负责审美创作决策全链路

---

## 12. 一句话结论

`inspect query / prompt contract` 的本质，是把“检索假设驱动的局部视觉判断”固定成“有限问题类型 + 少量候选 + 强约束结构化输出”的稳定通信协议。`
