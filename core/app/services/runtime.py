from __future__ import annotations

from dataclasses import dataclass

from app.gateways.server_gateway import MockServerGateway, ServerGateway
from app.repositories.project_repository import ProjectRepositoryShell
from app.services.context_engineering import CoreContextEngineeringShell
from app.services.websocket_hub import ProjectWebSocketHub
from app.tools.export_renderer import ExportRendererTool
from app.tools.ingest_coordinator import IngestCoordinatorTool
from app.tools.media_scanner import MediaScannerTool
from app.tools.mocks import MockFrameExtractionTool, MockRenderTool, MockSegmentationTool
from app.tools.path_normalizer import PathNormalizerTool
from app.tools.preview_renderer import PreviewRendererTool
from app.tools.registry import ToolRegistry
from app.workflows.launchpad import LaunchpadWorkflowShell
from app.workflows.render import RenderWorkflow
from app.workflows.workspace import WorkspaceWorkflowShell


@dataclass(slots=True)
class CoreRuntime:
    websocket_hub: ProjectWebSocketHub
    tool_registry: ToolRegistry
    server_gateway: ServerGateway
    project_repository: ProjectRepositoryShell
    context_engineering: CoreContextEngineeringShell
    launchpad_workflow: LaunchpadWorkflowShell
    workspace_workflow: WorkspaceWorkflowShell
    # 新增workflows（注意：IngestWorkflow需要依赖注入，在server.py中初始化）
    render_workflow: RenderWorkflow | None = None


def build_core_runtime() -> CoreRuntime:
    """构建Core运行时

    注意：IngestWorkflow需要在server.py中初始化，因为它依赖AssetRepository和IngestStateRepository，
    而这些Repository需要访问数据库连接，数据库连接在server.py中管理。
    """
    hub = ProjectWebSocketHub()

    # 创建工具注册器
    registry = ToolRegistry()

    # 注册路径规范化和扫描工具
    path_normalizer = PathNormalizerTool()
    registry.register(path_normalizer)
    registry.register(MediaScannerTool(path_normalizer))

    # 注册Ingest协调器
    registry.register(IngestCoordinatorTool())

    # 注册渲染工具
    registry.register(PreviewRendererTool())
    registry.register(ExportRendererTool())

    # 保留mock工具用于测试和回退
    registry.register(MockSegmentationTool())
    registry.register(MockFrameExtractionTool())
    registry.register(MockRenderTool())

    # 创建repositories和gateways
    repository = ProjectRepositoryShell()
    gateway = MockServerGateway()
    context_engineering = CoreContextEngineeringShell()

    # 创建workflows
    launchpad = LaunchpadWorkflowShell(hub)
    workspace = WorkspaceWorkflowShell(hub)

    # 创建渲染工作流
    render_workflow = RenderWorkflow(
        preview_renderer=PreviewRendererTool(),
        export_renderer=ExportRendererTool(),
        launchpad=launchpad,
    )

    return CoreRuntime(
        websocket_hub=hub,
        tool_registry=registry,
        server_gateway=gateway,
        project_repository=repository,
        context_engineering=context_engineering,
        launchpad_workflow=launchpad,
        workspace_workflow=workspace,
        render_workflow=render_workflow,
    )
