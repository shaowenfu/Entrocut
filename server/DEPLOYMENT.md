# Server 端部署文档

## 概述

Entrocut Server 是基于 FastAPI 的云端后端服务，提供 Mock API 接口（MVP 阶段）。

- **服务名称**: entrocut-mock-server
- **默认端口**: 8001
- **契约版本**: 0.1.0-mock

---

## 目录结构

```
server/
├── main.py              # 应用入口
├── routes/              # API 路由
│   ├── mock.py         # Mock API
│   ├── auth.py         # 认证
│   ├── projects.py     # 项目管理
│   └── search.py       # 搜索
├── middleware/          # 中间件
│   ├── error_handler.py      # 错误处理
│   └── request_tracking.py   # 请求追踪
├── models/              # 数据模型
│   └── schemas.py      # API Schema
├── utils/               # 工具
│   ├── logger.py       # 日志工具
│   └── mock_data.py    # Mock 数据生成
├── tests/               # 测试
│   └── test_mock_api.py
├── Dockerfile           # Docker 镜像定义
├── requirements.txt     # Python 依赖
└── .env.example         # 环境变量模板
```

---

## 环境变量

### 必需配置

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `SERVER_PORT` | 服务监听端口 | 8001 |
| `LOG_LEVEL` | 日志级别 | INFO |
| `CONTRACT_VERSION` | 契约版本 | 0.1.0-mock |

### 可选配置（后续阶段使用）

| 变量名 | 说明 |
|--------|------|
| `DASHSCOPE_API_KEY` | 通义千问 API Key |
| `DASHVECTOR_API_KEY` | DashVector API Key |
| `DASHVECTOR_ENDPOINT` | DashVector 端点 |
| `MONGODB_URI` | MongoDB 连接字符串 |
| `MONGODB_DATABASE` | MongoDB 数据库名 |
| `JWT_SECRET_KEY` | JWT 密钥 |
| `JWT_ALGORITHM` | JWT 算法 |
| `JWT_EXPIRE_MINUTES` | JWT 过期时间（分钟） |
| `ENVIRONMENT` | 运行环境 (development/production) |

---

## 本地开发

### 前置要求

- Python 3.10+
- pip

### 安装依赖

```bash
cd server
pip install -r requirements.txt
```

### 配置环境变量

```bash
# 复制模板
cp .env.example .env

# 编辑配置（本地开发可使用默认值）
vim .env
```

### 启动服务

```bash
# 开发模式（自动重载）
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# 生产模式
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001 --workers 4
```

### 验证服务

```bash
# 健康检查
curl http://localhost:8001/health

# 运行冒烟测试
./scripts/smoke_test.sh
```

---

## Docker 部署

### 构建镜像

```bash
cd server
docker build -t entrocut-mock-server:latest .
```

### 运行容器

```bash
docker run -d \
  --name entrocut-mock-server \
  -p 8001:8001 \
  --restart unless-stopped \
  -e SERVER_PORT=8001 \
  -e LOG_LEVEL=INFO \
  -e CONTRACT_VERSION=0.1.0-mock \
  entrocut-mock-server:latest
```

### 查看日志

```bash
docker logs -f entrocut-mock-server
```

### 停止容器

```bash
docker stop entrocut-mock-server
docker rm entrocut-mock-server
```

---

## CI/CD 部署（ECS）

项目使用 GitHub Actions 自动部署到阿里云 ECS。

### 部署流程

```
main 分支变动
    ↓
GitHub Actions (Runner)
    ↓ 1. 构建 Docker 镜像
    ↓ 2. 推送到 GHCR
    ↓ 3. SSH 登录阿里云 ECS
    ↓
阿里云 ECS
    ↓ 4. Docker 登录 GHCR
    ↓ 5. 拉取最新镜像
    ↓ 6. 停止旧容器，启动新容器
    ↓ 7. 健康检查
```

### 触发部署

```bash
git push origin main
```

### GitHub Secrets 配置

在仓库设置中配置以下 Secrets：

