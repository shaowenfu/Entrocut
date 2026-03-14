# Editing Agent 开发指南

本文档是精简版，用于直接指导接下来的 `editing agent（剪辑智能体）` 开发。

如果要看设计推导、取舍和讨论细节，请看：

- [Editing Agent 详细设计](./00_editing_agent_design_detailed.md)

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

### 4.1 phase 1 召回表示

1. 每个候选 `clip` 生成一个多模态融合 `embedding`
2. phase 1 只用这个 `embedding` 做主召回
3. `metadata` 只保留身份、来源与时长边界，不参与默认排序
4. 对候选的深理解延后给 `inspect`

### 4.2 检索流程

1. `planner` 生成 `retrieval hypothesis`
2. 每个假设生成一个自然语言 `semantic query`
3. 对每个 `query` 执行一次 `embedding recall`
4. 合并、去重，得到候选池
5. 将候选交给 `inspect`
6. 不够就扩展假设或改写 `query`

### 4.3 检索原则

1. phase 1 主系统只用纯多模态 `embedding` 召回
2. 不把 `ASR/OCR / tags / shot stats` 混进默认召回主链
3. `retrieve` 只解决“找得到”，`inspect` 才解决“选得准”
4. 抽象意图必须先被改写成可观测代理，再进入召回

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
