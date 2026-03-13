# Server 鉴权一期与桌面登录回流落地：我的开发日记

## 写在前面

今天这轮工作的主题很集中：把 `server` 从“只有健康检查的骨架”推进到“能真实完成用户登录”的状态。

如果说前几轮重构解决的是 `core / client` 的本地契约问题，那么今天解决的是另外一条更基础的链路：

1. 用户怎么登录
2. `server` 怎么认出这个人
3. `client / core` 后续应该拿什么 token 去请求云端能力
4. 在 `Electron` 和纯浏览器调试环境下，这条链路怎么都能跑通

这件事之所以重要，是因为后面的 `chat proxy / embeddings / search / quota` 都建立在同一条身份链路之上。这里如果做乱，后面所有云端能力都会反复返工。

---

## 一、我先把“身份”和“产品权限”拆开了

这轮里我最先固定下来的一个判断是：

第三方 `OAuth` 只负责证明“你是谁”，不负责定义“你在 EntroCut 里是谁”。

所以系统必须分成两层：

1. `Identity`
   - `Google / GitHub` 帮我们验证用户身份
2. `Entitlement`
   - EntroCut 自己维护本地 `user / session / quota / project ownership`

这也是为什么 `Core` 和 `Client` 后续不会直接持有第三方 token，而只会持有 EntroCut 自己签发的：

1. `access token`
2. `refresh token`

这个边界今天被真正写进了文档，也写进了代码。

---

## 二、我先把文档口径收口了

今天先补的不是代码，而是契约文档。

我新增了两份关键文档：

1. `docs/server/03_server_auth_system_design.md`
2. `docs/server/04_server_openai_compatible_contract.md`

其中第一份专门负责：

1. 登录/注册/用户管理
2. `OAuth`
3. `JWT`
4. `MongoDB Atlas`
5. `Redis`
6. `Electron` 深链接与网页回落

第二份则明确：

1. `Core -> Server` 的受保护请求契约
2. `OpenAI-compatible` 的中转接口面
3. `server` 只认 EntroCut 自己签发的 token

我刻意把这两份文档拆开，而不是混写成一篇“超级大文档”，因为这两者解决的问题根本不同：

1. 一个解决“怎么登录”
2. 一个解决“登录之后怎么调用 AI 接口”

如果混在一起，后面阅读和演进都会非常痛苦。

---

## 三、Server 端我做了什么

### 1. 从单文件骨架切到 `app/` 结构

`server/main.py` 原来还是极薄壳层，我今天把它收口成兼容入口，并把真实实现拆到了：

1. `server/app/config.py`
2. `server/app/errors.py`
3. `server/app/models.py`
4. `server/app/auth_store.py`
5. `server/app/auth_service.py`
6. `server/app/main.py`

我这么做的原因很直接：

鉴权系统不可能长期待在单文件里。

如果继续把：

1. 配置
2. 错误模型
3. `JWT`
4. `OAuth`
5. `MongoDB / Redis`
6. 路由

全都堆在一个文件里，后面一接 `chat proxy`，文件会立刻失控。

### 2. 做了 `Phase 1` 的最短登录闭环

今天落地的 `server` 能力包括：

1. `POST /api/v1/auth/login-sessions`
2. `GET /api/v1/auth/oauth/google/start`
3. `GET /api/v1/auth/oauth/google/callback`
4. `GET /api/v1/auth/login-sessions/{id}`
5. `POST /api/v1/auth/refresh`
6. `POST /api/v1/auth/logout`
7. `GET /api/v1/me`

这套接口已经足够打通：

1. 浏览器登录
2. 本地用户创建
3. `JWT` 签发
4. 登录态查询
5. 刷新
6. 登出

### 3. 数据层按“真实业务实体”建了最小形态

今天实际落下来的实体概念有：

1. `users`
2. `auth_identities`
3. `auth_sessions`
4. `refresh_tokens`
5. `login_sessions`

为了不让本地开发被外部依赖卡死，我让 `MongoDB` 和 `Redis` 都支持退回进程内存模式。

这不是最终生产形态，但对当前阶段很有价值，因为它让我们先验证身份链路，再接真实云资源，而不是反过来。

### 4. `JWT`、刷新和登出语义也补上了

这轮里我明确没走“一枚长期 JWT 走天下”的偷懒路线。

而是直接做成：

1. 短期 `access token`
2. 长期 `refresh token`

