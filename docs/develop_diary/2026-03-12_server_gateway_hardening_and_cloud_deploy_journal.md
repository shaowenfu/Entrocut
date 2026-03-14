# Server Gateway 加固与云端部署联调：我的开发日记

## 写在前面

这轮工作的主线很明确：把 `server` 从“本地链路已经闭环、云端还没跑稳”的状态，推进到“真实依赖已接通、部署链路已跑通、预发环境已可联调”的状态。

如果说前一阶段解决的是：

1. 登录、刷新、登出
2. `client -> core -> server` 的身份闭环
3. `chat proxy` 站上鉴权主链

那么这一阶段解决的是另外三件更接近上线的问题：

1. `server` 真实接入 `Google Gemini / DashScope / DashVector / MongoDB / Redis`
2. `server` 做完 `hardening（上线前加固）`
3. `server` 真正在阿里云 `ECS` 上通过 `GitHub Actions` 跑起来

这轮不再是“补功能”而是“收口系统”。

---

## 一、我先把 `server` 的业务能力补到位

### 1. `chat proxy` 从 `mock` 切到了真实上游

这轮前半段，我先把 `/v1/chat/completions` 从 `mock mode` 切到了真实 `Google Gemini` 上游，并且保持对 `core` 仍然是 `OpenAI-compatible（OpenAI 兼容）` 契约。

这里我做了几件关键事：

1. 接入 `google_gemini` provider
2. 保持虚拟模型名和 `OpenAI-compatible` 响应结构
3. 补上真实 `SSE streaming（SSE 流式）`
4. 在最终块注入规范化后的 `usage` 和 `entro_metadata`

这个点很重要，因为 `core` 不应该关心底层到底是 `Gemini` 还是别的模型服务，它只应该认稳定的 `server contract（服务端契约）`。

### 2. `quota / rate limit` 也接到了真实链路

仅仅把 `chat proxy` 接上真实模型还不够，因为商业闭环的关键不是“能调用”，而是“可控地调用”。

所以这轮里我又把：

1. `quota ledger（额度账本）`
2. `rate limit（限流）`
3. `usage` 回写

都接回到了 `chat proxy` 主路径上。

这样 `server` 不再只是一个纯转发器，而是真正承担了：

1. 鉴权
2. 额度扣减
3. 调用频控
4. 上游代理

这一层的网关职责。

### 3. 用户侧接口也补齐了

这轮我新增并独立拆出了：

1. `GET /user/profile`
2. `GET /user/usage`

这样 `server` 对外的用户面信息已经完整，`client` 后续可以直接消费这些接口来展示：

1. 会员状态
2. 剩余额度
3. 今日/月度消耗
4. 当前限流配置

### 4. 向量化与检索能力补到了真实云服务

这轮还有一条非常关键的能力线：`Vector & RAG（向量与检索）`。

我先根据阿里云官方文档收口了设计，再接通了真实能力：

1. `/v1/assets/vectorize`
   - 使用 `DashScope MultiModalEmbedding（多模态融合向量）`
   - 模型为 `qwen3-vl-embedding`
2. `/v1/assets/retrieval`
   - 使用 `DashVector` 做向量检索

其中我修掉了一个高风险实现偏差：

多模态融合输入必须作为同一个对象提交，不能把 `text / image / video` 拆成多个对象，否则拿到的是多个独立向量，而不是融合向量。

这个问题如果不修，表面上“接口能跑”，但语义空间会从根上错掉。

---

## 二、我把一整轮端到端回归跑通并固化成脚本

这轮我没有停留在“代码看起来对”，而是把主链手工从头走了一遍。

重点验证了：

1. 登录
2. `login_session` 一次性消费
3. `client -> core token sync（令牌同步）`
4. `core -> server` 带 `Bearer token` 调受保护接口
5. `refresh token rotation（刷新令牌轮换）`
6. 登出后的会话失效

这轮测试带来的一个很强的结论是：

当前系统已经不是“零散能力拼接”，而是真正完成了：

1. 身份闭环
2. 调用闭环
3. 会话闭环

之后我又把这套手工流程固化成了自动化脚本：

1. `scripts/e2e_auth_regression.py`
2. `scripts/e2e_auth_regression.sh`

它们会自动覆盖：

1. `login_session create -> claim -> consume_once`
2. `/api/v1/me`
3. `client -> core` 会话同步
4. `core -> server chat`
5. `refresh`
6. `logout`

这样后面再改鉴权和会话逻辑时，不需要靠“再点一遍 UI”来赌正确性。

---

## 三、在进入部署前，我先做了 `server hardening（服务端加固）`

这轮最核心的工程工作，其实是把 `server` 从“开发可用”推进到“云端可运维”。