| Secret 名称 | 说明 |
|-------------|------|
| `SERVER_SSH_HOST` | ECS 公网 IP |
| `SERVER_SSH_USER` | SSH 登录用户名 |
| `SERVER_SSH_KEY` | SSH 私钥 |
| `SERVER_SSH_PORT` | SSH 端口（可选，默认 22） |
| `DASHSCOPE_API_KEY` | 通义千问 API Key |
| `DASHVECTOR_API_KEY` | DashVector API Key |
| `DASHVECTOR_ENDPOINT` | DashVector 端点 |
| `MONGODB_ATLAS_URI` | MongoDB 连接字符串 |

### 部署后验证

```bash
# 本地运行冒烟测试
./scripts/smoke_test.sh https://your-domain.com

# 或在 ECS 上直接测试
curl https://your-domain.com/health
```

---

## 健康检查

### 端点

```
GET /health
```

### 响应

```json
{
  "status": "healthy",
  "service": "entrocut-mock-server",
  "version": "0.1.0-mock",
  "timestamp": "2026-02-07T10:30:00Z"
}
```

### Docker 健康检查

容器内置健康检查：

```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1
```

---

## API 端点

### Mock API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/mock/analyze` | Mock 分析接口 |
| POST | `/api/v1/mock/edl` | Mock EDL 接口 |

### 其他

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 |
| GET | `/docs` | API 文档（Swagger） |

---

## 重启与回滚

### 重启服务（Docker）

```bash
# 重启容器
docker restart entrocut-mock-server

# 等待健康检查
sleep 10
curl http://localhost:8001/health
```

### 回滚到上一版本

```bash
# 1. 查看镜像历史
docker images ghcr.io/sherwen/entrocut

# 2. 停止当前容器
docker stop entrocut-mock-server
docker rm entrocut-mock-server

# 3. 启动上一版本镜像
docker run -d \
  --name entrocut-mock-server \
  -p 8001:8001 \
  --restart unless-stopped \
  -e SERVER_PORT=8001 \
  -e LOG_LEVEL=INFO \
  ghcr.io/sherwen/entrocut:commit-<previous-sha>
```

---

## 日志与调试

### 日志格式

服务输出结构化 JSON 日志：

```json
{
  "timestamp": "2026-02-07T10:30:00.123456Z",
  "level": "INFO",
  "service": "entrocut-mock-server",
  "logger": "entrocut.api.mock",
  "message": "POST /api/v1/mock/analyze - 200",
  "event": "api_response",
  "method": "POST",
  "path": "/api/v1/mock/analyze",
  "status_code": 200,
  "duration_ms": 123.456,
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "job_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 日志查询

```bash
# 按请求 ID 查询
docker logs entrocut-mock-server 2>&1 | grep "550e8400"

# 按 job_id 查询
docker logs entrocut-mock-server 2>&1 | grep "job_id"

# 只看错误
docker logs entrocut-mock-server 2>&1 | grep '"level":"ERROR"'

# 使用 jq 解析
docker logs entrocut-mock-server 2>&1 | jq '. | select(.job_id == "xxx")'
```

---

## 测试

### 运行单元测试

```bash
cd server
pytest tests/test_mock_api.py -v
```

### 运行冒烟测试

```bash
# 本地测试
./scripts/smoke_test.sh

# 远程测试
./scripts/smoke_test.sh https://your-domain.com
```

---

## 常见问题

### 1. 端口被占用

```bash
# 查看占用进程
lsof -i :8001

# 或使用 netstat
netstat -tulpn | grep 8001
```

### 2. 容器无法启动

```bash
# 查看容器日志
docker logs entrocut-mock-server

# 检查容器状态
docker ps -a | grep entrocut
```

### 3. 健康检查失败

```bash
# 手动执行健康检查
curl -v http://localhost:8001/health

# 检查服务是否运行
docker ps | grep entrocut-mock-server
```

---

## 监控与告警

建议配置以下监控指标：

1. **服务可用性**: 定期健康检查
2. **请求延迟**: duration_ms 分布
3. **错误率**: 非 200 状态码比例
4. **容器健康**: Docker health status

---

## 安全建议

1. 生产环境关闭 CORS 允许所有来源
2. 使用 HTTPS 配置 SSL 证书
3. 限制 API 请求速率
4. 敏感信息使用环境变量，不写入代码
5. 定期更新依赖包版本
