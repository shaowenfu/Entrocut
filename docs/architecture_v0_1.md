# EntroCut Architecture v0.1（架构说明）

## 0. 目标
- 为 AI-first（AI 优先）框架建立最小架构骨架。
- 只实现“可编辑时间线 + 可视化 + 导出”主链路，AI 只保留扩展位。

## 1. 系统边界（System Boundaries（系统边界））
- Client（客户端）：Electron（桌面框架）+ React（前端框架），负责 UI（界面）与本地数据展示。
- Core（本地算法）：Python（解释语言）Sidecar（本地侧车服务），负责媒体处理与渲染。
- Server（云端）：FastAPI（Python Web 框架），v0.1 仅保留接口框架，不实现 AI 能力。
- AI Agent（智能体）：未来逻辑实体，通过 Tool（工具）+ Skill（技能）执行编辑操作；v0.1 仅保留扩展位。

## 2. 关键流程（v0.1）
1. Project Hub（项目管理）创建/打开项目。
2. 导入 Asset（素材）到 Media Library（素材库）。
3. 拖拽素材到 Timeline（时间线）并做基础编辑。
4. Preview Player（预览播放器）播放与定位。
5. Export（导出） -> Core（本地算法）渲染 -> 输出成片。

## 3. 未来扩展流程（v1+，仅占位）
- Indexing（索引构建）：本地切分与抽帧 -> Embedding（向量化）-> Vector Store（向量库）。
- Retrieval（检索）：语义搜索 -> 召回片段 -> 生成编辑建议。
- Agent Execution（智能体执行）：Plan（计划）-> IR（中间表示）-> Timeline（时间线）落地。

## 4. 数据归属与存储（v0.1）
- 本地 SQLite（本地数据库）：Project（项目）、Asset（素材）、Timeline（时间线）、Chat History（对话记录）、Export Task（导出任务）。
- 云端存储：仅保留接口占位，不做真实写入。

## 5. 接口与契约（Contract（契约））
- v0.1 只保留最小接口结构，未冻结字段。
- v1+ 再引入 Versioning（版本治理）与稳定 Schema（结构）。

## 6. 非目标（Non-goals（非目标））
- AI 驱动编辑操作落地。
- 语义检索与自动剪辑。
- 云端同步与多用户权限实现。

## 7. 约束
- Timeline（时间线）是执行层唯一权威视图。
- 任何 AI 操作必须可被 Timeline（时间线）验证与修正。
