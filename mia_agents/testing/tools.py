"""Herramientas prefabricadas que utiliza la suite de conformidad."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any

from pydantic import Field

from mia_agents.types import ToolSchema


@dataclass
class RecordingTool:
    """Herramienta de test que registra cada invocación y devuelve un valor fijo."""

    return_value: str = "ok"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def __call__(self, **kwargs: Any) -> str:
        self.calls.append(kwargs)
        return self.return_value


def make_recording_tool(
    name: str = "record",
    description: str = "Herramienta de test: registra sus entradas y devuelve un valor fijo.",
    return_value: str = "ok",
) -> tuple[RecordingTool, ToolSchema]:
    tool = RecordingTool(return_value=return_value)

    def record(
        text: Annotated[
            str,
            Field(description="Texto arbitrario para registrar."),
        ],
    ) -> str:
        return tool(text=text)

    schema = ToolSchema.from_callable(
        record,
        name=name,
        description=description,
    )
    return tool, schema
