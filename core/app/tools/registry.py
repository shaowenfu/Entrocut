from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class ToolResult:
    ok: bool
    payload: dict[str, Any] = field(default_factory=dict)


class Tool(Protocol):
    name: str

    def run(self, **kwargs: Any) -> ToolResult: ...


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> Tool:
        return self._tools[tool_name]

    def list_names(self) -> list[str]:
        return sorted(self._tools)

