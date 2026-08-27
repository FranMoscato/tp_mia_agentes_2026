"""Corte de loop en runtime (Clase 7) — señal: tool + argumentos repetidos.

El harness ya medía la repetición *a posteriori* (`repeticiones_consecutivas`),
pero el agente no hacía nada con ella: seguía repitiendo hasta agotar
`max_iterations` —medimos rachas de hasta 23 llamadas idénticas—. Estos tests
fijan el comportamiento del corte, que usa esa misma señal EN RUNTIME.

Usan el `MockLLMClient` de la cátedra: sin API, deterministas.
"""

from __future__ import annotations

import json

from mia_agents.testing import MockLLMClient
from mia_agents.types import LLMResponse, ToolCall, ToolSchema

from student_framework import build_agent


def _schema() -> ToolSchema:
    return ToolSchema(
        name="mirar",
        description="Mira la sala",
        parameters={"type": "object", "properties": {}},
    )


def _respuesta_repetida(n: int) -> list[LLMResponse]:
    """`n` turnos pidiendo SIEMPRE la misma tool con los mismos argumentos."""
    salidas = [
        LLMResponse(
            content="",
            tool_calls=[ToolCall(id=f"c{i}", name="mirar", arguments=json.dumps({}))],
        )
        for i in range(n)
    ]
    salidas.append(LLMResponse(content="listo", tool_calls=[]))
    return salidas


def _agente(loop_breaker: bool, ejecuciones: list[str], **extra):
    agente = build_agent({
        "llm_client": MockLLMClient(_respuesta_repetida(8)),
        "register_default_tools": False,
        "max_iterations": 10,
        "loop_breaker": loop_breaker,
        **extra,
    })

    def mirar() -> str:
        ejecuciones.append("mirar")
        return "Ves una sala vacía."

    agente.register_tool(mirar, _schema())
    return agente


def test_sin_loop_breaker_la_tool_se_ejecuta_siempre():
    """Baseline: el agente repite sin que nada lo corte (comportamiento previo)."""
    ejecuciones: list[str] = []
    agente = _agente(False, ejecuciones)
    agente.run("mirá la sala")
    assert len(ejecuciones) == 8
    assert agente.loops_cortados == 0


def test_con_loop_breaker_deja_de_ejecutar_la_tool_repetida():
    """A partir del umbral, la tool NO se vuelve a ejecutar."""
    ejecuciones: list[str] = []
    agente = _agente(True, ejecuciones)
    agente.run("mirá la sala")
    # Umbral 3: se ejecuta 2 veces y a la 3ra interviene el corte.
    assert len(ejecuciones) == 2
    assert agente.loops_cortados == 6


def test_el_corte_avisa_al_modelo_en_vez_de_matar_el_loop():
    """Es un empujón, no un corte duro: el mensaje vuelve como observación."""
    ejecuciones: list[str] = []
    agente = _agente(True, ejecuciones)
    agente.run("mirá la sala")
    avisos = [
        m for m in agente.messages
        if m.get("role") == "tool" and "[bucle detectado]" in (m.get("content") or "")
    ]
    assert avisos, "el corte debe devolver una observación al modelo"
    assert "probá otra herramienta" in avisos[0]["content"]


def test_el_umbral_es_configurable():
    ejecuciones: list[str] = []
    agente = _agente(True, ejecuciones, loop_threshold=5)
    agente.run("mirá la sala")
    assert len(ejecuciones) == 4


def test_el_contador_se_reinicia_entre_corridas():
    """`loops_cortados` es del último `run()`, no acumulado."""
    ejecuciones: list[str] = []
    agente = _agente(True, ejecuciones)
    agente.run("mirá la sala")
    primero = agente.loops_cortados
    assert primero > 0
    agente._llm = MockLLMClient(_respuesta_repetida(8))
    agente.run("mirá otra vez")
    assert agente.loops_cortados == primero  # misma cantidad, no el doble


def test_alternar_tools_no_dispara_el_corte():
    """La señal es tool+argumentos CONSECUTIVOS: alternar no es un loop."""
    salidas = []
    for i in range(6):
        nombre = "mirar" if i % 2 == 0 else "contar"
        salidas.append(LLMResponse(
            content="",
            tool_calls=[ToolCall(id=f"c{i}", name=nombre, arguments=json.dumps({}))],
        ))
    salidas.append(LLMResponse(content="listo", tool_calls=[]))

    ejecuciones: list[str] = []
    agente = build_agent({
        "llm_client": MockLLMClient(salidas),
        "register_default_tools": False,
        "max_iterations": 10,
        "loop_breaker": True,
    })

    def mirar() -> str:
        ejecuciones.append("mirar")
        return "sala vacía"

    def contar() -> str:
        ejecuciones.append("contar")
        return "hay 3 objetos"

    agente.register_tool(mirar, _schema())
    agente.register_tool(contar, ToolSchema(
        name="contar", description="Cuenta objetos",
        parameters={"type": "object", "properties": {}},
    ))
    agente.run("explorá")
    assert agente.loops_cortados == 0
    assert len(ejecuciones) == 6
