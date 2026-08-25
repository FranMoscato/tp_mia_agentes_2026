"""Regresión: la ventana de contexto en tareas de un solo turno (M3).

En M1/M2 el agente es conversacional: cada `run()` agrega un mensaje `user`,
y la ventana desliza sobre TURNOS. En M3 el agente resuelve el escenario
entero dentro de UN solo `run()`, así que hay un único mensaje `user` (el
goal) y después solo bloques `assistant(tool_calls)` + sus `tool`.

La estrategia por turnos no tenía dónde cortar en ese caso y degeneraba: al
superar el presupuesto, la ventana colapsaba al goal pelado y el agente
perdía TODA la exploración a mitad de partida (justo en `hard`/`extreme`,
que son los que necesitan 13-21 tool-calls). Estos tests fijan el
comportamiento correcto.

Los tests de M2 no lo detectaban porque ejercitan conversaciones multiturno,
donde sí hay varios mensajes `user` donde cortar.
"""

from __future__ import annotations

import json

from mia_agents.llm_client import BedrockProvider
from mia_agents.testing import MockLLMClient
from mia_agents.tool_schema import FINAL_RESULT_TOOL_NAME
from mia_agents.types import LLMResponse, ToolCall, ToolSchema

from student_framework import build_agent
from student_framework.agent import GameState

_SIN_BACKOFF = {"retry_backoff_base": 0}
_GOAL = "GOAL: abrí la puerta principal"


def _tool_mirar():
    schema = ToolSchema(
        name="mirar",
        description="mira la sala",
        parameters={"type": "object", "properties": {}, "required": []},
    )
    return (lambda: "ves una llave [id: k1]", schema)


def _agente_de_partida(mock, **config):
    agent = build_agent(
        {
            "llm_client": mock,
            "register_default_tools": False,
            **_SIN_BACKOFF,
            **config,
        }
    )
    fn, schema = _tool_mirar()
    agent.register_tool(fn, schema)
    return agent


def _respuestas_con_tools(n: int) -> list[LLMResponse]:
    """n turnos pidiendo la misma tool y un cierre con texto."""
    return [
        LLMResponse(content=None, tool_calls=[ToolCall(id=f"c{i}", name="mirar", arguments="{}")])
        for i in range(n)
    ] + [LLMResponse(content="abrí la puerta")]


# ---------------------------------------------------------------------------
# El bug: colapso de la ventana
# ---------------------------------------------------------------------------


def test_ventana_no_colapsa_en_partida_larga() -> None:
    """Con un solo `user`, la ventana no se desploma al superar el presupuesto.

    Antes del fix, al pasar de `max_history_messages` la ventana caía a 1
    mensaje (solo el goal) y se quedaba ahí para el resto de la partida.
    """
    presupuesto = 10
    mock = MockLLMClient(_respuestas_con_tools(25))
    agent = _agente_de_partida(mock, max_history_messages=presupuesto, max_iterations=26)

    agent.run(_GOAL)

    largos = [len(c["messages"]) for c in mock.calls]
    # Una vez que el historial supera el presupuesto, la ventana se estabiliza
    # cerca del tope; nunca vuelve a 1.
    estables = largos[presupuesto:]
    assert estables, "el historial nunca llegó a superar el presupuesto"
    assert min(estables) > 1, (
        f"la ventana colapsó a {min(estables)} mensaje(s): se perdió la exploración"
    )
    assert min(estables) >= presupuesto - 2, (
        f"la ventana quedó en {min(estables)} con presupuesto {presupuesto}: "
        "se está desaprovechando el contexto"
    )


def test_ventana_conserva_observaciones_recientes() -> None:
    """El agente sigue viendo lo que acaba de observar, no solo el goal."""
    mock = MockLLMClient(_respuestas_con_tools(20))
    agent = _agente_de_partida(mock, max_history_messages=8, max_iterations=21)

    agent.run(_GOAL)

    ultima = mock.calls[-1]["messages"]
    assert any(
        m.get("role") == "tool" and "k1" in str(m.get("content")) for m in ultima
    ), "la ventana debe conservar las observaciones más recientes"


# ---------------------------------------------------------------------------
# Invariantes que deben seguir valiendo
# ---------------------------------------------------------------------------


