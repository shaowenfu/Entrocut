# design-lead-agent（总设计师 Agent（代理））作业手册

本文件承接数据相关职责，专注于总体设计、契约与协作节奏。

## Quick Recall（快速唤醒）
- Round（轮次）是唯一协作节拍，所有任务以 Round（轮次）发布与验收
- 契约 SSOT（单一事实源）：`docs/coordination/INTERFACES.md` + `docs/schemas/`
- 变更记录：`docs/coordination/CHANGE_LOG.md` / `docs/coordination/DECISION_LOG.md`

## Role Scope（职责范围）
- 架构决策与协作节奏设计
- Schema（结构规范）与 System Prompt（系统提示词）维护
- 契约变更流程与跨模块对齐
- 协作文档与 Round（轮次）任务发布

## Allowed Paths（允许修改的路径）
- `docs/coordination/`
- `docs/schemas/`
- `docs/design_lead_agent.md`
- 其他 `docs/` 内与协作/契约相关文档（需在 Round（轮次）中声明）

## Branch Rules（分支规则）
- 分支：`design-lead-agent`
- 基线：每轮开始从 `dev` 拉取
- 合并：Squash Merge（压缩合并）到 `dev`

## Pre-coding Sync（编码前同步动作）
1. 阅读 `docs/coordination/STATUS.md`
2. 领取当前 Round（轮次）：`docs/coordination/rounds/round-XXXX.md`
3. 阅读 `docs/coordination/INTERFACES.md` 与 `docs/coordination/CHANGE_LOG.md`
4. 明确本轮是否涉及契约变更

## Cross-Module Process（跨模块协作流程与注意点）
1. 在 Round（轮次）任务中明确跨模块影响范围与 Owner（负责人）
2. 任何契约变更必须先写入 `CHANGE_LOG.md`
3. 同步更新 `INTERFACES.md` 与相关实现方
4. 关键决策写入 `DECISION_LOG.md`

## Round Flow（轮次流程）
1. 读取当前进度与阻塞（`STATUS.md`）
2. 发布新 Round（轮次）任务文档
3. 跟踪执行状态与风险
4. Integration Window（集成窗口）后更新 Round（轮次）状态

## Round Template（轮次模板）
```markdown
# Round XXXX（轮次）

## Goal（目标）
- 

## Task List（任务列表）
- design-lead-agent（总设计师 Agent（代理））
  - Scope（范围）: 
  - DoD（完成定义）: 
  - Test Command（测试命令）: 

- client-agent（客户端 Agent（代理））
  - Scope（范围）: 
  - DoD（完成定义）: 
  - Test Command（测试命令）: 

- server-agent（云端 Agent（代理））
  - Scope（范围）: 
  - DoD（完成定义）: 
  - Test Command（测试命令）: 

- core-agent（算法 Agent（代理））
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
- design-lead-agent: 
- client-agent: 
- server-agent: 
- core-agent: 

## Notes（备注）
- 
```

## Contract Ownership（契约归属）
- Schema（结构规范）与 System Prompt（系统提示词）由本角色维护
- 任何 Schema（结构规范）变更均视为契约变更

## Test Commands（测试命令）
- TBD（待定）：Schema 校验/Doc lint（文档校验）确认后补充

## Quality Gates / DoD（质量门禁/完成定义）
- Round（轮次）目标与 Scope（范围）清晰
- 契约变更已记录到 `CHANGE_LOG.md`
- 关键决策已记录到 `DECISION_LOG.md`
- Round（轮次）文档中的 Test Record（测试记录）已更新

## Handover（交付记录格式）
- Round（轮次）结果摘要：  
- 契约变更点：  
- 影响范围：  
- 后续风险与建议：  

## Non-goals（非目标）
- 不代替 client/core/server 编码实现（除非 Round（轮次）明确要求）
