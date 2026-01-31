本方案基于“端云协同”架构，明确了客户端本地处理与云端逻辑分发的各项技术指标。

1. 客户端技术栈 (本地端)

客户端负责视频文件的本地扫描、特征提取、本地检索结果存储以及最终的视频合并。

应用框架：Electron

核心逻辑：采用主进程（Node.js）与渲染进程（React）分离架构，主进程通过 child_process 调度本地算法引擎。

本地算法引擎：Python 3.10+

核心库：PySceneDetect（镜头切分）、OpenCV/FFmpeg-python（抽帧处理）、DashScope SDK（云端 API 调用）。

分发方式：内置 Python 虚拟环境及静态 FFmpeg 二进制文件。

前端 UI：React 18 + Tailwind CSS

组件库：Shadcn UI。

状态管理：TanStack Query (React Query) 处理 API 异步状态。

本地数据库：SQLite

用途：存储视频文件指纹（Hash）、本地绝对路径、镜头切分时间轴元数据及处理任务状态。

2. 云端后端技术栈 (逻辑中控)

云端负责用户权限校验、向量库路由以及非向量业务数据的持久化。

服务端框架：FastAPI (Python)

性能保障：利用全异步（Asynchronous）架构处理高并发的向量库查询请求。

通信协议：HTTP/HTTPS (RESTful API)

交互工具：Axios (客户端调用)。

3. 数据存储与向量检索 (数据层)

云端业务库：MongoDB Atlas

用途：托管于云端的 NoSQL 数据库，存储用户信息、全局搜索记录及跨设备同步的配置。

云端向量库：阿里云 DashVector

用途：存储 1024 维视频语义向量，实现基于用户 ID (user_id) 的分区检索。

4. 系统架构逻辑闭环

| 环节 | 执行位置 | 技术组件 | 关键动作 |

| 视频切分| 本地 | PySceneDetect | 在本地硬盘完成镜头边界检测，不产生云端带宽成本。 |

| 特征提取 | 本地 | Python + FFmpeg | 本地抽取 10s 镜头中的 8 帧关键图片。 |

| 向量化 | 云端 | Qwen3-VL-Embedding | 接收本地上传的 Base64 图片，返回 1024 维向量。 |

| 向量存储 | 云端 | DashVector | 将向量连同 user_id 和本地路径存入阿里云索引。 |

| 检索理解 | 云端 | Qwen3-VL-Flash | 对检索结果进行细粒度分析，返回标准 JSON 结构信息。 |

| 业务同步 | 云端 | MongoDB Atlas | 记录用户检索历史及个性化标签。 |

| 本地剪辑 | 本地 | FFmpeg (Native) | 依据云端返回的时间戳，在本地硬盘直接合并视频片段。 |

5. 核心选型考量

Electron + SQLite：确保了对本地文件系统操作的稳定性，同时 SQLite 的无服务器特性保证了客户端的独立运行能力。

FastAPI + MongoDB Atlas：利用 MongoDB Atlas 的动态模式（Schema-less）特性，能够快速存储和扩展 Qwen 模型输出的各种复杂 JSON 结构。

内网性能优化：通过在本地完成所有编解码（FFmpeg）和切分（PySceneDetect），将网络传输负载从“GB级视频”降至“KB级图片”，极大提升用户感知的响应速度。