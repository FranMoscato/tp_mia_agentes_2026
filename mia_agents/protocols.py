"""Protocolos fijos.

Cualquier agente entregado para evaluación debe satisfacer `Agent`. El
runner de la CLI y todos los tests de conformidad dependen de estas firmas.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

from mia_agents.types import AgentResult, LLMResponse, ToolSchema

# Re-export para anotar implementaciones de LLMClient.
ToolSpecInput = ToolSchema | dict[str, Any]


_TSchema = TypeVar("_TSchema")


@runtime_checkable
class LLMClient(Protocol):
    """Wrapper de una sola llamada sobre un proveedor de LLM.

    `tools` es una lista de `ToolSchema` (recomendado) o dicts con
    `name`, `description` y `parameters`. El cliente LLM aplica
    `to_llm_spec()` al llamar al proveedor.

    `response_format` recibe un JSON Schema representado como `dict`.
    Cuando se pasa, el proveedor debe pedirle al modelo una respuesta JSON
    que respete ese schema. El agente sigue siendo responsable de validar
    la salida si necesita garantías fuertes.
    """

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpecInput] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse: ...


@runtime_checkable
class Agent(Protocol):
    """Contrato que toda entrega debe implementar.

    `register_tool` recibe un callable y un `ToolSchema` (típicamente
    `ToolSchema.from_callable(fn)`). En cada `run`, el agente expone al LLM
    `tools=list(schemas)` en `chat` — el cliente aplica `to_llm_spec()`.
    El callable se invoca con kwargs alineados a esa firma y devuelve str.

    `run` recibe un único mensaje del usuario y devuelve un `AgentResult`.

    Estado de la conversación:
      - M1: cada llamada a `run` se trata como una interacción
        independiente (sin estado persistente entre llamadas).
      - M2: el agente es *estatal*. Llamadas sucesivas a `run` sobre la
        misma instancia continúan la conversación. La gestión del
        historial (resumen, recorte, ventana, recuperación, etc.) es
        responsabilidad del agente.
    """

    def register_tool(
        self,
        tool: Callable[..., str],
        schema: ToolSchema,
    ) -> None: ...

    def run(self, user_message: str) -> AgentResult: ...

    def structured_call(
        self,
        prompt: str,
        schema: type[_TSchema],
        max_repair_attempts: int = 2,
    ) -> _TSchema:
        """Pide al LLM una respuesta estructurada validada contra `schema`.

        M2: el agente recibe un `prompt` y una clase `schema` (típicamente
        un `pydantic.BaseModel`), llama al LLM y devuelve una instancia
        de `schema` con la salida parseada y validada. Si el LLM produce
        salida malformada, debe reintentar dándole contexto del fallo
        (modo de reparación) hasta `max_repair_attempts` veces antes de
        levantar una excepción.

        M2 exige la herramienta sintética `final_result`
        (`mia_agents.tool_schema.FINAL_RESULT_TOOL_NAME`): el agente la
        ofrece al LLM con un `ToolSchema` derivado de `schema`, valida los
        `arguments` del tool call y reintenta con contexto de reparación si
        falla. No se acepta cerrar con texto libre en `content`.
        El contrato observable: devolver instancia válida o levantar
        limpiamente tras agotar reintentos.

        En el M1 se acepta como stub (`NotImplementedError`); el contrato
        se verifica en los tests de M2. El bucle de `run(...)` en M1/M2
        sigue cerrando con texto sin `tool_calls` salvo que documenten
        una extensión propia con `final_result` en `run`.
        """
        ...
