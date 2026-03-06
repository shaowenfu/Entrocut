from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ProjectProjection:
    project_id: str
    title: str
    ai_status: str


class ProjectRepositoryShell:
    """
    Phase 2 skeleton only.
    真正的 SQLite 读写仍暂时由 legacy core/server.py 持有，
    后续会逐步迁移到这个 repository 层。
    """

    def get_projection(self, project_id: str) -> ProjectProjection:
        return ProjectProjection(
            project_id=project_id,
            title=project_id,
            ai_status="mock_projection",
        )

