# server-agent（云端 Agent（代理））作业手册

## Role Scope（职责范围）
- FastAPI（Python Web 框架）API（接口）与业务逻辑
- 向量检索与检索结果组装（可用 Stub（占位实现））
- OpenAPI（接口规范）与错误语义（Error Semantics（错误语义））

## Allowed Paths（允许修改的路径）
- `server/`
- `docs/server_agent.md`

跨模块变更必须在 Round（轮次）文档中声明，并按 Cross-Module Process（跨模块流程）执行。

## Branch Rules（分支规则）
- 分支：`server-agent`
- 基线：每轮开始从 `dev` 拉取
- 合并：Squash Merge（压缩合并）到 `dev`

## Mandatory Git Workflow（强制 Git 流程）
任务开始前必须执行：
1. 拉取远程最新代码：`git fetch origin`
2. 在当前分支同步 `dev`：`git merge origin/dev`

任务完成后必须执行：
1. 提交到当前分支：`git add -A && git commit -m "round-XXXX: <summary>"`
2. 推送到远程仓库：`git push origin server-agent`

## Pre-coding Sync（编码前同步动作）
1. 阅读 `docs/coordination/STATUS.md`
2. 领取当前 Round（轮次）：`docs/coordination/rounds/round-XXXX.md`
3. 阅读 `docs/coordination/INTERFACES.md`
4. 执行 Mandatory Git Workflow（强制 Git 流程）中的“任务开始前步骤”
5. 如需跨模块变更，先在 Round（轮次）文档声明并通知相关 Agent（代理）

## Cross-Module Process（跨模块协作流程与注意点）
1. 在 Round（轮次）任务中明确跨模块影响范围
2. 若涉及契约变更，先记录到 `docs/coordination/CHANGE_LOG.md`
3. 影响 API（接口）或 Schema（结构规范）时，必须同步更新 `docs/coordination/INTERFACES.md`
4. 任何关键决策写入 `docs/coordination/DECISION_LOG.md`

## Round Flow（轮次流程）
1. 确认 Scope（范围）与 DoD（完成定义）
2. 实现 → Unit Test（单元测试） → 记录结果
3. 执行 Mandatory Git Workflow（强制 Git 流程）中的“任务完成后步骤”
4. Integration Window（集成窗口）统一合并到 `dev`
5. 更新 Round（轮次）文档中的 Test Record（测试记录）

## Round Template（轮次模板）
```markdown
# Round XXXX（轮次）

## Goal（目标）
- 

## Task List（任务列表）
- server-agent（云端 Agent（代理））
  - Scope（范围）: 
  - DoD（完成定义）: 
  - Test Command（测试命令）: 

## Dependencies（依赖）
- 

## Risks（风险）
- 

## Non-goals（非目标）
- 

## Test Record（测试记录）
- server-agent: 

## Notes（备注）
- 
```

## Contract Dependencies（契约依赖）
- OpenAPI（接口规范）：FastAPI `/docs`
- Schema（结构规范）：`docs/schemas/analysis.json`
- 任何契约变更以 `docs/coordination/INTERFACES.md` 为准

## Test Commands（测试命令）
- TBD（待定）：在首次可运行测试后写入本节

## Quality Gates / DoD（质量门禁/完成定义）
- Scope（范围）完成且无越界修改
- Unit Test（单元测试）通过并记录
- 若涉及契约变更，已更新 `CHANGE_LOG.md`
- 关键决策已更新 `DECISION_LOG.md`
- 已提交到当前分支并推送到远程仓库

## Handover（交付记录格式）
- 变更内容：  
- 影响范围：  
- 测试命令与结果：  
- 风险与回滚点：  

## Non-goals（非目标）
- 不修改 `client/` 与 `core/` 代码（除非 Round（轮次）明确要求）
