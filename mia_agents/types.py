"""Dataclasses fijas compartidas por todas las entregas.

No editar. La infraestructura de evaluación importa estas clases
directamente y asume que sus campos y formas son estables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Una invocación de herramienta solicitada por el LLM."""

    id: str
    name: str
    arguments: str  # codificado en JSON


@dataclass
class LLMResponse:
    """Respuesta normalizada (independiente del proveedor) de una llamada al LLM.

    Campos para el bucle del agente: `content`, `tool_calls`, `input_tokens`,
    `output_tokens`. Metadatos del proveedor (p. ej. `stopReason`,
    `done_reason`) viven solo en `raw_response` para depuración.
    """

    content: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    input_tokens: int | None = None
    output_tokens: int | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class ToolSchema:
    """Descripción de una herramienta que el LLM puede invocar.

    Vive en el **agente** (`register_tool`). Pasá la lista de
    `ToolSchema` a `LLMClient.chat(..., tools=...)`; el cliente aplica
    `to_llm_spec()` al formatear para Ollama/Bedrock.

    Creá cada esquema con `ToolSchema.from_callable(fn)` (firma con
    `Annotated` + `Field` + docstring). No hace falta armar `parameters`
    a mano.
    """

    name: str
    description: str
    parameters: dict[str, Any]

    @classmethod
    def from_callable(
        cls,
        fn: Any,
        *,
        name: str | None = None,
        description: str | None = None,
    ) -> ToolSchema:
        """Deriva nombre, descripción y `parameters` desde la firma Python."""
        from mia_agents.tool_schema import tool_schema_from_callable

        return tool_schema_from_callable(fn, name=name, description=description)

    @classmethod
    def from_model(
        cls,
        model: Any,
        *,
        name: str,
        description: str,
    ) -> ToolSchema:
        """Deriva `parameters` desde un `pydantic.BaseModel`."""
        from mia_agents.tool_schema import tool_schema_from_model

        return tool_schema_from_model(model, name=name, description=description)

    def to_llm_spec(self) -> dict[str, Any]:
        """Dict con name/description/parameters; lo usa `llm_client._format_tools`."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }


@dataclass
class AgentStep:
    """Una iteración del bucle del agente en la que se invocó una herramienta."""

    tool_name: str | None
    tool_input: str | None
    tool_output: str | None
    error: str | None = None


@dataclass
class AgentResult:
    """Resultado final de `Agent.run`.

    `input_tokens` / `output_tokens` reflejan los totales acumulados por
    el agente a partir de los `LLMResponse` recibidos durante esta
    llamada a `run`. Permanecen `None` si ningún `LLMResponse` reportó
    tokens (p. ej. `MockLLMClient` sin tokens programados); de lo
    contrario, suman lo reportado tratando `None` por respuesta como 0.
    Sub-agentes invocados por herramientas NO se contabilizan aquí
    (sus tokens viven en su propio `AgentResult`).
    """

    answer: str
    steps: list[AgentStep] = field(default_factory=list)
    error: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
