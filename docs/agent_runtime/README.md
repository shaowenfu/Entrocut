# Agent Runtime 文档

这一组文档集中收纳 `editing agent（剪辑智能体）` 的设计、分层、契约和运行时闭环，并按推荐阅读顺序编号。

## 推荐阅读顺序

1. [00_editing_agent_design_detailed.md](./00_editing_agent_design_detailed.md)
   - 高密度设计讨论总收口
2. [01_editing_agent_dev_guide.md](./01_editing_agent_dev_guide.md)
   - 精简版开发指南
3. [02_editing_agent_runtime_architecture.md](./02_editing_agent_runtime_architecture.md)
   - 五层运行时总骨架
4. [03_state_layer_design.md](./03_state_layer_design.md)
   - `State Layer`
5. [04_planner_action_schema.md](./04_planner_action_schema.md)
   - `Planner Action`
6. [05_tool_layer_minimal_contract.md](./05_tool_layer_minimal_contract.md)
   - `Tool Layer` 总契约
7. [06_read_tool_contract.md](./06_read_tool_contract.md)
8. [07_retrieval_request_schema.md](./07_retrieval_request_schema.md)
9. [08_inspect_tool_contract.md](./08_inspect_tool_contract.md)
10. [09_edit_draft_patch_schema.md](./09_edit_draft_patch_schema.md)
11. [10_preview_tool_contract.md](./10_preview_tool_contract.md)
12. [11_memory_context_layer_design.md](./11_memory_context_layer_design.md)
13. [12_action_context_packet_schema.md](./12_action_context_packet_schema.md)
14. [13_context_assembler_design.md](./13_context_assembler_design.md)
15. [14_planner_output_schema.md](./14_planner_output_schema.md)
16. [15_execution_loop_design.md](./15_execution_loop_design.md)

## 阅读建议

1. 想先理解方向，看 `00 -> 02`
2. 想看运行时骨架，看 `03 -> 05`
3. 想看上下文工程，看 `11 -> 13`
4. 想看规划与执行闭环，看 `14 -> 15`
