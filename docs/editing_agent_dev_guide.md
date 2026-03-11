# Editing Agent 开发指南

本文档是精简版，用于直接指导接下来的 `editing agent（剪辑智能体）` 开发。

如果要看设计推导、取舍和讨论细节，请看：

- [Editing Agent 详细设计](./editing_agent_design_detailed.md)

---

## 1. 核心原则

1. 事实源是 `EditDraft`，不是 `Storyboard`
2. `shot` 是最小可编辑语义单元
3. `scene` 是可选工作分组层，不是必选层
4. `render` 以 `shots` 为最终执行输入
5. `agent` 的标准输出应是 `EditDraftPatch`
6. 系统走 `retrieval-first（检索优先）` 路线，不做全量深理解

---

## 2. 系统分层

### 2.1 World Model（世界模型）

必须稳定的核心对象：

1. `Asset`
2. `Clip`
3. `Shot`
4. `Scene`
5. `EditDraft`

### 2.2 Agent Layers（智能体分层）

1. `Perception Layer`
   - 提取低成本元信息
   - 建立粗索引
2. `Planner Layer`
   - 理解用户意图
   - 生成检索假设和编辑计划
3. `Tool Layer`
   - 检索、裁剪、替换、重排、导出
4. `Validation Layer`
   - 只做硬约束和结构校验

---

## 3. 先做什么，不先做什么

### 3.1 先做

1. `retrieval request schema`
2. `candidate clip schema`
3. `EditDraftPatch schema`
4. `selection/context schema`
5. `planner -> retrieval -> patch` 最小闭环

### 3.2 不先做

1. 不做全量 `clip` 深理解
2. 不做固定叙事模板
3. 不做以 `timeline` 为中心的交互
4. 不做“全程由多模态大模型直接看片决策”的主链路
5. 不做自动审美评分系统

---

## 4. 检索策略

### 4.1 三层索引

1. `Asset-level coarse index`
   - ASR
   - OCR
   - 稀疏帧 caption
   - 基础 tag
   - 时间采样帧 embedding
2. `Segment-level candidate index`
   - 文本 embedding
   - 图像 embedding
   - 结构化 tag / metadata
3. `Candidate deep understanding`
   - 只对候选片段做更贵理解
   - 必须缓存

### 4.2 检索流程

1. `planner` 生成 `retrieval hypothesis`
2. 输出：
   - `semantic query`
   - `retrieval constraints`
3. 执行：
   - `hard filter`
   - `broad recall`
   - `rerank`
   - `sufficiency check`
4. 不够就扩召或换假设

### 4.3 检索原则

1. 主系统用多路检索，不只用纯向量
2. 融合必须分阶段，不能一开始乱加权
3. 先保证召回，再做重排
4. 先用便宜信号，后用昂贵理解

---

## 5. 用户决策与 Agent 决策边界

### 5.1 必须尽量由用户提供

1. 视频目的
2. 目标受众
3. 总时长
4. 必须出现/禁止出现的内容
5. 风格偏好与硬约束

### 5.2 Agent 可以默认补全

1. 开头怎么切入
2. 中间如何组织
3. 结尾如何收束
4. 具体选哪个近似候选
5. 微小 trim（裁剪）和局部重排

### 5.3 何时需要澄清

1. 目标不清
2. 约束冲突
3. 候选不足
4. 多种方案差异大且无法自行取舍
5. 会影响整体方向

原则：

`minimum clarification（最小澄清）`

---

## 6. 多模态模型怎么用

1. `planner` 默认走文本推理
2. 候选级深理解优先生成可缓存文本描述
3. 复杂视觉歧义再按需调用多模态
4. 不把多模态基座当默认全流程 planner

适合调用多模态的场景：

1. 表情自然度比较
2. 遮挡判断
3. 画面质感比较
4. 难以从摘要判断的视觉细节

---

## 7. 交互上下文

必须尽快稳定的上下文状态：

1. `selected_scene_id`
2. `selected_shot_id`
3. 当前是否为全局编辑还是局部编辑
4. 用户锁定了哪些字段

原因：

没有这些上下文，局部编辑几乎无法可靠落地。

---

## 8. 近期实现优先级

### 第一优先级

1. 定义 `EditDraftPatch schema`
2. 定义 `retrieval request schema`
3. 定义 `selection/context schema`

### 第二优先级

1. 让前端交互真正接入 `selected_scene_id / selected_shot_id`
2. 让 `chat` 请求携带局部目标上下文

### 第三优先级

1. 实现检索优先主链路
2. 做候选级深理解缓存
3. 建立最小 `validation`

---

## 9. 成功标准

当前阶段不以“自动剪出大片”为成功标准，而以以下能力为成功标准：

1. 用户能明确表达全局或局部编辑意图
2. agent 能围绕当前意图检索到一批合理候选
3. agent 能输出稳定的 `EditDraftPatch`
4. patch 执行后能得到新的可预览草案
5. 用户能继续基于局部结果迭代