同时：

1. `/logout` 会撤销当前会话
2. 同一会话下的 `refresh token` 也会一起撤销

这一点后来联调时也被验证了：你登出后，再拿旧 `refresh token` 刷新，服务端会明确拒绝。

---

## 四、为什么我没有让深链接直接携带 JWT

今天最值得强调的一个安全决策是：

我没有采用：

1. `entrocut://auth?token=...`

而是坚持：

1. 深链接只带 `login_session_id`
2. 真正 token 由客户端回到 `server` 再领一次

原因很简单：

如果把真正 `JWT` 塞进深链接：

1. URL 更容易泄露
2. 日志更容易污染
3. 被系统、浏览器、协议处理器意外暴露的风险更高

而只传 `login_session_id` 时，风险面会小很多，因为真正的 token 领取仍由 `server` 控制。

今天后面所有 `Electron deep link` 和网页回落的设计，都是围绕这个判断展开的。

---

## 五、Electron 回流链路我怎么设计的

### 1. 平台兼容方式

主进程里我按平台做了兼容：

1. `Windows / Linux`
   - `requestSingleInstanceLock + second-instance + argv`
2. `macOS`
   - `open-url`

但我没有把这些平台逻辑散在很多地方，而是统一收口到：

1. 提取 URL
2. 白名单解析
3. 统一 `dispatchDeepLink`

这个收口很重要，因为深链接这类能力最怕散乱，越散越难审计安全边界。

### 2. 深链接解析只接受严格白名单

今天主进程只接受这类 URL：

1. `protocol === entrocut:`
2. `hostname === auth`
3. `pathname === /callback`
4. `status === authenticated`
5. `login_session_id` 匹配预期格式

也就是说：

1. 任何未知参数都不会被信任
2. 任意伪造 URL 不会直接流入渲染进程

这一步其实就是在给未来的桌面产品做最低限度的攻击面收缩。

### 3. 渲染层只接收最小 payload

我没有让渲染层接原始 URL，而是通过 `preload` 暴露最小桥：

1. `onAuthDeepLink`
2. 只传 `{ loginSessionId, status }`

这也是刻意的。

渲染层根本不该知道外部协议 URL 长什么样，只该知道“有一个登录会话回来了”。

---

## 六、为什么我又加了一个网页调试回落页

今天开发过程中暴露出一个很现实的问题：

你现在在 `WSL2` 里跑 `Electron`，而浏览器登录测试很多时候在 Windows Chrome 里做。

这会造成两个环境分裂：

1. `Electron` 在 Linux 里
2. 浏览器登录态在 Windows 里

结果就是：

1. `Electron shell.openExternal()` 打开的是 Linux 浏览器
2. 你真正有登录态的是 Windows Chrome

如果只保留正式桌面链路：

1. 浏览器登录完只能回 `entrocut://`
2. 纯网页测试就会卡死

所以我加了一个很薄的：

1. `dev fallback`

它只在开发环境启用，用于：

1. 浏览器登录成功后先落到 `server`
2. 再把 `login_session_id` 回传给网页前端

这不是正式产品主路径，但在当前开发环境下非常有价值，因为它把“系统协议回流”问题和“身份链路是否正确”解耦了。

---

## 七、我把登录态真正同步到了 Core

前面的工作把登录做通了，但还有一个关键缺口：

`client` 拿到 EntroCut 自己的 `access token / refresh token` 之后，不能只把它们留在前端本地存储里。

因为真正要调用云端 `server` 的执行者，其实是 `core`。

所以我接着补了这条链路：

1. 在 `core` 增加：
   - `POST /api/v1/auth/session`
   - `DELETE /api/v1/auth/session`
2. 让 `client` 在以下时机同步会话给 `core`
   - 登录成功
   - 刷新 token 成功
   - 启动时恢复登录态成功
   - 登出

这里我刻意保持了职责单一：

1. `client` 负责刷新 token
2. `core` 不持有 `refresh token`
3. `core` 只消费最新同步过来的 `access token`

这个设计很重要，因为它避免了 `client` 和 `core` 双写刷新逻辑。  
如果两边都偷偷刷新，后面一定会出现状态竞争和不可预测 bug。

---

## 八、我把 Server 的 Chat Proxy 接到了现有鉴权链上

登录态同步给 `core` 之后，真正重要的一步才成立：

