from __future__ import annotations

from dataclasses import dataclass

from app.gateways.server_gateway import MockServerGateway, ServerGateway
from app.repositories.project_repository import ProjectRepositoryShell
from app.services.websocket_hub import ProjectWebSocketHub
from app.tools.mocks import MockFrameExtractionTool, MockRenderTool, MockSegmentationTool
from app.tools.registry import ToolRegistry
from app.workflows.launchpad import LaunchpadWorkflowShell
from app.workflows.workspace import WorkspaceWorkflowShell


@dataclass(slots=True)
class CoreRuntime:
    websocket_hub: ProjectWebSocketHub
    tool_registry: ToolRegistry
    server_gateway: ServerGateway
    project_repository: ProjectRepositoryShell
    launchpad_workflow: LaunchpadWorkflowShell
    workspace_workflow: WorkspaceWorkflowShell


def build_core_runtime() -> CoreRuntime:
    hub = ProjectWebSocketHub()
    registry = ToolRegistry()
    registry.register(MockSegmentationTool())
    registry.register(MockFrameExtractionTool())
    registry.register(MockRenderTool())

    repository = ProjectRepositoryShell()
    gateway = MockServerGateway()

    return CoreRuntime(
        websocket_hub=hub,
        tool_registry=registry,
        server_gateway=gateway,
        project_repository=repository,
        launchpad_workflow=LaunchpadWorkflowShell(hub),
        workspace_workflow=WorkspaceWorkflowShell(hub),
    )
