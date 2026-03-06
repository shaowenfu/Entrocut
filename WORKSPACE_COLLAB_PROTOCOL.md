# EntroCut 同工作区并行协作协议（5 人）

## 1. 目标

在同一个工作区并行推进时，避免互相覆盖、契约漂移和回归不可控。

## 2. 文件级 Ownership（文件所有权）

1. 工程师 A（主工程师）：
   - `core/`（核心业务与任务模型）
   - `docs/05_API_CORE_LOCAL.md`
2. 工程师 B：
   - `server/`
   - `docs/06_API_SERVER_CLOUD.md`
   - `docs/review/CONTRACT_REVIEW_CHECKLIST.md`
3. 工程师 C：
   - `client/src/pages/`
   - `client/src/index.css`
4. 工程师 D：
   - `client/src/store/`
   - `client/src/services/`
   - `client` 测试目录
5. 工程师 E：
   - `scripts/`
   - `.github/workflows/`
   - `docs/`（非契约主文档）

## 3. 共享冻结区（禁止直接改）

以下文件是冻结区，任何修改必须先由主工程师确认：

1. `client/src/contracts/contract.ts`
2. `docs/04_CONTRACTS.md`
3. `core/server.py` 与 `server/main.py` 中的 `ErrorEnvelope` 字段结构
4. `decision_type` 枚举与错误码主命名空间

## 4. 提交流程

1. 每个工程师提交前先执行本地自检：
   - `client`：`npm run typecheck`
   - `core/server`：`python -m py_compile`
   - 全链路：`bash scripts/smoke_test.sh`
2. Commit message（提交信息）使用前缀：
   - `feat(A): ...`
   - `feat(B): ...`
   - `feat(C): ...`
   - `feat(D): ...`
   - `feat(E): ...`
3. 每次提交只包含自己 ownership 范围内文件；跨边界变更拆成单独提交并标注原因。

## 5. 冲突处理

1. 若发现他人正在修改同一文件，立即暂停并在任务群同步，等待 owner 决策。
2. 禁止直接覆盖他人未合并变更。
3. 对冻结区的任何改动，必须附带：
   - 变更动机
   - 兼容性说明
   - 回滚方案

## 6. 非目标

本轮并行不做：

1. 契约 `Major Version（主版本）` 升级。
2. 新增未评审的基础设施（如替换队列中间件）。
3. 非必要的大规模重构（`refactor`）。