让 `core` 能带着 EntroCut 自己的 `access token` 去请求 `server` 的 AI 代理接口。

所以我新加了：

1. `POST /v1/chat/completions`

这个接口现在已经接入了统一的鉴权依赖，顺序是：

1. 解析 `Authorization`
2. 校验 `Bearer`
3. 解码 `JWT`
4. 校验服务端会话
5. 查当前用户
6. 检查用户状态
7. 再进入真实 `chat proxy`

这意味着：

1. `chat proxy` 不再是公开接口
2. 它不自己发明一套登录逻辑
3. 它完全复用已经做好的 `current_user/current_session` 上下文

当前这个 `chat proxy` 默认跑的是：

1. `mock proxy mode`

我故意先这样做，而不是一上来就接真实上游模型。原因是：

1. 先验证“身份链路 + 契约 + 本地工作流映射”
2. 再验证“真实上游 provider”

这比两件事同时做更稳，也更容易定位问题。

---

## 九、我把 Core 的本地 Chat 任务流接到了 Server

`core` 原本的聊天工作流只是本地生成一个简单的编辑决策。

这轮我做的不是推翻它，而是把它换成：

1. `core` 先用当前本地会话里的 `access token`
2. 调用 `server /v1/chat/completions`
3. 拿回 `OpenAI-compatible` 响应
4. 提取其中的推理文本
5. 再映射回当前 `EditDraft` 的 `assistant decision`

这样做的好处是：

1. 保住了当前前端和 `core` 的工作流契约
2. 让“文本推理来源”先切到云端 `server`
3. 后面接真实 `LLM provider` 时，不需要把整个 `Workspace` 工作流推倒重来

换句话说，这轮不是“重写聊天功能”，而是“把聊天能力的身份和推理来源云端化”。

---

## 十、这轮里还踩到了一个很典型的字段边界问题

在把 `chat proxy` 接通后，服务端第一次实际跑请求时，马上暴露出一个典型问题：

内部用户文档用的是：

1. `_id`

但我在 `chat proxy` 的 `entro_metadata` 里，一开始错误地写成了：

1. `current["user"]["id"]`

结果直接触发 `KeyError: 'id'`。

这个问题非常有代表性，因为它说明：

1. 存储层模型
2. API 层模型
3. 业务逻辑层

只要边界一松，就会开始混用字段名。

所以我立刻把规范收口成：

1. 服务内部统一只用 `_id`
2. 对外响应才映射成 `id`

并且顺手补了一份：

1. `docs/server/05_auth_implementation_spec.md`

这份文档不是愿景文档，而是当前真实代码的工程规范，专门写给后面接手的工程师。

---

## 十一、当前结果

到这一步，链路已经不是“能登录”而已，而是完整闭环了：

1. 用户通过 `Google OAuth` 登录
2. `server` 签发 EntroCut 自己的 `JWT`
3. `client` 成功拿到登录态
4. `client` 把 `access token` 同步给 `core`
5. `core` 带 `Bearer token` 调 `server /v1/chat/completions`
6. `server` 通过统一鉴权链放行
7. `server` 返回 `OpenAI-compatible` 结果
8. `core` 把结果映射回本地 `EditDraft` 任务流
9. 前端成功显示新的 `AI DECISION`

你最后看到的那条：

1. `Editing focus: 你好 ...`

就是这条链路已经跑通的直接证据。

---

## 十二、我现在对这套系统的判断

今天这轮做完之后，我对这套鉴权系统的判断是：

它已经从“概念设计”进入“可以承接真实云能力”的状态了。

当前还没完成的，不是链路结构本身，而是后续增强项：

1. 把 `chat proxy` 从 `mock mode` 切到真实上游模型
2. 把 `quota / rate limit` 接进来
3. 补更多回归测试和文档收口

但最重要的骨架已经具备：

1. 身份来源清晰
2. token 生命周期清晰
3. `client / core / server` 边界清晰
4. `chat proxy` 已经真正站在这条身份链路之上

这意味着后续扩展是在正确结构上加能力，而不是继续修补临时方案。

---

## 七、我怎么把网页调试链路做薄

我并没有让这个 `fallback` 页面变成一个“半正式登录页”。

相反，我刻意把它做薄了：

1. 不直接展示 token
2. 不要求手动领取 token
3. 登录成功后自动跳回前端页面
4. 只通过 URL 带回：
   - `auth_login_session_id`
   - `auth_status`

