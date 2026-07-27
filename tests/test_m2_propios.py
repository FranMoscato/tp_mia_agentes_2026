"""Tests propios del equipo para el Milestone 2.

Complementan los tests de conformidad (`tests/conformance/test_m2.py`)
cubriendo los comportamientos que el enunciado pide y la suite oficial no
ejercita directamente:

  - Resiliencia: fallos transitorios simulados (timeout, throttling) se
    reintentan y la ejecución termina con éxito; los errores no transitorios
    afloran sin reintentos.
  - Recencia: el último mensaje de usuario aparece en TODAS las llamadas al
    LLM, incluso con presupuestos de historial mínimos.
  - Salida estructurada: un prompt deliberadamente roto dispara el flujo de
    reparación y se recupera.
  - Errores recuperables de las tools: mensajes accionables de la calculadora
    y el lector de archivos, y un ciclo completo de recuperación vía agente.
"""

from __future__ import annotations

import json

import pytest

from mia_agents.testing import MockLLMClient
from mia_agents.types import LLMResponse, ToolCall

from student_framework import build_agent
from student_framework.tools.calculator import calculadora
from student_framework.tools.file_reader import (
    get_sandbox_root,
    leer_archivo,
    set_sandbox_root,
)

# Config común: sin espera entre reintentos para que los tests sean rápidos.
_SIN_BACKOFF = {"retry_backoff_base": 0}


@pytest.fixture()
def sandbox(tmp_path):
    """Apunta el sandbox del lector de archivos a `tmp_path`."""
    anterior = get_sandbox_root()
    set_sandbox_root(tmp_path)
    yield tmp_path
    set_sandbox_root(anterior)


# ---------------------------------------------------------------------------
# Resiliencia: reintentos ante fallos transitorios
# ---------------------------------------------------------------------------


def test_timeout_del_llm_se_reintenta_y_termina_bien() -> None:
    """Un timeout transitorio del cliente LLM se reintenta y `run` tiene éxito."""
    mock = MockLLMClient(
        [
            TimeoutError("read timed out"),
            LLMResponse(content="respuesta tras el reintento"),
        ]
    )
    agent = build_agent({"llm_client": mock, **_SIN_BACKOFF})

    result = agent.run("hola")

    assert result.answer == "respuesta tras el reintento"
    assert mock.call_count == 2  # 1 fallo + 1 reintento exitoso


def test_throttling_del_llm_se_reintenta() -> None:
    """Un rate limit (throttling / 429) también se considera transitorio."""
    mock = MockLLMClient(
        [
            RuntimeError("ThrottlingException: Too many requests (429)"),
            RuntimeError("503 Service Unavailable"),
            LLMResponse(content="ok"),
        ]
    )
    agent = build_agent({"llm_client": mock, **_SIN_BACKOFF})

    result = agent.run("hola")

    assert result.answer == "ok"
    assert mock.call_count == 3


def test_error_no_transitorio_no_se_reintenta() -> None:
    """Un error de programación aflora limpio, sin reintentos silenciosos."""
    mock = MockLLMClient([ValueError("schema inválido")])
    agent = build_agent({"llm_client": mock, **_SIN_BACKOFF})

    with pytest.raises(ValueError):
        agent.run("hola")

    assert mock.call_count == 1  # no hubo reintentos


def test_reintentos_agotados_propagan_el_error() -> None:
    """Si el fallo transitorio persiste, tras agotar reintentos se propaga."""
    fallos = [TimeoutError("timed out") for _ in range(10)]
    mock = MockLLMClient(fallos)
    agent = build_agent({"llm_client": mock, "max_retries": 2, **_SIN_BACKOFF})

    with pytest.raises(TimeoutError):
        agent.run("hola")

    assert mock.call_count == 3  # 1 intento inicial + 2 reintentos