### 1. 运行时强校验

我先引入了 `runtime guard（运行时守卫）`，明确区分：

1. `local`
2. `staging`
3. `production`

在严格环境下，系统会主动拒绝这些不安全配置：

1. 默认 `JWT secret`
2. `AUTH_DEV_FALLBACK_ENABLED=true`
3. 允许 `MongoDB/Redis` 静默退回内存
4. 空的 `CORS_ALLOW_ORIGINS`

后面这套守卫在云端部署时果然立刻发挥了价值：它比“部署完以后线上报错”要早得多地把问题拦住了。

### 2. 可观测性

我补了生产级基础 `observability（可观测性）`：

1. `structured logging（结构化日志）`
2. `/livez`
3. `/readyz`
4. `/metrics`
5. `audit log（审计日志）`

`/readyz` 现在不仅告诉我们“就绪没就绪”，还会直接展开各类依赖：

1. `mongodb`
2. `redis`
3. `chat_provider`
4. `dashscope`
5. `dashvector`

这让部署失败时，排查路径从“盲猜”直接变成“看 JSON”。

### 3. Provider 错误分级

我还把上游模型服务错误细分了一层，不再一股脑都叫“不可用”：

1. `PROVIDER_TIMEOUT`
2. `PROVIDER_TRANSPORT_ERROR`
3. `MODEL_PROVIDER_INVALID_RESPONSE`

这样后面线上一旦真的有波动，日志和告警就能区分：

1. 是网络问题
2. 是协议问题
3. 还是上游本身超时

---

## 四、我把 `server` 的部署链路从零搭了起来

### 1. Docker 化

进入云端部署前，我先补了：

1. `server/Dockerfile`
2. `server/.dockerignore`
3. `docker-compose.production.yml`

这里我最终选择的是：

1. `docker compose`
2. `server + redis` 一起编排
3. `Nginx` 继续由宝塔面板托管

理由很简单：

1. 现在的依赖已经不止一个容器
2. 纯 `docker run` 会把配置堆进一条命令里，后面很快就会失控

### 2. GitHub Actions 拆分

我没有继续沿用旧的 `ci-soft.yml`，而是直接删掉并重建：

1. `server-ci.yml`
   - 只做 `server` 的测试与构建校验
2. `deploy-server.yml`
   - 负责构建镜像、推送 `GHCR`、SSH 到 `ECS`、拉起新容器
3. `cleanup-ghcr.yml`
   - 单独做 `GHCR` 镜像清理
4. `mirror-redis-to-ghcr.yml`
   - 一次性把 `redis:7-alpine` 同步到 `GHCR`

这个拆分很重要，因为：

1. `CI（持续集成）` 和 `CD（持续部署）` 不该混在一份工作流里
2. 首次部署阶段不应该让“清理旧镜像”这种辅助逻辑卡主链

### 3. 为什么还要把 Redis 镜像同步到 `GHCR`

部署过程中很快暴露出一个典型国内环境问题：

`ECS` 拉 `Docker Hub` 上的 `redis:7-alpine` 很不稳定。

所以我没有继续赌网络，而是把 `redis` 也纳入自己的镜像分发链：

1. 通过 `GitHub Actions` 拉取 `redis:7-alpine`
2. 重新打 tag
3. 推到 `ghcr.io/<owner>/redis:7-alpine`
4. `docker-compose.production.yml` 改成直接从 `GHCR` 拉

这样整个部署链只依赖一个镜像源，稳定性明显更高。

---

## 五、云端联调过程中，我是怎么一步步排查故障的

这轮部署并不是一次过，而是典型的“链路都对，细节一层层收口”的过程。

### 1. 第一个问题：域名还在指向旧 `mock server`

第一次部署后访问域名，看到的还是旧的：

1. `entrocut-mock-server`

最后定位到的问题并不复杂：

1. 旧容器还占着 `8001`
2. 新部署没有先把它清掉

所以我把部署脚本补成了：

1. 先删 `entrocut-mock-server`
2. 再删 `entrocut-server`
3. 然后才 `docker compose up -d`

### 2. 第二个问题：SSH 私钥配置错误

之后 `scp/ssh` 报：

1. `ssh.ParsePrivateKey: no key found`

这个本质上不是代码问题，而是 `GitHub Secret: SERVER_SSH_KEY` 里放错了内容。

最后确认的正确做法是：

1. `SERVER_SSH_USER=root`
2. `SERVER_SSH_KEY` 必须放完整私钥，而不是 `.pub` 公钥

### 3. 第三个问题：运行时守卫拦住了空的 `CORS_ALLOW_ORIGINS`

接着 `server` 启动又被运行时守卫拦下：

