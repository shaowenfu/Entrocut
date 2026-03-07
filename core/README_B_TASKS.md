# 工程师B任务实现总结

## 完成的任务

### 3.1 Core 资产去重、路径规范化与重扫幂等

**新增文件:**
- `core/app/tools/path_normalizer.py` - 路径规范化工具
- `core/app/tools/media_scanner.py` - 媒体扫描工具
- `core/app/repositories/asset_repository.py` - 资产数据访问层

**核心功能:**
1. **路径规范化**: 处理跨平台路径问题
   - 解析软链接，获取真实路径
   - Windows驱动器大小写规范化
   - 生成稳定的source_hash用于去重

2. **媒体扫描**: 幂等扫描目录
   - 通过source_hash去重
   - 跳过已存在的资产
   - 支持自定义文件扩展名过滤

3. **数据访问**: 封装资产CRUD操作
   - 线程安全的数据库操作
   - 利用UNIQUE约束保证幂等
   - 批量插入优化

**使用示例:**
```python
from app.tools.path_normalizer import PathNormalizerTool
from app.tools.media_scanner import MediaScannerTool

# 规范化路径
normalizer = PathNormalizerTool()
result = normalizer.run('/path/to/video.mp4')
source_hash = result.payload['source_hash']

# 扫描目录并去重
scanner = MediaScannerTool(normalizer)
scan_result = scanner.run(
    folder_path='/path/to/folder',
    existing_hashes={'hash1', 'hash2'}  # 已存在的hash集合
)
new_assets = scan_result.payload['new_assets']
```

### 3.2 Ingest 阶段化进度模型

**新增/修改文件:**
- `core/app/schemas/events.py` - 添加IngestProgressPayload
- `core/app/tools/ingest_coordinator.py` - Ingest协调器
- `core/app/workflows/ingest.py` - Ingest工作流

**核心功能:**
1. **阶段定义**: 6个处理阶段
   - scan (5%) - 扫描
   - segment (25%) - 切分
   - extract_frames (20%) - 抽帧
   - embed (25%) - 向量化
   - index (15%) - 索引
   - render (10%) - 渲染

2. **进度跟踪**: 细粒度进度管理
   - 阶段内进度 (0.0-1.0)
   - 总体进度 (0.0-1.0)
   - 阶段状态统计

3. **实时通知**: 通过WebSocket推送进度

**使用示例:**
```python
from app.tools.ingest_coordinator import IngestCoordinatorTool

coordinator = IngestCoordinatorTool()

# 启动阶段
coordinator.run('start_phase', phase='segment', total_items=10)

# 更新进度
coordinator.run('update_progress', phase='segment', items_processed=5)

# 完成阶段
coordinator.run('complete_phase', phase='segment')

# 获取总体进度
result = coordinator.run('get_overall_progress')
overall_progress = result.payload['overall_progress']
```

### 3.3 增量 ingest 与全量重跑的策略切分

**新增文件:**
- `core/app/schemas/ingest.py` - Ingest配置Schema
- `core/app/repositories/ingest_state_repository.py` - Ingest状态仓库

**核心功能:**
1. **策略模式**: 支持两种处理模式
   - **增量模式** (INCREMENTAL): 只处理新增和失败的资产
   - **全量模式** (FULL): 重新处理所有资产

2. **状态跟踪**: 跟踪每个资产在各阶段的完成状态
   - scan_completed
   - segment_completed
   - frames_extracted
   - embedding_completed
   - indexed
   - preview_rendered

3. **配置灵活**: 支持自定义配置
   - force_rescan: 强制重扫
   - reprocess_failed: 重新处理失败资产
   - skip_phases: 跳过特定阶段

**使用示例:**
```python
from app.schemas.ingest import IngestConfig, IngestMode

# 增量模式
incremental_config = IngestConfig(
    mode=IngestMode.INCREMENTAL,
    reprocess_failed=True
)

# 全量模式
full_config = IngestConfig(
    mode=IngestMode.FULL,
    force_rescan=True
)
```

### 3.5 Render Preview 与 Export Output 分离

**新增文件:**
- `core/app/schemas/render.py` - 渲染配置Schema
- `core/app/tools/preview_renderer.py` - 预览渲染工具
- `core/app/tools/export_renderer.py` - 导出渲染工具
- `core/app/workflows/render.py` - 渲染工作流

