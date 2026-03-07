# Phase 4/5 Validation Matrix

## 1. Scope

本文只覆盖工程师 D 当前负责的四项：

1. `4.1 Server` 规划结果的结构稳定性
2. `5.1 Prompt queue` 只保留最后一条
3. `5.3` 断线恢复
4. `5.4` 三端 `smoke` 扩展为 `CI smoke`

非目标：

1. 不修改 `client/core` 业务状态机。
2. 不新增跨端契约字段。
3. 不把 `reconnect/resync` 的真实实现混进验证脚本。

## 2. Server Plan Stability

自动化命令：

```bash
bash scripts/phase45_server_plan_stability.sh
```

覆盖点：

| 场景 | 入口 | 期望 |
| --- | --- | --- |
| `service-level` mock plan | `LLMProxyService.plan_edit` | `reasoning_summary / ops / storyboard_scenes` 三个关键字段始终存在且类型稳定 |
| `prompt-only` chat | `POST server /api/v1/chat` | `decision_type=ASK_USER_CLARIFICATION`，`storyboard_scenes=[]`，`project.reasoning_summary` 与顶层一致 |
| `media-ready` chat | `POST server /api/v1/chat` | `decision_type=UPDATE_PROJECT_CONTRACT`，`storyboard_scenes` 为稳定对象数组，`project.timeline.tracks` 存在 |

失败语义：

1. 任一关键字段缺失、类型漂移、`project.reasoning_summary` 与顶层不一致，脚本直接失败。

## 3. Prompt Queue Last-Only

自动化命令：

```bash
bash scripts/phase45_prompt_queue_last_only_check.sh
```

自动化断言：

1. `isMediaProcessing=true` 时连续调用两次 `sendChat`，`pendingPrompt` 只保留最后一条。
2. 两次输入都会留下 `user turn`。
3. 排队反馈只产生 `prompt_queued` 的 `assistant turn`，不提前进入真实 `chat`。

手工矩阵：

| 场景 | 步骤 | 期望 |
| --- | --- | --- |
| 双击连续输入 | 素材处理中依次发送 `A -> B` | `pendingPrompt` 最终为 `B`，工作台只应在处理完成后自动执行 `B` |
| 三次连续输入 | 素材处理中依次发送 `A -> B -> C` | `pendingPrompt` 最终为 `C`，`A/B` 不应在处理完成后被自动补发 |
| 处理中失败 | 素材处理中发送 `A -> B`，随后 ingest 失败 | 页面保留失败态，不能静默执行旧 prompt，重新触发前应由用户显式操作 |

说明：

1. 自动化脚本只验证 `queue overwrite（队列覆盖）` 的 store 语义。
2. “处理完成后只补发最后一条” 仍需通过工作台手工矩阵复核，因为该链路跨 `upload -> ingest -> auto-chat`。

## 4. Disconnect Recovery

自动化命令：

```bash
bash scripts/phase45_disconnect_recovery_test.sh
```

覆盖矩阵：

| 场景 | 注入方式 | 期望 |
| --- | --- | --- |
| `WebSocket` 主动重连 | 连接后断开，再次连接 | 新连接再次收到 `session.ready` |
| `Server` 短暂离线 | 停掉 `server` 后经 `core /api/v1/chat` 发起请求 | 返回 `HTTP 502`，错误码为 `SERVER_UNAVAILABLE` 或 `SERVER_PROXY_HTTP_ERROR` |
| `Server` 恢复 | 重启 `server` 后再次请求 `core /api/v1/chat` | 返回正常 `ChatDecisionResponse` |
| `Core` 重启导致 `WebSocket` 断开 | 持有中的 `ws` 连接，停掉 `core` 后再拉起 | 老连接被关闭；新连接再次收到 `session.ready` |

当前边界说明：

1. 该脚本验证的是“失败可见 + 新连接可恢复”。
2. 它不宣称已经具备自动 `resync`；`event sequence` 和自动补同步仍属于后续实现范围。

## 5. CI Smoke

入口约定：

```bash
bash scripts/smoke_test.sh
```

行为约定：

1. 本地默认仍跑轻量 `baseline smoke`。
2. 当 `CI=true` 或显式设置 `SMOKE_MODE=phase45` 时，`scripts/smoke_test.sh` 自动委托到 `scripts/phase45_smoke_test.sh`。
3. `phase45 smoke` 在 `CI` 下若发现 `client/node_modules` 缺失，会自动执行 `npm ci` 后继续三端链路验证。

成功路径：

1. `core/server/client` 三端可启动。
2. `upload -> ingest -> index -> chat -> WebSocket events` 主干链路全部打通。

失败路径：

1. 任一健康检查失败。
2. `client` 未能加载。
3. `workspace.chat.* / workspace.patch.ready` 关键事件缺失。

## 6. Residual Risk

1. `Prompt queue` 的“自动补发只有最后一条”仍依赖工作台手工矩阵复核。
2. 当前恢复脚本验证的是“重新连接可恢复”，不是“自动重同步已实现”。
