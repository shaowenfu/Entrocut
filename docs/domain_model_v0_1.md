# EntroCut Domain Model v0.1（领域模型）

## 0. 目标与边界
- 目标：为 AI-first（AI 优先）框架提供最小但可扩展的领域模型。
- 边界：不实现 AI Tool（工具）/Skill（技能），仅预留扩展位。

## 1. 核心实体（Entities（实体））

### 1.1 User（用户）
- 目的：保留 Multi-User（多用户）接口位。
- 字段：
1. userId（字符串）
2. displayName（字符串，可选）
3. createdAt（时间）

### 1.2 Project（项目）
- 目的：编辑与导出的组织单元。
- 字段：
1. projectId（字符串）
2. ownerUserId（字符串）
3. name（字符串）
4. createdAt（时间）
5. updatedAt（时间）

### 1.3 Asset（素材）
- 目的：原始视频素材。
- 字段：
1. assetId（字符串）
2. projectId（字符串）
3. filePath（字符串，绝对路径）
4. duration（数值，秒）
5. format（字符串，可选）
6. createdAt（时间）

### 1.4 Segment（片段）
- 目的：素材内可寻址片段，预留 AI 检索与拆分能力。
- 字段：
1. segmentId（字符串）
2. assetId（字符串）
3. start（数值，秒）
4. end（数值，秒）
5. tags（字符串数组，可选）

### 1.5 Timeline（时间线）
- 目的：可编辑的权威视图。
- 字段：
1. timelineId（字符串）
2. projectId（字符串）
3. tracks（Track（轨道）数组）
4. updatedAt（时间）

### 1.6 Track（轨道）
- 字段：
1. trackId（字符串）
2. type（video|audio）
3. clips（Clip（剪辑片段）数组）

### 1.7 Clip（剪辑片段）
- 目的：Timeline（时间线）的最小编辑单元。
- 字段：
1. clipId（字符串）
2. assetId（字符串）
3. start（数值，秒）
4. end（数值，秒）
5. trackId（字符串）

### 1.8 ChatSession（对话会话）
- 目的：AI Copilot（AI 副驾驶）对话容器。
- 字段：
1. sessionId（字符串）
2. projectId（字符串）
3. createdAt（时间）

### 1.9 ChatMessage（对话消息）
- 字段：
1. messageId（字符串）
2. sessionId（字符串）
3. role（user|assistant|system）
4. content（字符串）
5. createdAt（时间）

### 1.10 ExportTask（导出任务）
- 目的：渲染任务记录。
- 字段：
1. taskId（字符串）
2. projectId（字符串）
3. status（queued|rendering|success|failed）
4. outputPath（字符串，可选）
5. createdAt（时间）
6. finishedAt（时间，可选）

## 2. 关键关系（Relations（关系））
1. Project -> Asset（一对多）
2. Project -> Timeline（一对一）
3. Timeline -> Track（一对多）
4. Track -> Clip（一对多）
5. Asset -> Segment（一对多）
6. Project -> ChatSession（一对一或一对多）
7. ChatSession -> ChatMessage（一对多）
8. Project -> ExportTask（一对多）

## 3. 不变量（Invariants（不变量））
1. Clip.start < Clip.end
2. Segment.start < Segment.end
3. Clip.assetId 必须存在于 Project 的 Asset 列表
4. Timeline 是 Project 的唯一权威编辑视图

## 4. 扩展位（Extensibility（可扩展性））
1. Segment 支持 AI 生成 tags（标签）与检索索引字段（未实现）。
2. Clip 可扩展 effects（效果）、speed（速度）、volume（音量）字段（未实现）。
3. ChatMessage 可扩展 toolCalls（工具调用）字段（未实现）。
