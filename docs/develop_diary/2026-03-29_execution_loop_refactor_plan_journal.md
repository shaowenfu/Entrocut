# 2026-03-29 执行闭环最小重构计划日志

今天我重新回头看了 `core/server.py`，比起继续纠结局部字段，我更清楚地看到真正的卡点其实只有一个：

`_run_chat_agent_loop` 现在还不是一个完整的 agent 闭环，它只是一个会调用 planner 的循环壳。`

这件事我之前其实已经隐约意识到了，但今天我把问题收得更具体了。

当前 `core/chat` 已经有这些东西：

1. `workspace state`
2. `planner context`
3. `server planner proxy`
4. 结构化 `planner decision`
5. `WebSocket event stream`

所以它不是没有基础，真正缺的是中间那段最关键的桥：

1. 工具执行
2. 工具结果规范化
3. 循环内状态回写
4. 基于新状态重新规划

我现在的判断很明确：

`下一步最值得做的，不是继续扩 API，也不是先拆多文件，而是把 planner -> tool -> observation -> replanning 这条主链先在 core 里跑通。`

这次我也刻意压住了“想一次性设计完整框架”的冲动。

对当前仓库来说，更合理的推进方式是：

1. 保留 `core/server.py` 作为主控文件
2. 只在局部增加最小结构和辅助函数
3. 先让 `_run_chat_agent_loop` 真正能执行一轮工具调用并回写状态
4. 等主链跑通后，再决定是否拆层和拆文件

我把这次判断收口进了：

1. [docs/agent_runtime/15_execution_loop_design.md](../agent_runtime/15_execution_loop_design.md)

给未来的我留一句最重要的话：

`当前最缺的不是更多规划，而是让循环内部第一次真正改变世界。`

---

今天我还顺手把另一个长期会拖垮代码质量的问题先拆开了：

`上下文编排不能继续留在 core/server.py 里和 API、状态、任务逻辑混在一起。`

我最后做的不是直接把上下文逻辑全部补完，而是先把框架抽成了独立模块：

1. [core/context_engineering.py](/home/sherwen/MyProjects/Entrocut/core/context_engineering.py)

这一步的意义不在于“功能立刻变强了”，而在于我终于把三层东西分开了：

1. 上下文原材料
2. 运行时状态
3. 提供给 planner 的决策输入

在这之前，`server.py` 里做的事情其实是：

1. 一边读变量
2. 一边裁剪
3. 一边拼 prompt
4. 一边调模型

这种写法短期方便，但后面只会让上下文工程继续退化成字符串拼接。

所以我刻意保留了一堆 `TODO`：

1. `identity`
2. `goal`
3. `scope`
4. `tools`
5. `memory`
6. `system prompt`

原因很简单：

`现在最重要的不是把每个细节都补完，而是先把未来要演进的边界挖出来。`

我把这部分判断也单独写进了：

1. [docs/agent_runtime/17_context_engineering_module_design.md](../agent_runtime/17_context_engineering_module_design.md)

给未来的我再补一句：

`从这一步开始，上下文优化应该优先发生在 context_engineering 模块里，而不是回到 server.py 继续堆变量和字符串。`

---

今天后半段我还把这两条线真正推进成了两个可交付的 `PR`。

我把任务拆成了两部分：

1. `PR #3`
   - 主攻 `context engineering`
   - 目标是把 `runtime state -> planner context` 从散变量拼接，推进到更正式的结构化编排
2. `PR #4`
   - 主攻 `agent loop`
   - 目标是把 `planner -> tool observation -> replanning` 这条最小执行闭环真正跑起来

这两个方向的拆分最后证明是对的。

因为它们各自都有自己的主责边界，但又能在 `core/server.py` 和 `core/context_engineering.py` 这两个关键位置自然接上。

等两位工程师把 `PR` 提上来以后，我没有直接在当前工作区硬合，而是先拉到独立的临时工作树里做本地合并。

这么做的原因很朴素：

`我当时的 main 上还有未提交文档改动，我不想让 PR 合并过程污染当前工作区。`

实际合并时，真正出现的冲突点很集中：

1. [core/context_engineering.py](/home/sherwen/MyProjects/Entrocut/core/context_engineering.py)

我最后的处理原则是：

1. 保留 `PR #3` 更完整的上下文契约和工具说明
2. 吸收 `PR #4` 对最小执行闭环状态的推进

这一步很符合我对两个 `PR` 关系的判断：

`一个负责把决策输入做对，另一个负责把决策执行跑通。`

合并之后，我还顺手修了一个真实的测试问题。

问题不在业务语义本身，而在异步测试的边界上：

1. 后台 `asyncio.create_task(...)` 还没真正执行完
2. `patch("httpx.AsyncClient.post", ...)` 的作用域就先退出了
3. 这会导致集成测试偶发或稳定卡住

我当时的判断是：

`这种问题如果只当成测试小毛病处理，后面还会再回来。`

所以我没有只改测试，而是又补了一层最小运行时收口：

1. 给 `InMemoryProjectStore` 加了最小 `background task registry`
2. 把 `chat` 成功收尾单独抽成统一路径
3. 在集成测试里显式断言后台任务已经真正清空

这次工作的产物，最后都安全并回了本地 `main`，然后又整理成了两笔额外提交：

1. 文档：补充本地数据存储架构说明
2. `core`：收口后台任务收尾并加固集成测试

给未来的我留一句更偏工程协作的话：

`把一个大方向拆成 context engineering 和 agent loop 两条线分别推进，是这次能稳定落地的关键。`
