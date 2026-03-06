## 场景一：初始化与素材导入（冷启动）

这是用户第一次打开应用，建立“本地感知”的过程。

| 步骤 | 用户行为 | Client (React/Electron) | Core (本地 Python) | Server (云端中转) |
| --- | --- | --- | --- | --- |
| **1. 启动** | 打开 EntroCut | 展示启动台，监听 `localhost:8000` | 启动 FastAPI 服务，检查本地 FFmpeg 环境及数据库 | 校验用户 Token，返回 API 调用配额 |
| **2. 导入** | 拖入“滑雪”视频文件夹 | 捕获路径，通过 IPC 传给 Core | **[关键逻辑]** 开始扫描文件，利用 FFmpeg 提取关键帧和元数据 | 无感知 |
| **3. 向量化** | 等待处理 | 显示进度条（订阅 Core 的 WebSocket） | 将提取的关键帧图像发送给 Server 中转 | 接收图片流，调用阿里云 Embedding，返回向量给 Core |
| **4. 索引** | 无感知 | 无感知 | 将返回的向量存入本地 SQLite，并同步一份索引至云端 DashVector | 接收向量并存入 DashVector |

---

## 场景二：AI 辅助创意（Chat-to-Cut）

用户开始通过对话框表达意图，这是“本地大脑”最活跃的时刻。

### 场景：用户输入“帮我剪一个高燃的滑雪集锦”

1. **意图捕获 (Client)**：
* 用户在 `WorkspacePage` 输入 Prompt。
* Client 通过 WebSocket 将文本发送给 Core。


2. **大脑思考 (Core - Local Agent)**：
* **上下文构建**：Core 读取本地 DB，发现该项目有 50 个视频片段。
* **逻辑编排**：Core 组装 Prompt：“现有素材 A...B...C，用户要‘高燃集锦’，请给出 5 个搜索关键词。”
* **中转调用**：Core 请求 Server 转发给大模型（如 Qwen-Max）。


3. **语义检索 (Server & Core)**：
* Server 返回关键词：“跃起、喷雪、快速滑行”。
* **Core** 生成这些词的向量，请求 **Server** 调用 DashVector。
* **Server** 在云端向量库中完成 Top-K 检索，返回匹配的片段 ID 给 Core。


4. **生成决策 (Core)**：
* Core 根据检索结果，自主决定分镜顺序。例如：先来个全景，再来三个特写切换。
* Core 生成一个 `ProjectPatch`（包含新的 Storyboard 结构）。


5. **UI 同步 (Client)**：
* Core 通过 WebSocket 把 Patch 发给 Client。
* **Zustand Store** 更新，界面上瞬间弹出 5 张分镜卡片，`isThinking` 状态转为 `false`。



---

## 场景三：精修与实时预览（人机协作）

用户对 AI 的结果进行微调，确保“确定性”。

* **操作 A：用户点击分镜卡片进行 Seek**
* **Client**: 触发 `seekTo(timestamp)` 动作。
* **Core**: 接收指令，通过 FFmpeg 读取对应时间戳的视频帧，或者驱动本地播放器跳转。


* **操作 B：用户手动调整分镜顺序**
* **Client**: 拖拽 UI 卡片，更新本地 Zustand Store。
* **Core**: 监听到 Client 发来的顺序变更，实时更新本地 `project.db` 中的 `sequence_order`。



---

## 场景四：本地渲染与导出（产出结果）

这是最重体力的活，完全由本地 Core 承担。

| 步骤 | Client 表现 | Core 行为 | Server 行为 |
| --- | --- | --- | --- |
| **1. 导出指令** | 点击 Export，界面进入 `isEditLocked` 状态 | 锁定数据库，读取最终 Storyboard 序列 | 无感知 |
| **2. 渲染合成** | 显示百分比进度条 | **[重活]** 调用 FFmpeg 按照 Storyboard 的入点出点进行视频切片、拼接、添加转场 | 无感知 |
| **3. 完成** | 弹出系统通知，显示文件路径 | 释放资源，更新项目状态为“已完成” | 记录一次成功的导出行为（用于数据分析） |

---

## 总结：这一架构的优势场景

1. **断网可用性**：即便断网，用户依然可以手动调整分镜、本地预览和导出，因为**“身体（Core）”**和**“眼睛（Client）”**都在本地。
2. **隐私极致化**：用户知道 AI 只是在帮他“搜关键词”和“排顺序”，他的原始视频原片从未离开过电脑。
3. **响应零延迟**：对于频繁的 UI 交互（如拖拽、点击），Client 直接和本地 Core 说话，没有公网延迟带来的顿挫感。