1. `CORS_ALLOW_ORIGINS cannot be empty`

这个错误我没有“绕过去”，而是按原计划让用户补齐：

1. `CORS_ALLOW_ORIGINS`

这正是强校验存在的意义：防止带着危险默认值上线。

### 4. 第四个问题：`localhost` 与严格环境冲突

再往后，用户又把本地开发源一起放进了 `CORS_ALLOW_ORIGINS`，导致：

1. `production/staging` 下禁止 `localhost`

这一步我重新思考了边界，最终没有简单粗暴地“全放开”，而是收口成：

1. `production`
   - 继续禁止 `localhost`
2. `staging`
   - 允许包含 `localhost`

同时把当前云端环境切到了：

1. `APP_ENV=staging`

这样既能满足本地 `client/core` 调云端 `server` 联调，又不会把正式生产边界提前做脏。

### 5. 第五个问题：`readyz=503`

这一轮里最关键的排障节点，其实是 `readyz`。

最初只是知道：

1. `livez=200`
2. `readyz=503`

但不知道具体哪一层依赖没过。

所以我反过来增强了部署脚本本身：

1. `readyz` 失败时直接打印 JSON 本体
2. 旧镜像清理改为按 `image ID` 删除，避免 `invalid reference format`
3. 部署前先校验必填 `Secrets / Variables`

结果很快把问题定位到了唯一失败依赖：

1. `chat_provider`
2. `error=MODEL_PROVIDER_UNAVAILABLE`

也就是：

1. `GOOGLE_API_KEY` 没有成功注入部署环境

这个问题一旦被明确化，修复就非常直接：

1. 补好 `GOOGLE_API_KEY`
2. 重跑部署

最终 `readyz` 就变成了：

1. `mongodb ok`
2. `redis ok`
3. `chat_provider ok`
4. `dashscope ok`
5. `dashvector ok`

---

## 六、最终达成的状态

到这轮结束时，`server` 已经达成了几个关键里程碑：

### 1. 云端 `server` 已成功部署

访问：

1. `/`
2. `/livez`
3. `/readyz`
4. `/docs`

都已经指向新的云端服务，而不是旧的 `mock server`。

### 2. 真实依赖全部就绪

`readyz` 已明确展示这些依赖全部 `ok=true`：

1. `MongoDB Atlas`
2. `Redis`
3. `Google Gemini`
4. `DashScope`
5. `DashVector`

### 3. 云端环境的角色已经明确

当前云端环境被明确定位为：

1. `staging`

这意味着：

1. 它是真实部署环境
2. 依赖真实云资源
3. 可供本地 `client/core` 联调
4. 但还不把它当成最终对外生产环境

### 4. `core` 的联调边界也收口了

最后我又把 `core/.env.example` 补齐了和云端 `server` 通信相关的配置：

1. `SERVER_BASE_URL`
2. `SERVER_CHAT_MODEL`
3. `SERVER_CHAT_TIMEOUT_SECONDS`

并再次明确了一次边界：

1. 本地 `core` 调云端 `server`
2. 本地 `core` 不需要直连云端 `Redis`
3. 云端 `Redis` 只服务于云端 `server`

---

## 七、这轮我认为最重要的几个判断

回头看，这轮最重要的不是“写了多少代码”，而是这几个判断最终都被验证为正确：

### 1. 强校验不是阻碍，而是上线前最省时间的护栏

如果没有 `runtime guard`，很多错误不会在部署时暴露，而会拖到“用户请求已经打进来”之后才爆。

### 2. `readyz` 必须可解释

只有 `200/503` 不够，必须知道是：

1. 哪一个依赖失败
2. 为什么失败

否则运维只能靠猜。

### 3. 国内云环境不要依赖不可控镜像源

把 `redis` 也纳入自己的镜像分发链，是这轮一个很实用的工程决策。它没有业务光环，但它直接决定了部署能不能稳定。

### 4. `staging` 和 `production` 需要真实分层

即使现在还没有正式对外商用，也不能把“联调方便”和“生产边界”混成一套规则。

把当前云环境明确为 `staging`，并允许它承担本地联调，是这轮一个非常重要的收口。

---

## 八、下一步最合理的工作

这轮结束后，`server` 已经不再是主要阻塞点，下一步更合理的是：

1. 让本地 `client/core` 指向云端 `server` 做三端联调
2. 验证桌面登录、刷新、登出在真实云端环境下是否仍完整闭环
3. 进一步收口 `client` 侧环境变量和调试方式
4. 再根据真实联调结果决定是否进入更接近 `production` 的阶段

一句话总结这轮：

`server` 已经从“本地可跑的云能力骨架”，推进到了“真实依赖接通、部署链路跑通、预发环境就绪”的状态。
