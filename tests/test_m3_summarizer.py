"""Tests del flag `use_summarizer` (M3).

Verifican el contrato del summarizer de estado, que es un brazo del
experimento "resumen on/off":

  - Con el flag APAGADO (default) el agente no hace llamadas LLM extra ni
    inyecta el estado: M1/M2 y el modo ReAct puro quedan intactos.
  - Con el flag ENCENDIDO, antes de la próxima llamada se re-deriva el
    `GameState` (una llamada LLM extra vía `structured_call`), se inyecta el
    bloque "ESTADO ACTUAL DE LA PARTIDA" en la ventana del loop principal y su
    costo se contabiliza APARTE en `memory_input_tokens`/`memory_output_tokens`.
"""

from __future__ import annotations

import json

from mia_agents.testing import MockLLMClient
from mia_agents.tool_schema import FINAL_RESULT_TOOL_NAME
from mia_agents.types import LLMResponse, ToolCall, ToolSchema

from student_framework import build_agent

# Sin espera entre reintentos para tests rápidos.
_SIN_BACKOFF = {"retry_backoff_base": 0}


def _tool_mirar():
    """Una tool determinista para disparar un turno de herramientas."""
    schema = ToolSchema(
        name="mirar",
        description="mira la sala",
        parameters={"type": "object", "properties": {}, "required": []},
    )
    return (lambda: "ves una llave", schema)


def _mirar_call(cid: str = "c1") -> ToolCall:
    return ToolCall(id=cid, name="mirar", arguments=json.dumps({}))


def test_summarizer_off_no_hace_llamadas_extra() -> None:
    """Flag apagado (default): ni llamadas LLM extra ni estado inyectado."""
    mock = MockLLMClient(
        [
            LLMResponse(content=None, tool_calls=[_mirar_call()]),
            LLMResponse(content="listo"),
        ]
    )
    agent = build_agent({"llm_client": mock, **_SIN_BACKOFF})  # use_summarizer False
    fn, schema = _tool_mirar()
    agent.register_tool(fn, schema)

    result = agent.run("abrí la puerta")

    assert result.answer == "listo"
    assert mock.call_count == 2  # solo las 2 llamadas del loop principal
    assert agent.memory_input_tokens == 0
    assert agent.memory_output_tokens == 0
    # No se inyectó el bloque de estado en ninguna llamada.
    for llamada in mock.calls:
        for m in llamada["messages"]:
            assert "ESTADO ACTUAL DE LA PARTIDA" not in str(m.get("content"))


def test_summarizer_on_invoca_memoria_inyecta_estado_y_cuenta_tokens() -> None:
    """Flag encendido: corre update_memory (1 llamada extra), inyecta el estado
    y contabiliza su costo aparte."""
    game_state_json = json.dumps(
        {
            "inventory": ["llave"],
            "current_location": "sala",
            "visited_locations": ["sala"],
            "succesful_actions": ["mirar"],
            "failed_actions": [],
            "observations": ["hay una llave en la sala"],
            "known_exits": [],
        }
    )
    mock = MockLLMClient(
        [
            # 1) loop principal: pide la tool
            LLMResponse(content=None, tool_calls=[_mirar_call()]),
            # 2) update_memory -> structured_call: devuelve el GameState
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="m1",
                        name=FINAL_RESULT_TOOL_NAME,
                        arguments=game_state_json,
                    )
                ],
                input_tokens=11,
                output_tokens=7,
            ),
            # 3) loop principal: respuesta final
            LLMResponse(content="listo"),
        ]
    )
    agent = build_agent(
        {"llm_client": mock, "use_summarizer": True, **_SIN_BACKOFF}
    )
    fn, schema = _tool_mirar()
    agent.register_tool(fn, schema)

    result = agent.run("abrí la puerta")

    assert result.answer == "listo"
    # Hubo una llamada LLM EXTRA respecto al modo off: la del summarizer.
    assert mock.call_count == 3
    # El costo del resumen se contabilizó APARTE del agente principal.
    assert agent.memory_input_tokens == 11
    assert agent.memory_output_tokens == 7
    # El estado quedó actualizado con lo que devolvió la memoria.
    assert "llave" in agent._state.inventory
    assert agent._state.current_location == "sala"
    # La última llamada del loop principal llevó el estado inyectado.
    ultima = mock.calls[-1]["messages"]
    assert any(
        "ESTADO ACTUAL DE LA PARTIDA" in str(m.get("content")) for m in ultima
    ), "el loop principal debe recibir el bloque de estado cuando el flag está on"
