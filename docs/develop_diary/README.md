# Develop Diary

`docs/develop_diary/` 用来记录开发过程中的关键决策、阶段推进和重要复盘。

这里不追求写成正式设计文档，而是强调三件事：

1. 当天到底做了什么
2. 为什么这样做
3. 给未来自己留下什么判断和边界

## 建议阅读方式

如果想快速理解项目推进脉络，建议按时间顺序阅读：

1. [2026-03-07 重建日记](./2026-03-07_rebuild_journal.md)
2. [2026-03-08 EditDraft Contract 落地日记](./2026-03-08_edit_draft_contract_landing_journal.md)
3. [2026-03-09 Server 鉴权与桌面登录回流日记](./2026-03-09_server_auth_and_desktop_login_journal.md)
4. [2026-03-09 Agent Runtime Notes](./2026-03-09_agent_runtime_notes.md)
5. [2026-03-12 Server Gateway 加固与云端部署日志](./2026-03-12_server_gateway_hardening_and_cloud_deploy_journal.md)
6. [2026-03-13 Agent Runtime 落地开发日志](./2026-03-13_agent_runtime_landing_journal.md)
7. [2026-03-13 GitHub OAuth 接入复盘](./2026-03-13_github_oauth_iteration_journal.md)
8. [2026-03-13 Credits / BYOK 改造复盘](./2026-03-13_credits_byok_settlement_followup_journal.md)
9. [2026-03-24 项目回顾与阶段性暂停日志](./2026-03-24_project_recap_and_pause_journal.md)
10. [2026-03-29 Execution Loop Refactor Plan 日记](./2026-03-29_execution_loop_refactor_plan_journal.md)
11. [2026-03-29 Server 分支 PR 回收合并日志](./2026-03-29_server_branch_pr_merge_journal.md)
12. [2026-03-30 本地数据层落地日志](./2026-03-30_local_data_layer_implementation_journal.md)
13. [2026-03-30 ui_ux 分支合并 server 最新账户能力](./2026-03-30_ui_ux_server_merge_followup_journal.md)
14. [2026-03-30 Core 模块重构日志](./2026-03-30_core_module_reconstruct_journal.md)
15. [2026-03-31 项目状态管理收口日志](./2026-03-31_project_state_management_wrapup_journal.md)
16. [2026-03-31 Server 目录重构日志](./2026-03-31_server_directory_refactor_journal.md)
<<<<<<< HEAD
17. [2026-04-13 真实桌面导入与检索准备收敛日志](./2026-04-13_real_desktop_ingest_retrieval_landing_journal.md)
18. [2026-04-13 MVP 闭环与渲染收口日志](./2026-04-13_mvp_closure_rendering_timeline_journal.md)

## 当前这组日记主要覆盖的主题

1. `EditDraft` 契约与本地状态中心落地
2. `agent runtime` 设计与最小闭环推进
3. `server auth / credits / BYOK` 相关迭代
4. 本地数据层、项目工作目录与 `SQLite`
5. `core` 模块边界和代码结构收口
6. 项目状态管理从 `workflow_state` 向事实分层模型收口
7. `server` 目录分层与 `FastAPI` 结构收口
8. MVP 阶段 `render/retrieve/patch/timeline` 闭环落地

## 命名约定

当前文件命名规则保持为：

`YYYY-MM-DD_<topic>_journal.md`

如果是偏随手记录、非正式日志，也允许像 `notes` 这种后缀，但建议尽量继续统一到 `journal`。
