from __future__ import annotations

from app.tools.registry import ToolResult


class MockSegmentationTool:
    name = "segment"

    def run(self, **_: object) -> ToolResult:
        return ToolResult(
            ok=True,
            payload={
                "scene_count": 3,
                "segments": [
                    {"start_ms": 0, "end_ms": 4200},
                    {"start_ms": 4200, "end_ms": 9600},
                    {"start_ms": 9600, "end_ms": 15000},
                ],
            },
        )


class MockFrameExtractionTool:
    name = "extract_frames"

    def run(self, **_: object) -> ToolResult:
        return ToolResult(
            ok=True,
            payload={
                "frame_sheet_count": 3,
                "sheets": ["mock://frame-sheet/1", "mock://frame-sheet/2", "mock://frame-sheet/3"],
            },
        )


class MockRenderTool:
    name = "render_preview"

    def run(self, **_: object) -> ToolResult:
        return ToolResult(
            ok=True,
            payload={
                "preview_url": "mock://preview/latest",
                "duration_ms": 30000,
            },
        )
