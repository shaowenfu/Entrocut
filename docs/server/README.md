# Server 文档

这一组文档收纳 `server` 方向的设计、契约、鉴权和上线前约束。

## 当前分支状态

当前 `server` 分支已经同时吸收了两条之前独立推进的能力线：

1. `GitHub OAuth` 登录接入
2. `credits-based billing + BYOK routing + model selection` 配套调整

但要注意，这并不意味着所有能力都已经完全产品化。当前更准确的理解是：

1. 鉴权主链已经具备 `Google + GitHub` 双 provider 基础
2. `client -> core -> server` 的登录态传递已经存在
3. `credits / BYOK` 的字段、前端入口和部分调用链已经合回主线
4. 后续仍需要继续做真实上游能力验证、计费回归和端到端测试

如果你是第一次进入 `server` 方向，建议先看下面的阅读顺序，再看最近两篇相关开发日志。

## 推荐阅读顺序

1. [01_server_module_design.md](./01_server_module_design.md)
   - `server` 模块边界与总体职责
2. [02_server_api_inventory.md](./02_server_api_inventory.md)
   - 基于模块设计收口接口面
3. [03_server_auth_system_design.md](./03_server_auth_system_design.md)
   - 登录、注册、用户、授权整体方案
4. [04_server_openai_compatible_contract.md](./04_server_openai_compatible_contract.md)
   - `Core -> Server` 云端契约
5. [05_auth_implementation_spec.md](./05_auth_implementation_spec.md)
   - 当前已落地鉴权实现规范
6. [06_server_vector_rag_design.md](./06_server_vector_rag_design.md)
   - 向量与 `RAG` 设计
7. [06a_server_retrieve_inspect_gateway_design.md](./06a_server_retrieve_inspect_gateway_design.md)
   - `retrieve / inspect` 云端网关主方案
8. [06b_server_vectorize_contract.md](./06b_server_vectorize_contract.md)
   - `POST /v1/assets/vectorize` 字段级契约草案
9. [06c_server_retrieval_contract.md](./06c_server_retrieval_contract.md)
   - `POST /v1/assets/retrieval` 字段级契约草案
10. [06d_server_inspect_contract.md](./06d_server_inspect_contract.md)
   - `POST /v1/tools/inspect` 字段级契约草案
11. [06e_server_inspect_implementation_draft.md](./06e_server_inspect_implementation_draft.md)
   - `/v1/tools/inspect` 实现级设计草案
12. [07_server_production_hardening_plan.md](./07_server_production_hardening_plan.md)
   - 生产加固
13. [08_server_staging_runbook.md](./08_server_staging_runbook.md)
   - `staging` 运维说明

## 配套阅读

1. 本地 `client / core` 契约： [contracts/01_core_api_ws_contract.md](../contracts/01_core_api_ws_contract.md)
2. 剪辑草案基础： [editing/01_edit_draft_schema.md](../editing/01_edit_draft_schema.md)
3. 最近和 `server` 状态最相关的开发日记：
   - [2026-03-13 GitHub OAuth 接入复盘](../develop_diary/2026-03-13_github_oauth_iteration_journal.md)
   - [2026-03-13 Credits / BYOK 改造复盘](../develop_diary/2026-03-13_credits_byok_settlement_followup_journal.md)
   - [2026-03-29 Server 分支 PR 回收合并日志](../develop_diary/2026-03-29_server_branch_pr_merge_journal.md)
