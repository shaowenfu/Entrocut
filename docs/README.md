# EntroCut 文档总览（MVP）

本文档集用于指导 `EntroCut MVP` 的功能开发与联调。  
开发方法固定为 `Feature-driven Development（按功能切片开发）`，不再维护阶段性路线图文档。

## 1. 核心规范（按阅读顺序）

1. `docs/01_MVP_SCOPE.md`：MVP 边界与验收标准。
2. `docs/02_SYSTEM_ARCHITECTURE.md`：系统架构与依赖方向。
3. `docs/03_DOMAIN_MODEL.md`：核心领域模型。
4. `docs/04_CONTRACTS.md`：三端共享契约。
5. `docs/05_API_CORE_LOCAL.md`：本地 `core` API。
6. `docs/06_API_SERVER_CLOUD.md`：云端 `server` API。
7. `docs/07_WORKFLOW_WALKTHROUGH.md`：端到端场景流程。
8. `docs/08_FEATURE_DEVELOPMENT_PRINCIPLES.md`：按功能切片开发原则。
9. `docs/09_ENGINEERING_GUARDRAILS.md`：工程护栏（可观测性/隐私/错误语义/非目标/关键决策）。

## 2. UI 文档

1. `docs/ui/EntroCut_design.md`
2. `docs/ui/WORKSPACE_UI_COMPONENT_INTERACTION_SPEC.md`
3. `docs/ui/CLIENT_COMPONENT_STORE_FILE_STRUCTURE.md`

## 3. 评审清单与归档

1. `docs/review/CONTRACT_REVIEW_CHECKLIST.md`
2. `docs/archive/high-fidelity_prototype.txt`
3. `docs/archive/high-fidelity_prototype_v2.txt`

## 4. 文档治理规则

1. 遵循 `Scenario -> Function -> Contract -> API -> Implementation -> E2E` 顺序。
2. 契约变更先改 `docs/04_CONTRACTS.md`，后改代码。
3. API 变更必须同步更新 `docs/05_API_CORE_LOCAL.md` 或 `docs/06_API_SERVER_CLOUD.md`。
4. 新增能力若触碰 `09` 中非目标，必须先更新 `01` 和 `09`。
