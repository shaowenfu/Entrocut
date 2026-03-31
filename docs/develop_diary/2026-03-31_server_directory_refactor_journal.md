# 2026-03-31 Server 目录重构日志

今天我把 `server/app` 这块长期处于“能跑，但边界越来越糊”的区域，真正做了一次结构级收口。

这次工作的目标不是做新功能，而是把已经存在的 `FastAPI` 服务，从扁平堆叠的原型目录，推进到更适合长期维护的模块目录。

重构前，`server/app` 的问题非常典型：

1. `main.py` 同时承担启动、异常处理、中间件、依赖组装、健康探针、鉴权路由、`chat proxy`、向量接口、`inspect` 接口
2. `auth_store.py` 同时承担 `Mongo repository`、`Redis login session`、`in-memory fallback`、账本写入
3. `models.py` 把所有 `schema` 放在一个文件里
4. API、service、repository、runtime 基础设施全部挤在同一层

这种结构在原型期很常见，但一旦功能线变多，就会带来两个问题：

1. 读一个功能时，上下文分散在一千多行的大文件里
2. 改一个局部时，很容易碰到不相关职责

所以这次我的判断很明确：

`server 需要的不是再加一层抽象，而是恢复结构的方向感。`

---

## 一、这次重构的核心不是“拆小”，而是按职责重新摆边界

我没有按“每个文件平均分配代码行数”的方式拆，而是按真实职责拆。

最后形成的主结构是：

1. `bootstrap/`
2. `api/routes/`
3. `core/`
4. `repositories/`
5. `schemas/`
6. `services/`
7. `shared/`

这背后的原则其实很朴素：

1. 启动与装配放 `bootstrap`
2. HTTP surface 放 `api`
3. 横切基础能力放 `core`
4. 数据访问与回退策略放 `repositories`
5. 外部契约放 `schemas`
6. 业务逻辑放 `services`
7. 最小公共工具放 `shared`

我认为只有这样，后续继续扩 `server` 时，才不会重新回到“所有逻辑都长回入口文件”的状态。

---

## 二、我刻意保留了一个稳定入口，而没有把入口直接删掉

这次虽然做的是目录重构，但我没有让 `app.main` 消失。

原因很简单：

1. 测试已经依赖 `app.main`
2. 启动链已经依赖 `server.main -> app.main`
3. 现在最重要的是结构重组，不是顺手把所有调用方教育一遍

所以我最后的处理是：

1. 真正的 `FastAPI app` 装配移到 `bootstrap/app.py`
2. 运行态单例移到 `bootstrap/dependencies.py`
3. `app.main` 退化成一个薄入口，只做 `re-export`

我对这种处理是认可的。

因为这里真正该保护的是：

`已有启动入口和测试 patch surface，不应该因为目录优化被顺手打断。`

---

## 三、这次最重的三个文件，分别按最自然的方向拆开了

### 1. `main.py`

它原来是一个全知文件。

这次我把它拆成：

1. `bootstrap/exception_handlers.py`
2. `bootstrap/middleware.py`
3. `bootstrap/lifespan.py`
4. `api/routes/*.py`
5. `services/gateway/*.py`

这样做之后，入口层终于重新只负责“系统怎么组起来”，而不再负责“系统里所有事情怎么做”。

### 2. `auth_store.py`

它原来把 `Mongo`、`Redis`、回退存储、会话、账本都糊在一个文件里。

这次我把它拆成：

1. `repositories/mongo_repository.py`
2. `repositories/login_session_repository.py`
3. `repositories/auth_store.py`

这里我没有激进地把 `AuthStore` facade 一起杀掉，而是保留成轻量聚合入口。

原因不是我觉得它多优雅，而是：

`这次任务的首要约束是“完全不改逻辑”，不是顺手重写依赖注入风格。`

### 3. `models.py`

这个文件已经天然适合按接口域拆。

所以我把它拆成：

1. `schemas/auth.py`
2. `schemas/user.py`
3. `schemas/runtime.py`
4. `schemas/assets.py`
5. `schemas/inspect.py`
6. `schemas/common.py`

这一步的收益很直接：

以后读鉴权契约时，不必再在向量和 `inspect` 的模型里跳来跳去。

---

## 四、我特地没有把重构做成“更标准但更碎”的假进步

做这种目录重构时，一个很常见的误区是：

`为了看起来更像教科书，把一切都拆成极细碎的文件。`

这次我刻意避免了这种做法。

比如：

1. `vector` 仍然保留成一个 service 文件
2. `inspect` 仍然保留成一个 service 文件
3. `quota` 仍然保留成一个 service 文件

因为它们现在的复杂度，还没有大到必须继续往下拆。

真正需要下钻的是：

1. `chat gateway`
2. `auth`
3. `repository`

所以我只在这些确实复杂、确实交叉的区域继续拆分。

这不是保守，而是为了守住一个更重要的原则：

`局部性优先于形式上的“分层完整感”。`

---

## 五、测试兼容是这次重构里我最先盯住的约束

这类工作最容易出的问题，不是语法，而是：

1. import 路径悄悄断掉
2. patch 目标悄悄失效
3. 启动入口悄悄变化

所以这次我在做目录重组时，有三个兼容面一直没放松：

1. `server.main:app` 启动方式不变
2. `app.main` 仍然可导出 `app / settings / store / token_service / vector_service / metrics`
3. 测试和脚本中的旧 import 全部切到新目录

最后回归结果是：

`server` 侧 `55` 个测试全部通过。

这件事比“目录看起来更整齐”更重要。

因为只有测试证明没漂移，目录优化才真正成立。

---

## 六、这次重构之后，server 终于开始像一个长期维护的云端网关了

回头看这次改动，我最满意的不是“文件数量变多了”，而是职责线终于清楚了：

1. `bootstrap` 负责装配
2. `api/routes` 负责对外 surface
3. `services` 负责业务过程
4. `repositories` 负责存储细节
5. `schemas` 负责契约
6. `core` 负责横切基础设施

这意味着后续无论继续推进 `BYOK`、`credits`、`retrieval`、`inspect`，还是继续把 `chat proxy` 做实，

都不会再默认回到一个一千多行的扁平入口里找位置。

对我来说，这一步真正完成的不是“整理目录”，而是：

`把 server 从可运行原型，推进成了具备长期演进稳定性的 FastAPI 服务骨架。`

---

## 七、给未来的我留几句最重要的话

1. 不要再把新的 route 或 helper 回填进 `app.main`
2. 不要为了“再纯一点”贸然破坏 `app.main` 这个稳定入口
3. 优先保护 HTTP 契约、错误语义和测试 surface
4. 如果某个 service 再次开始膨胀，先问它是不是承担了多个变化原因
5. 目录结构的价值不在“像不像标准答案”，而在“下一次读代码时，能不能更快抓住上下文”

今天这次工作做完以后，`server` 至少在结构层面，已经不再是那个“先把所有东西堆进 app 目录再说”的阶段了。