**核心功能:**
1. **预览渲染 (Preview)**:
   - 快速编码（webm/vp9）
   - 低分辨率（480p/720p/1080p）
   - **幂等**: 重复调用覆盖旧预览
   - 缓存在本地临时目录

2. **导出渲染 (Export)**:
   - 高质量编码（h264/h265）
   - 原始分辨率或指定分辨率
   - **不可变**: 每次生成新文件（带时间戳）
   - 输出到用户指定位置

**使用示例:**
```python
from app.tools.preview_renderer import PreviewRendererTool
from app.tools.export_renderer import ExportRendererTool

# 生成预览（幂等）
preview = PreviewRendererTool()
preview_result = preview.run(
    timeline_json={'project_id': 'proj1', 'duration_ms': 30000},
    quality='low',
    output_format='webm'
)

# 导出最终视频（不可变）
export = ExportRendererTool()
export_result = export.run(
    timeline_json={'project_id': 'proj1', 'duration_ms': 30000},
    format='mp4',
    resolution='1080p',
    codec='h264'
)
```

## 验证方法

### 运行回归测试

```bash
bash scripts/test_unit.sh
```

### 最小回归命令

1. **路径去重测试:**
```bash
cd core && source venv/bin/activate && python -c "
from app.tools.path_normalizer import PathNormalizerTool
n = PathNormalizerTool()
r = n.run('/tmp/test.mp4')
print(f'source_hash: {r.payload[\"source_hash\"]}')
"
```

2. **阶段进度测试:**
```bash
cd core && source venv/bin/activate && python -c "
from app.tools.ingest_coordinator import IngestCoordinatorTool
c = IngestCoordinatorTool()
c.run('start_phase', phase='scan', total_items=10)
c.run('update_progress', phase='scan', items_processed=5)
r = c.run('complete_phase', phase='scan')
print(f'overall_progress: {r.payload[\"overall_progress\"]}')
"
```

3. **增量/全量模式测试:**
```bash
cd core && source venv/bin/activate && python -c "
from app.schemas.ingest import IngestConfig, IngestMode
inc = IngestConfig(mode=IngestMode.INCREMENTAL)
full = IngestConfig(mode=IngestMode.FULL)
print(f'增量模式: {inc.mode}, 全量模式: {full.mode}')
"
```

4. **预览/导出分离测试:**
```bash
cd core && source venv/bin/activate && python -c "
from app.tools.preview_renderer import PreviewRendererTool
from app.tools.export_renderer import ExportRendererTool
p = PreviewRendererTool()
e = ExportRendererTool()
pr = p.run({'project_id': 'test', 'duration_ms': 30000}, quality='low')
er = e.run({'project_id': 'test', 'duration_ms': 30000}, format='mp4')
print(f'预览: {pr.payload[\"preview_url\"]}')
print(f'导出: {er.payload[\"export_url\"]}')
"
```

## 架构亮点

1. **依赖注入**: 所有工具和仓库都通过Runtime组装，便于测试和维护
2. **职责分离**: Tools负责原子操作，Workflows负责流程编排，Repositories负责数据访问
3. **幂等设计**: 路径规范化、扫描去重、预览渲染都支持幂等操作
4. **不可变设计**: 导出渲染每次生成新文件，避免覆盖
5. **阶段化进度**: 精细的进度跟踪，提升用户体验

## 残留风险

1. **IngestWorkflow集成**: IngestWorkflow需要AssetRepository和IngestStateRepository，这些依赖数据库连接，在server.py中初始化
2. **真实FFmpeg集成**: 当前PreviewRenderer和ExportRenderer是mock实现，需要后续接入真实的FFmpeg
3. **性能优化**: 大规模文件扫描和处理的性能优化需要后续验证

## 协作协议遵守

✅ 只修改了允许的文件范围：
- core/app/tools/*
- core/app/repositories/*
- core/app/workflows/*
- core/app/schemas/*
- core/app/services/runtime.py

✅ 未修改禁止的文件：
- client/
- server/
- core/server.py的主入口路由和事件名

✅ 所有实现都挂在现有骨架后面，通过Runtime注册
