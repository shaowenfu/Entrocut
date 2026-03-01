# Entrocut Monorepo Baseline

本仓库已清理为最小 `Monorepo（单仓多包）` 骨架，仅保留：

1. `client/`：前端壳层（React + Vite）。
2. `core/`：本地算法服务壳层（FastAPI）。
3. `server/`：云端编排服务壳层（FastAPI）。
4. `docs/`：基线文档与契约说明。

## 快速启动

1. Client（前端壳层）
```bash
cd client
pnpm install
pnpm run dev
```

2. Core（本地服务壳层）
```bash
cd core
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --host 127.0.0.1 --port 8000 --reload
```

3. Server（云端服务壳层）
```bash
cd server
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8001 --reload
```

## 当前状态

1. 仅提供 `Health API（健康接口）` 与 `Contract Placeholder（契约占位接口）`。
2. 历史验证链路代码（`Mock API`、旧 `Pipeline`、旧脚本和测试资产）已移除。
