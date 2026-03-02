# EntroCut 开发文档集（MVP）

本文档集用于指导 `EntroCut MVP` 从当前壳层代码进入可交付实现，唯一主线是 `Chat-to-Cut` 闭环。

## 阅读顺序

1. `docs/01_MVP_SCOPE.md`：定义边界与验收标准。
2. `docs/02_SYSTEM_ARCHITECTURE.md`：定义 `Hybrid Local-First Architecture（本地优先混合架构）`。
3. `docs/03_DOMAIN_MODEL.md`：定义核心实体与关系。
4. `docs/04_CONTRACTS.md`：定义共享 `Contract（契约）` 与版本规则。
5. `docs/05_API_CORE_LOCAL.md`：定义本地 `core` 接口。
6. `docs/06_API_SERVER_CLOUD.md`：定义云端 `server` 接口。
7. `docs/07_WORKFLOW_WALKTHROUGH.md`：定义端到端场景流程。
8. `docs/08_IMPLEMENTATION_PLAN.md`：定义分阶段实现路径。
9. `docs/09_OBSERVABILITY_PRIVACY_ERROR.md`：定义可观测性、隐私和错误语义。
10. `docs/10_NON_GOALS.md`：定义明确不做事项。
11. `docs/11_DECISIONS.md`：记录当前架构决策与待定项。

## 文档治理规则

1. 遵循 `Scenario -> Function -> Contract -> API -> Implementation` 顺序，不允许跳步实现。
2. `Contract（契约）` 变更必须先修改 `docs/04_CONTRACTS.md`，再改代码。
3. `API（接口）` 变更必须同步修改 `docs/05_API_CORE_LOCAL.md` 或 `docs/06_API_SERVER_CLOUD.md`。
4. 任何新增功能若超出 `docs/10_NON_GOALS.md`，必须先更新 `MVP Scope（MVP 范围）`。
