# Server 文档

这一组文档收纳 `server` 方向的设计、契约、鉴权和上线前约束。

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
11. [07_server_production_hardening_plan.md](./07_server_production_hardening_plan.md)
   - 生产加固
12. [08_server_staging_runbook.md](./08_server_staging_runbook.md)
   - `staging` 运维说明

## 配套阅读

1. 本地 `client / core` 契约： [contracts/01_core_api_ws_contract.md](../contracts/01_core_api_ws_contract.md)
2. 剪辑草案基础： [editing/01_edit_draft_schema.md](../editing/01_edit_draft_schema.md)
