"""Cliente LLM programable para tests.

Uso:
    mock = MockLLMClient([
        LLMResponse(content=None, tool_calls=[ToolCall("c1", "calculator", '{"left_operand":2,"right_operand":2,"operator":"+"}')]),
        LLMResponse(content="La respuesta es 4."),
    ])
    agent = MyAgent(llm_client=mock)
    result = agent.run("...")
"""

from __future__ import annotations

from typing import Any

from mia_agents.types import LLMResponse, ToolSchema

ToolSpecInput = ToolSchema | dict[str, Any]


class MockLLMClient:
    """Devuelve `LLMResponse`s prefabricados en orden; lanza excepciones programadas si así se indica.

    Cada llamada a `chat()` registra los argumentos recibidos en `self.calls`,
    para que los tests puedan validar lo que el agente envió al modelo.
    """

    def __init__(self, responses: list[LLMResponse | Exception]) -> None:
        self._responses: list[LLMResponse | Exception] = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[ToolSpecInput] | None = None,
        system: str | None = None,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": messages,
                "tools": tools,
                "system": system,
                "temperature": temperature,
                "response_format": response_format,
            }
        )
        if not self._responses:
            raise RuntimeError(
                "MockLLMClient se quedó sin respuestas programadas. "
                f"chat() fue llamado {len(self.calls)} veces."
            )
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def call_count(self) -> int:
        return len(self.calls)