def test_tool_con_fallo_transitorio_se_reintenta() -> None:
    """Una tool que falla una vez con timeout se reintenta y el paso termina sin error."""
    intentos = {"n": 0}

    def tool_inestable(texto: str) -> str:
        intentos["n"] += 1
        if intentos["n"] == 1:
            raise TimeoutError("connection timed out")
        return "resultado ok"

    from mia_agents.types import ToolSchema

    schema = ToolSchema(
        name="tool_inestable",
        description="tool que falla la primera vez",
        parameters={
            "type": "object",
            "properties": {"texto": {"type": "string"}},
            "required": ["texto"],
        },
    )

    mock = MockLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(id="c1", name="tool_inestable", arguments=json.dumps({"texto": "x"}))
                ],
            ),
            LLMResponse(content="listo"),
        ]
    )
    agent = build_agent({"llm_client": mock, **_SIN_BACKOFF})
    agent.register_tool(tool_inestable, schema)

    result = agent.run("usá la tool")

    assert intentos["n"] == 2  # falló una vez y se reintentó
    assert result.steps[0].error is None
    assert result.steps[0].tool_output == "resultado ok"


# ---------------------------------------------------------------------------
# Memoria: invariante de recencia
# ---------------------------------------------------------------------------


def test_ultimo_mensaje_de_usuario_siempre_presente() -> None:
    """Con presupuesto mínimo, el último user aparece en TODAS las llamadas."""
    budget = 3
    mock = MockLLMClient([LLMResponse(content=f"r{i}") for i in range(15)])
    agent = build_agent({"llm_client": mock, "max_history_messages": budget})

    for i in range(10):
        agent.run(f"mensaje-{i}")

    for llamada in mock.calls:
        mensajes = llamada["messages"]
        assert len(mensajes) <= budget
        users = [m for m in mensajes if m.get("role") == "user"]
        assert users, "toda llamada al LLM debe incluir al menos un mensaje de usuario"

    # La última llamada debe contener exactamente el último mensaje enviado.
    ultima = mock.calls[-1]["messages"]
    assert any(
        m.get("role") == "user" and "mensaje-9" in str(m.get("content"))
        for m in ultima
    ), "el mensaje de usuario más reciente nunca puede descartarse"


def test_primer_turno_goal_se_conserva() -> None:
    """El primer mensaje de usuario (el goal) sigue presente aunque el
    historial supere el presupuesto (patrón preserve_first_user)."""
    budget = 4
    mock = MockLLMClient([LLMResponse(content=f"r{i}") for i in range(20)])
    agent = build_agent({"llm_client": mock, "max_history_messages": budget})

    agent.run("GOAL: resolver la tarea inicial")
    for i in range(10):
        agent.run(f"seguimiento-{i}")

    # En la última llamada, el historial es mucho mayor que el presupuesto:
    # el TURNO inicial completo (goal + su respuesta) debe encabezar la ventana.
    ultima = mock.calls[-1]["messages"]
    assert len(ultima) <= budget
    assert ultima[0].get("role") == "user" and "GOAL:" in str(ultima[0].get("content")), \
        "el goal debe encabezar la ventana"
    assert ultima[1].get("role") == "assistant", \
        "se preserva el turno completo: el goal va con su respuesta del asistente"

    # Coherencia conversacional: nunca dos mensajes `user` consecutivos.
    roles = [m.get("role") for m in ultima]
    assert not any(
        roles[i] == "user" and roles[i + 1] == "user" for i in range(len(roles) - 1)
    ), "la ventana no debe dejar dos turnos de usuario pegados"


def test_conversacion_larga_sigue_respondiendo() -> None:
    """Decenas de turnos con mensajes grandes: cada run devuelve answer no vacío."""
    turnos = 40
    mock = MockLLMClient([LLMResponse(content=f"respuesta {i}") for i in range(turnos)])
    agent = build_agent({"llm_client": mock, "max_history_messages": 8})

    for i in range(turnos):
        result = agent.run(f"turno {i}: " + "relleno " * 500)
        assert result.answer, f"el turno {i} devolvió una respuesta vacía"


