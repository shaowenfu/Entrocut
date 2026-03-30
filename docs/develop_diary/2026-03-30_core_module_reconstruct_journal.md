# 2026-03-30 Core 模块重构日志

今天我把 `core/server.py` 这块长期悬着的技术债，真正收了一次口。

这次工作的目标不是“把一个大文件拆小一点”，而是把 `core` 里的职责边界重新摆正。

在重构之前，`core/server.py` 同时承载了太多东西：

1. `FastAPI app`
2. 配置常量
3. `Pydantic schema`
4. 工具函数
5. `agent loop`
6. `store`
7. 路由
8. 错误处理

这类文件一开始看起来跑得很快，但一旦本地数据层、`planner-driven chat`、后台任务、`WebSocket event stream` 都开始往里长，阅读和修改成本就会指数上升。

我今天做的判断很明确：

`必须把 core 从“单文件可运行原型”推进到“模块边界清晰的本地后端骨架”。`

---

## 一、这次重构的目标不是抽象炫技，而是恢复局部性

我没有把这次重构理解成“做一套更优雅的架构图”。

我真正关心的是两件事：

1. 看一个功能时，能不能在少量文件里把上下文看全
2. 改一个模块时，能不能不把别的职责一起拖进来

所以这次拆分我刻意按职责走，而不是按“代码行数平均分配”走。

最后形成的结构是：

1. `config.py`
2. `schemas.py`
3. `helpers.py`
4. `agent.py`
5. `store.py`
6. `routers/`
7. `server.py`

这个划分的核心不是形式，而是让每个文件都能回答一个明确问题：

1. 配置从哪里来
2. 契约长什么样
3. 纯函数如何构造事实
4. `agent loop` 如何运转
5. 本地状态如何保存和广播
6. HTTP / `WebSocket` 如何暴露
7. `FastAPI app` 如何装配

我认为这才叫真正的局部性恢复。

---

## 二、我最在意的一点，是不要把“重构”做成行为漂移

这种拆文件工作最容易犯的错，不是 import 写错，而是：

`表面上没改业务，实际上悄悄改掉了测试语义和运行时边界。`

这次我特别盯住了一个点：

`AGENT_LOOP_MAX_ITERATIONS`

任务文档里原本写的是：

1. 把常量提到 `config.py`
2. `server.py` 只做 `re-export`

看起来很干净，但仓库里的测试并不是只“读取”这个值，而是会：

`patch.object(core_server, "AGENT_LOOP_MAX_ITERATIONS", 1)`

如果我让 `agent.py` 直接静态读取 `config.py`，那这个 patch 就会失效。

这类问题最危险，因为：

1. 代码能跑
2. 大部分场景也没事
3. 但兼容性已经悄悄坏了

所以我最后没有机械照搬文档，而是做了一个很小但必要的修正：

1. `projects.py` 增加运行时 `resolver`
2. `server.py` 在装配阶段注入 `lambda: AGENT_LOOP_MAX_ITERATIONS`
3. chat 路由在请求时读取当前值，再传入 `store -> agent`

这个处理很朴素，但我认为是对的。

因为这里真正要保护的不是“常量放在哪个文件里”，而是：

`现有运行时语义和测试契约不能被文档字面拆分悄悄破坏。`

---

## 三、这次拆分之后，server.py 终于像 server.py 了

重构前的 `server.py` 是所有东西的入口和实现。

重构后，它终于退回了它该有的位置：

1. 创建 `FastAPI app`
2. 注册 `CORS middleware`
3. 注入 `request_context_middleware`
4. 注册异常处理
5. 挂载 router
6. 保留必要的兼容性 `re-export`

我很满意这个变化，因为它让入口层重新变得诚实。

一个入口文件最重要的价值不是“能装下多少逻辑”，而是：

`让人一眼看出系统是怎么被组起来的。`

现在这一点终于成立了。

---

## 四、agent/store/router 三层也终于有了清晰分工

这次我对三层的分工是刻意收紧的。

### 1. agent

`agent.py` 只负责：

1. 组装 `planner context`
2. 请求 `Server /v1/chat/completions`
3. 验证结构化 `planner decision`
4. 执行最小 `tool loop`
5. 把 `tool observation` 应用回草案

### 2. store

`store.py` 只负责：

1. 本地项目状态
2. `SQLite repository` 对接
3. 工作目录管理
4. 后台任务调度
5. 事件广播
6. chat 成功/失败后的状态收尾

### 3. routers

`routers/` 只负责：

1. HTTP / `WebSocket` surface
2. 请求参数接入
3. 调用 `store`
4. 做最薄的一层路由级校验

这样的好处很直接：

1. 路由不再知道 `agent loop` 细节
2. `store` 不再需要承载 HTTP 装配代码
3. `agent` 不再和所有接口 surface 混在一起

这不是抽象洁癖，而是之后继续扩 `core/chat` 时最基本的防线。

---

## 五、我顺手把另一个小但真实的兼容点也留住了

测试里还有一个不太起眼但很真实的依赖：

`core_server.json.loads(...)`

也就是说，测试会把 `server.py` 当成一个动态加载模块，并直接拿它上面的 `json` 模块引用。

这件事从工程美学上看当然不完美，但在当前仓库里它就是一个已有 surface。

所以我没有强行“清理得很纯”，而是继续在 `server.py` 里保留了：

1. `json`
2. `store`
3. `auth_session_store`
4. `InMemoryProjectStore`
5. `CoreAuthSessionStore`
6. `AGENT_LOOP_MAX_ITERATIONS`

我对这种处理的看法一直很一致：

`重构不是用来教育旧调用方的，先把兼容面保护住，再慢慢收口。`

---

## 六、这次重构真正带来的，不只是“文件变多了”

回头看这次工作，我最满意的地方并不是多了多少新文件。

我最满意的是，`core` 终于开始体现出一个本地后端该有的结构感：

1. 契约在 `schemas`
2. 纯逻辑在 `helpers`
3. 运行闭环在 `agent`
4. 状态与任务在 `store`
5. 装配在 `server`
6. surface 在 `routers`

这意味着之后再推进 `core/chat`，我不用每次都回到一个一千多行的大文件里找上下文。

对我来说，这一步的意义很明确：

`core 的主链已经不再只是“能跑”，而是开始具备继续演进的结构稳定性。`

---

## 七、给未来的我留几句最重要的话

1. 不要再把 `server.py` 重新长回大杂烩
2. 不要为了“纯粹”破坏已有测试 surface
3. 新增能力时优先放进已经定义好的边界，而不是回填入口文件
4. 如果 `agent/store/router` 的职责开始模糊，优先重看依赖方向
5. `core` 现在最值得继续投入的，仍然是生产级 `planner -> tool -> replanning` 收口，而不是再扩一堆新接口

如果说之前本地数据层的工作，是让 `core` 从纯内存服务变成真正的本地后端，

那今天这次模块重构做的事就是：

`让这个本地后端开始具备长期维护的结构。`