def test_goal_y_presupuesto_en_toda_la_partida() -> None:
    """En cada llamada: el goal está, y la ventana no supera el presupuesto."""
    presupuesto = 9
    mock = MockLLMClient(_respuestas_con_tools(25))
    agent = _agente_de_partida(mock, max_history_messages=presupuesto, max_iterations=26)

    agent.run(_GOAL)

    for i, llamada in enumerate(mock.calls):
        mensajes = llamada["messages"]
        assert len(mensajes) <= presupuesto, (
            f"llamada {i}: {len(mensajes)} mensajes con presupuesto {presupuesto}"
        )
        assert mensajes[0].get("role") == "user", f"llamada {i}: no arranca en `user`"
        assert _GOAL in str(mensajes[0].get("content")), (
            f"llamada {i}: se perdió el goal — el agente no sabe qué está resolviendo"
        )


def test_no_deja_tool_calls_huerfanos() -> None:
    """Recortar nunca parte un bloque: cada `tool` sigue a su `assistant`."""
    mock = MockLLMClient(_respuestas_con_tools(25))
    agent = _agente_de_partida(mock, max_history_messages=8, max_iterations=26)

    agent.run(_GOAL)

    for i, llamada in enumerate(mock.calls):
        roles = [m.get("role") for m in llamada["messages"]]
        for j, role in enumerate(roles):
            if role == "tool":
                assert j > 0 and roles[j - 1] in ("assistant", "tool"), (
                    f"llamada {i}: mensaje `tool` huérfano en la posición {j} ({roles})"
                )


def test_ventana_alterna_roles_tras_normalizar_a_bedrock() -> None:
    """Bedrock Converse exige empezar en `user` y alternar roles.

    Los mensajes `tool` se normalizan a `user` (bloques `toolResult`), así que
    la comprobación se hace sobre la lista ya normalizada.
    """
    mock = MockLLMClient(_respuestas_con_tools(25))
    agent = _agente_de_partida(mock, max_history_messages=12, max_iterations=26)

    agent.run(_GOAL)

    for i, llamada in enumerate(mock.calls):
        roles = [m["role"] for m in BedrockProvider._normalize_messages(llamada["messages"])]
        assert roles[0] == "user", f"llamada {i}: Bedrock exige que el primero sea `user`"
        pegados = [
            (j, roles[j]) for j in range(len(roles) - 1) if roles[j] == roles[j + 1]
        ]
        assert not pegados, f"llamada {i}: roles consecutivos iguales en {pegados} ({roles})"


# ---------------------------------------------------------------------------
# Summarizer: la inyección del estado no puede romper los invariantes
# ---------------------------------------------------------------------------


def _mock_con_summarizer(turnos: int) -> MockLLMClient:
    """Intercala las respuestas del loop principal con las del summarizer."""
    estado = json.dumps(
        {
            "inventory": ["k1"],
            "current_location": "estudio",
            "visited_locations": ["estudio"],
            "succesful_actions": ["mirar"],
            "failed_actions": [],
            "observations": ["la llave k1 está en el estudio"],
            "known_exits": [],
        }
    )
    respuestas: list[LLMResponse] = []
    for i in range(turnos):
        respuestas.append(
            LLMResponse(content=None, tool_calls=[ToolCall(id=f"c{i}", name="mirar", arguments="{}")])
        )
        respuestas.append(
            LLMResponse(
                content=None,
                tool_calls=[ToolCall(id=f"m{i}", name=FINAL_RESULT_TOOL_NAME, arguments=estado)],
                input_tokens=5,
                output_tokens=3,
            )
        )
    respuestas.append(LLMResponse(content="abrí la puerta"))
    return MockLLMClient(respuestas)


def _llamadas_del_loop(mock) -> list[list[dict]]:
    """Filtra las llamadas del loop principal (las del summarizer ofrecen
    únicamente la tool `final_result`)."""
    return [
        c["messages"]
        for c in mock.calls
        if [t.name for t in (c.get("tools") or [])] != [FINAL_RESULT_TOOL_NAME]
    ]


def test_summarizer_respeta_el_presupuesto() -> None:
    """El estado no puede agregar un mensaje extra por encima del tope.

    Antes del fix se anteponía como un `user` aparte, así que la lista enviada
    al proveedor medía `max_history_messages + 1`.
    """
    presupuesto = 7
    mock = _mock_con_summarizer(12)
    agent = _agente_de_partida(
        mock, max_history_messages=presupuesto, max_iterations=13, use_summarizer=True
    )

    agent.run(_GOAL)

    for mensajes in _llamadas_del_loop(mock):
        assert len(mensajes) <= presupuesto, (
            f"{len(mensajes)} mensajes con presupuesto {presupuesto}"
        )