然后由前端页面自己调用：

1. `GET /api/v1/auth/login-sessions/{id}`

去真正领取结果并写入登录态。

这样做的好处是：

1. `fallback` 页面不持有复杂状态
2. 登录结果依然由前端自己消费
3. `server` 的一次性消费语义仍然成立

---

## 八、联调里遇到的几个真实问题

### 1. `.env` 和 Google OAuth 凭据

今天中途我直接帮你把：

1. `server/.env`

配好了，并从你生成的 Google OAuth 凭据文件中提取：

1. `AUTH_GOOGLE_CLIENT_ID`
2. `AUTH_GOOGLE_CLIENT_SECRET`

同时把：

1. `server/.env`
2. `temp/client_secret_*.json`

都加进了 `.gitignore`，避免凭据误入版本控制。

这一步看起来是小事，但如果不做，后面非常容易出安全事故。

### 2. `login_session` 一次性消费语义

一开始 `login_session` 虽然会被标记为 `consumed`，但后续再次查询仍然可能拿到旧结果。

这个行为不对。

我后面修成了：

1. 首次领取时返回结果
2. 同时立即清空 `result`
3. 之后再次查询只能看到 `status=consumed`

这个修正是必要的，因为它真正把“一次性领取”从口头规则变成了服务端保证。

### 3. `React StrictMode` 导致网页登录回流重复领取

这是今天联调里最隐蔽但也最典型的一个问题。

症状是：

1. 你明明已经成功登录
2. 但前端报：
   - `auth_error: login_session_result_unavailable`

我排查后确认：

1. `App.tsx` 里根据 URL 参数自动领取登录结果的 `useEffect`
2. 在开发模式的 `StrictMode` 下被执行了两次

于是发生了：

1. 第一次领取成功
2. 第二次再领时，服务端已把结果消费掉
3. 前端就收到 `consumed + result=null`

修法并不复杂，但必须判断准确。

我最后加了一个模块级护栏：

1. `claimedWebLoginSessionIds`

保证同一个 `login_session_id` 在前端只会被领取一次。

这也是今天最后让网页登录真正跑通的关键一步。

---

## 九、今天我确认下来的工程原则

今天这轮让我更确定几件事：

1. 桌面登录链路不要把真实 token 暴露在深链接里
2. 浏览器登录回流一定要给开发环境留薄的 fallback，不然联调效率会非常差
3. `StrictMode` 下的副作用重复执行，不是“偶发现象”，而是开发期必须正视的行为
4. 鉴权系统一定要先把身份链路做对，再去接业务接口
5. `server` 的错误语义必须结构化，否则前端只会得到一堆模糊状态

---

## 十、今天刻意没有做的事

我今天也很明确地没有做几件事：

1. 没有接 `GitHub OAuth`
2. 没有接 `Core /set_auth`
3. 没有做系统安全存储中的 `refresh token`
4. 没有做用户资料编辑页
5. 没有开始接受保护的 `chat proxy`

这些都值得做，但不应该和今天的身份链路闭环混在一起。

---

## 十一、当前我认为系统已经达到什么状态

到今天结束时，我对当前状态的判断是：

`server` 的 `Phase 1 auth` 已经从“设计讨论”走到了“可以真实登录和联调”的状态。

这包括：

1. `Google OAuth`
2. 本地用户创建
3. `JWT access/refresh token`
4. `/me`
5. `/logout`
6. `Electron deep link`
7. `Web dev fallback`
8. 一次性消费的 `login_session`

而且最关键的是：

1. `Electron` 链路可走
2. 纯网页调试链路也可走

这意味着后面无论是继续接 `Core`，还是开始给 `server` 加 `chat proxy`，我们都已经有了一条可信的身份底座。

---

## 十二、我认为下一步最值得做什么

在今天这轮之后，我认为最值得继续推进的是：

1. 让 `client` 在登录成功后把 token 明确同步给 `core`
2. 在 `server` 侧开始把 `POST /v1/chat/completions` 接到同一套鉴权中间件
3. 引入真实 `MongoDB Atlas` 持久化，而不是继续只依赖内存回退
4. 补 `GitHub OAuth`
5. 把开发期 `fallback` 文案和行为再做轻一点，避免误导成正式产品路径

如果今天这轮的核心目标是“让系统学会认人”，那下一轮就应该是“让系统带着身份去调用真正的云端能力”。
