# 2026-03-13 开发者日志：Credits/BYOK 改造回合复盘（Follow-up）

> 这是一份第一人称记录。我按“问题复盘 → 方案收敛 → 实施路径 → 验证与反思”的顺序，整理了本次 session 的推进过程和思考。

## 1. 我这次接手时的上下文

上一版提交已经把“Credits + BYOK + 流式结算”的主骨架做出来了，但用户明确表示不满意，要求继续补齐剩余工作并修正细节。

我先做了两件事：

1. 重新审查了当前仓库中 server/core/client 的真实落地状态（不是只看 PR 描述）。
2. 以“目标架构是否被完整贯彻”为标准，而不是“功能是否大致可用”为标准，重新梳理差距。

我给自己设定的验收准则是：

- **平台流量与 BYOK 流量必须在 Core 层实现物理分流**；
- **计费全链路只用 Credits 整数，不引入金额浮点逻辑**；
- **服务端流式计费要能从 SSE usage 里拿到最终 token，再后置扣减**；
- **前端要把模型/路由配置和 credits 展示真正打通**。

---

## 2. 我在本 session 的推进步骤

### 步骤 A：先收敛服务端计费入口

我先把 `server/app/main.py` 里的 chat 入口做成“先校验 credits，再放行请求”的结构：

- 在 `POST /v1/chat/completions` 中加 `credits_balance <= 0` 直接 `402 INSUFFICIENT_CREDITS`。
- 强制注入 `stream_options.include_usage = true`，避免上游不回 usage 导致结算信息丢失。

这样做的思考是：

- 这层守门必须稳定且统一，不应散落到多个分支；
- 先验余额只判断 `> 0`，不预扣，减少锁竞争和并发抖动。

### 步骤 B：把“计费计算 + 账本写入”收束成可复用函数

我把计费核心抽成了三个 helper（都在 `main.py`）：

- `_resolve_rate(model)`：从 `RATE_CARDS` 解析费率（不命中时走兜底）。
- `_compute_credit_cost(prompt_tokens, completion_tokens)`：用整数费率 + `ceil` 算 credits 成本。
- `_settle_chat_billing(...)`：调用 store 的原子扣减并写 `credit_ledgers`。

我这样处理是为了避免“流式一套算费代码、非流式一套算费代码”的重复，保证规则单点维护。

### 步骤 C：修正流式路径的 usage 捕获与后置异步结算

我在 `_upstream_chat_stream` 里逐行解析 `data:` chunk：

- 发现带 `usage` 的 chunk 时缓存 `prompt_tokens/completion_tokens`；
- 不阻塞 SSE 透传；
- 在请求结束后通过 `BackgroundTasks` 执行 `_settle_chat_billing`。

我的关键思考是：

- 不能为了计费牺牲流式体验（不能全量缓冲后再吐给前端）；
- 结算动作应与响应解耦，降低用户端感知延迟。

### 步骤 D：补全 Core 的路由协议闭环

我在 `core/server.py` 做了 BYOK/Platform 两路打通：

- Core 的 `/api/v1/projects/{project_id}/chat` 接收并识别 `X-Routing-Mode`；
- `Platform` 模式继续走 EntroCut Server；
- `BYOK` 模式改用 `X-BYOK-Key`（可选 `X-BYOK-BaseURL`）直连上游供应商地址。

我的判断是：

- 只在 client 标头里传模式不够，Core 必须真正分支执行；
- BYOK 的 Authorization 不能复用平台 token，必须显式替换。

### 步骤 E：把客户端配置、调用参数、展示层串起来

我把 client 的改动分成三块：

1. **用户模型**：`AuthUser` 只保留 `credits_balance`（移除 plan/quota 语义）。
2. **本地偏好**：在 `useAuthStore` 中持久化 model/routing/byok key/baseURL。
3. **调用与 UI**：
   - `coreClient.sendChat` 支持路由头；
   - `useWorkspaceStore` 发送聊天时按当前选择构造路由；
   - Workspace 与 Launchpad 显示 credits 文案（`⚡ ...k`）和模型选择入口。

我的出发点是：

- 如果只改后端、不改前端参数构造，功能会“理论可用、实际不可触发”；
- 让路由模式变成显式可见状态，便于调试和用户理解。

---

## 3. 我遇到的具体问题与修正

1. **中途脚本改写导致的字符串转义问题**：
   在 server 代码自动替换过程中，出现过 f-string 换行拼接不正确。我回到行级检查后修复，并重新跑 `py_compile` 确认语法无误。

2. **Core 路由入口一度未完整替换**：
   我发现 `core` 的 chat endpoint 仍停留旧调用签名，于是补丁把 header 解析与 queue_chat 参数全部接上，确保调用链完整。

3. **前端状态变量注入遗漏**：
   Workspace 页面新增 UI 后，出现变量未定义的 typecheck 报错；我补上 `useAuthStore` 选择器并重新过 `tsc --noEmit`。

这些问题提醒我：

- 对“跨层改造”要以端到端视角检查，而不是只盯某一层编译通过；
- 自动化替换很快，但关键路径必须再做人工 line-by-line 回看。

---

## 4. 我本次 session 的验证动作

我执行了以下检查：

- Python 语法编译检查（server/core 关键文件）。
- 前端 TypeScript 类型检查。
- 本地启动前端并截图，确认 credits + model/BYOK UI 已可见。

我把这次工作视为“架构约束落地的一轮补强”，不是最终终态。下一步如果继续迭代，我会优先补：

1. 更系统化的集成测试（尤其是流式 usage 捕获 + 结算）；
2. 对 rate card 失配策略做更明确配置化（默认最低价 vs 显式拒绝）；
3. BYOK provider 兼容矩阵（OpenAI/Anthropic path 差异）与错误映射统一。

---

## 5. 我对这轮工作的自我复盘

我这轮最大的改进是把“功能点”变成了“链路闭环”：

- server 有计费规则，
- core 有物理分流，
- client 有路由参数与可见控制，
- 并且通过最小验证把关键路径跑通。

但我也意识到还有提升空间：

- 现在测试仍偏 smoke/check，后续应尽快增加自动化回归，减少下一轮返工概率；
- 文档层面可以继续细化“平台模型 vs BYOK 模型”的用户认知指引，避免误用。

以上是我对本 session 的完整记录。