def test_summarizer_no_rompe_la_alternancia() -> None:
    """El bloque de estado no puede dejar dos `user` consecutivos.

    Antes del fix se anteponía un `user` delante de una ventana que ya
    empezaba en `user`; Bedrock Converse rechaza eso con ValidationException,
    que además no es transitorio y tumba la corrida entera.
    """
    mock = _mock_con_summarizer(12)
    agent = _agente_de_partida(
        mock, max_history_messages=9, max_iterations=13, use_summarizer=True
    )

    agent.run(_GOAL)

    for mensajes in _llamadas_del_loop(mock):
        roles = [m["role"] for m in BedrockProvider._normalize_messages(mensajes)]
        assert roles[0] == "user"
        assert not any(roles[j] == roles[j + 1] for j in range(len(roles) - 1)), (
            f"roles consecutivos iguales: {roles}"
        )


def test_summarizer_pone_el_estado_al_final() -> None:
    """El estado viaja en el último mensaje: mejor atención y no rompe el
    prefijo cacheable del prompt."""
    mock = _mock_con_summarizer(6)
    agent = _agente_de_partida(
        mock, max_history_messages=20, max_iterations=7, use_summarizer=True
    )

    agent.run(_GOAL)

    ultima = _llamadas_del_loop(mock)[-1]
    assert "ESTADO ACTUAL DE LA PARTIDA" in str(ultima[-1].get("content")), (
        "el estado debe ir en el último mensaje de la ventana"
    )
    previos = [str(m.get("content")) for m in ultima[:-1]]
    assert not any("ESTADO ACTUAL DE LA PARTIDA" in c for c in previos), (
        "el estado no debe aparecer también al principio"
    )


def test_summarizer_no_inyecta_estado_vacio() -> None:
    """En la primera llamada el estado está vacío: no se paga por un JSON de
    campos por defecto."""
    mock = _mock_con_summarizer(3)
    agent = _agente_de_partida(mock, max_iterations=4, use_summarizer=True)

    agent.run(_GOAL)

    primera = _llamadas_del_loop(mock)[0]
    assert not any(
        "ESTADO ACTUAL DE LA PARTIDA" in str(m.get("content")) for m in primera
    ), "no hay estado que inyectar todavía en la primera llamada"


def test_summarizer_no_muta_el_historial() -> None:
    """La inyección trabaja sobre una copia: `self.messages` queda limpio."""
    mock = _mock_con_summarizer(6)
    agent = _agente_de_partida(mock, max_iterations=7, use_summarizer=True)

    agent.run(_GOAL)

    assert agent._state != GameState(), "el summarizer debería haber actualizado el estado"
    assert not any(
        "ESTADO ACTUAL DE LA PARTIDA" in str(m.get("content")) for m in agent.messages
    ), "el bloque de estado no debe quedar pegado en el historial persistente"


# ---------------------------------------------------------------------------
# Contador de llamadas al LLM (lo que consume el harness)
# ---------------------------------------------------------------------------


def test_llm_calls_refleja_el_tope_de_iteraciones() -> None:
    """`llm_calls` llega a `max_iterations`, y `tool_calls` se queda uno abajo.

    Es exactamente la diferencia que hacía inalcanzable la categoría
    `exhausted_iterations` del harness.
    """
    mock = MockLLMClient(_respuestas_con_tools(30))
    agent = _agente_de_partida(mock, max_iterations=6)

    resultado = agent.run(_GOAL)

    assert agent.llm_calls == 6
    assert len(resultado.steps) == 5


def test_llm_calls_se_reinicia_por_run() -> None:
    """Cada `run()` cuenta sus propias llamadas."""
    mock = MockLLMClient(
        [
            LLMResponse(content=None, tool_calls=[ToolCall(id="a", name="mirar", arguments="{}")]),
            LLMResponse(content="listo"),
            LLMResponse(content="listo de nuevo"),
        ]
    )
    agent = _agente_de_partida(mock, max_iterations=10)

    agent.run(_GOAL)
    assert agent.llm_calls == 2

    agent.run("otra cosa")
    assert agent.llm_calls == 1
