# 11. Decisions（架构决策）

## 已确认决策

1. 产品主路径采用 `Chat-to-Cut`，不是传统编辑器优先。
2. 架构采用 `Hybrid Local-First`，视频重处理在本地 `core`。
3. 语义理解与向量检索放在云端 `server`。
4. 以 `EntroVideoProject` 作为三端共享契约。
5. `Timeline` 在 MVP 不引入状态机，按最新契约覆盖。
6. 导出仅支持默认配置，导出期间禁止并行编辑。
7. 素材检索粒度采用 `AtomicClip（切片级）`，不是原视频级。
8. `reasoning` 为必填可视字段，用于解释 AI 选择。

## 保留扩展位

1. `Multi-User Interface（多用户接口）` 字段预留，不实现协作能力。
2. `Agent Tool/Skill` 框架接口预留，不实现具体工具链。
3. `AI Quick Start（AI 速启）` 入口预留，不在 MVP 开发。

## 待确认事项（不阻塞当前开发）

1. `CORE_PORT` 默认端口号最终值。
2. `DashVector` 索引分片策略与成本上限。
3. `Qwen3-VL-Flash` 二次理解触发阈值（Top-N 的 N 值）。
4. `Export` 输出编码参数（在默认预设内固定哪些项）。