# ---------------------------------------------------------------------------
# Salida estructurada: prompt roto dispara la reparación
# ---------------------------------------------------------------------------


def test_prompt_roto_dispara_reparacion_y_se_recupera() -> None:
    """Texto libre primero, `final_result` válido después: se recupera."""
    from pydantic import BaseModel

    from mia_agents.tool_schema import FINAL_RESULT_TOOL_NAME

    class Resumen(BaseModel):
        titulo: str
        cantidad: int

    mock = MockLLMClient(
        [
            # Respuesta rota a propósito: texto libre en lugar de la tool.
            LLMResponse(content="El título es X y la cantidad 3"),
            # Tras el prompt de reparación, responde bien.
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="fr-1",
                        name=FINAL_RESULT_TOOL_NAME,
                        arguments=json.dumps({"titulo": "X", "cantidad": 3}),
                    )
                ],
            ),
        ]
    )
    agent = build_agent({"llm_client": mock, **_SIN_BACKOFF})

    parsed = agent.structured_call(prompt="resumí esto", schema=Resumen)

    assert parsed == Resumen(titulo="X", cantidad=3)
    assert mock.call_count == 2
    # El segundo intento debe incluir un mensaje de reparación.
    mensajes_reintento = mock.calls[1]["messages"]
    assert any(
        m.get("role") == "user" and "final_result" in str(m.get("content"))
        for m in mensajes_reintento
    ), "el reintento debe llevar un prompt de reparación que mencione final_result"


# ---------------------------------------------------------------------------
# Tools: errores recuperables con mensajes accionables
# ---------------------------------------------------------------------------


def test_calculadora_operando_no_numerico_es_accionable() -> None:
    """El error indica qué parámetro falló y qué valor recibió."""
    resultado = calculadora("tres", 2, "+")
    assert resultado.startswith("Error:")
    assert "operando_a" in resultado  # qué parámetro
    assert "tres" in resultado  # qué valor llegó


def test_calculadora_string_numerico_se_convierte() -> None:
    """Un string numérico ('42') se acepta en lugar de fallar."""
    assert calculadora("42", "2", "/") == "21.0"


def test_calculadora_operador_invalido_lista_los_soportados() -> None:
    resultado = calculadora(2, 3, "**")
    assert resultado.startswith("Error:")
    for op in ("+", "-", "*", "%"):
        assert op in resultado  # lista los operadores permitidos


def test_lector_escape_del_sandbox_via_subdirectorio(sandbox) -> None:
    """'sub/../../x' contiene '..' y se rechaza explicando la regla."""
    resultado = leer_archivo("sub/../../x.txt")
    assert resultado.startswith("Error:")
    assert ".." in resultado


def test_recuperacion_de_error_en_calculadora_via_agente() -> None:
    """Ciclo completo: la tool falla con mensaje accionable y el LLM corrige.

    Turno 1: el LLM manda un operando no numérico -> error accionable.
    Turno 2: el LLM corrige los argumentos -> éxito.
    """
    mock = MockLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="c1",
                        name="calculadora",
                        arguments=json.dumps(
                            {"operando_a": "diez", "operando_b": 2, "operador": "+"}
                        ),
                    )
                ],
            ),
            LLMResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id="c2",
                        name="calculadora",
                        arguments=json.dumps(
                            {"operando_a": 10, "operando_b": 2, "operador": "+"}
                        ),
                    )
                ],
            ),
            LLMResponse(content="El resultado es 12."),
        ]
    )
    agent = build_agent({"llm_client": mock, **_SIN_BACKOFF})

    result = agent.run("sumá diez más dos")

    # El primer paso devolvió el error accionable COMO SALIDA de la tool
    # (no rompe el bucle) y el segundo tuvo éxito.
    assert "operando_a" in (result.steps[0].tool_output or "")
    assert result.steps[1].tool_output == "12.0" or result.steps[1].tool_output == "12"
    assert result.answer == "El resultado es 12."
