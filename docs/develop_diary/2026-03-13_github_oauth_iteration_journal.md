# GitHub OAuth 接入复盘：从需求拆解到交付约束的开发日志

## 背景

这轮任务的目标并不是“重做一套鉴权系统”，而是在项目已经打通 Google OAuth 的前提下，
以最小侵入方式扩展 GitHub OAuth 登录能力，并保持现有 login_session + 双 token（access/refresh）架构不变。

需求核心包括五块：

1. 服务端配置新增 GitHub OAuth 环境变量。
2. OAuthService 增加 provider=github 分支与对应错误处理。
3. 客户端服务层新增 createGithubLoginSession。
4. 前端登录页面增加 “Continue with GitHub” 入口并复用现有回调/轮询链路。
5. 部署工作流注入 AUTH_GITHUB_CLIENT_ID / AUTH_GITHUB_CLIENT_SECRET。

---

## 我对本次任务的执行策略

我当时采用的策略是：

1. 先沿着“Google 已有链路”做镜像式扩展，避免触碰 JWT 签发与会话消费逻辑。
2. 在服务端先补 provider 分支，再补请求模型的 provider 字段白名单。
3. 客户端按现有 createGoogleLoginSession 的实现风格新增 GitHub 版本。
4. UI 层仅增加新入口，不改动 login_session claim 的底层流程。
5. 部署工作流只增变量注入与必填校验，不改动整体部署结构。

这个策略本身是对的：在现有架构上做增量，而不是重构式改造。

---

## 这轮提交里真正完成的事情

### 1) 服务端配置扩展

在 `Settings` 中新增了：

- `auth_github_client_id: str | None = None`
- `auth_github_client_secret: str | None = None`

这样本地开发可选，线上通过环境变量注入。

### 2) OAuth provider 逻辑扩展

在 `OAuthService._provider_config` 中实现了：

- `google` 分支保持原逻辑。
- 新增 `github` 分支（authorize/token/userinfo/scope）。
- 非法 provider 统一抛 `INVALID_REQUEST`。
- GitHub 配置缺失抛 `OAUTH_PROVIDER_NOT_CONFIGURED`。

### 3) 回调 profile 解析按 provider 分支

在 `handle_callback` 对 userinfo payload 做了 provider 维度解析：

- Google：`sub / picture / name`
- GitHub：`id -> str(id)`、`avatar_url`、`name || login`

其中 `id` 强制转字符串，是为了维持系统内 provider_user_id 的一致类型。

### 4) 客户端 API 和状态层扩展

- `authClient.ts` 新增 `createGithubLoginSession()`。
- `useAuthStore.ts` 新增 `startGithubLogin()`。

### 5) 前端入口与部署配置

- Launchpad 页面增加 GitHub 登录按钮。
- 部署 workflow 增加 GitHub secrets 的注入和必填校验。

---

## 过程中的问题与反思

虽然主目标实现了，但从“工程质量”视角，本轮有两个值得反思的点：

1. **UI 变更粒度偏大风险**：
   在登录入口改动时，如果一次性调整过多按钮结构，容易引入非必要的视觉/交互回归。
   未来应坚持“新增入口优先、结构重排谨慎”的改动策略。

2. **验证手段受环境约束**：
   尝试截图时，本地未运行可访问的前端服务，导致浏览器容器无法获取页面。
   这提醒我后续在“可视化改动任务”里应更早确认运行态，再执行截图步骤。

---

## 我对后续同类任务的固定 checklist

为了减少返工，后续会固定执行下面这套顺序：

1. 先查 `config -> service -> models -> client service -> store -> page -> workflow` 的依赖链。
2. provider 扩展时优先写 `INVALID_REQUEST` 与 `NOT_CONFIGURED` 两类错误路径。
3. 明确第三方 payload 的字段差异，先做类型归一化（例如 GitHub `id`）。
4. 前端入口只做增量改动，避免无关 UI 重排。
5. 若有视觉改动，先确认可访问端口，再做截图取证。
6. 交付前做“最小闭环”核查：创建 session -> 获取 authorize_url -> callback -> claim。

---

## 结语

这轮工作的本质是“在已打通的 OAuth 框架里新增 provider 能力”，不是重写鉴权。
从结果看，链路扩展方向是正确的；从过程看，还需要进一步压缩 UI 层改动的噪声，并提升可视化验证前的环境检查。

后续若继续扩展 Apple/Microsoft 等 provider，这次的 provider 分支模式和字段归一化策略可以直接复用。
