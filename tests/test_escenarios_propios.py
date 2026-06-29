"""Escenarios de prueba propios del grupo (entregable adicional del M1).

El enunciado / README piden "escenarios de prueba propios donde el agente use
al menos dos herramientas". Estos tests NO son los de conformidad de la cátedra
(esos viven en `tests/conformance/` y son fijos): son nuestros, para demostrar
que el bucle del agente encadena varias herramientas y maneja errores.

Usan el `MockLLMClient` de la cátedra, que devuelve respuestas prefabricadas en
orden. Así guionamos exactamente qué "decide" el LLM en cada turno y los tests
son deterministas y no consumen créditos de API.

Patrón de cada escenario:
  1. Programamos la secuencia de `LLMResponse` que el mock irá devolviendo
     (primero pide herramientas con `tool_calls`, al final responde con texto).
  2. Construimos el agente con ese mock vía `build_agent`.
  3. Ejecutamos `run(...)` y verificamos `answer` y los `steps`.
"""

from __future__ import annotations

import json

from mia_agents.testing import MockLLMClient
from mia_agents.types import LLMResponse, ToolCall

from student_framework import build_agent


def _tool_call(call_id: str, nombre: str, **argumentos: object) -> ToolCall:
    """Helper: arma un `ToolCall` serializando los argumentos a JSON.

    El campo `arguments` de un `ToolCall` es siempre un string JSON (así lo
    define `mia_agents.types.ToolCall`), tal como lo emitiría un LLM real.
    """
    return ToolCall(id=call_id, name=nombre, arguments=json.dumps(argumentos))


def test_escenario_leer_archivo_y_contar_palabras(tmp_path) -> None:
    """Dos herramientas encadenadas: leer un archivo y contar sus palabras.

    Simula: "Leé este archivo y decime cuántas palabras tiene." El LLM:
      Turno 1 -> usa `leer_archivo` con la ruta.
      Turno 2 -> con el contenido leído, usa `contar_palabras`.
      Turno 3 -> responde en texto con el total.
    """
    # Creamos un archivo de texto temporal con 5 palabras conocidas.
    archivo = tmp_path / "nota.txt"
    archivo.write_text("hola mundo esto es prueba", encoding="utf-8")

    mock = MockLLMClient(
        [
            # Turno 1: el LLM pide leer el archivo.
            LLMResponse(
                content=None,
                tool_calls=[_tool_call("c1", "leer_archivo", ruta=str(archivo))],
            ),
            # Turno 2: el LLM pide contar las palabras del contenido leído.
            LLMResponse(
                content=None,
                tool_calls=[
                    _tool_call("c2", "contar_palabras", texto="hola mundo esto es prueba")
                ],
            ),
            # Turno 3: respuesta final en texto (sin tool_calls -> corta el bucle).
            LLMResponse(content="El archivo tiene 5 palabras."),
        ]
    )

    agent = build_agent({"llm_client": mock})
    result = agent.run("¿Cuántas palabras tiene nota.txt?")

    # Se usaron exactamente dos herramientas, en orden.
    assert [s.tool_name for s in result.steps] == ["leer_archivo", "contar_palabras"]
    # La primera devolvió el contenido del archivo; la segunda, el conteo "5".
    assert result.steps[0].tool_output == "hola mundo esto es prueba"
    assert result.steps[1].tool_output == "5"
    # Ningún paso falló.
    assert all(s.error is None for s in result.steps)
    # La respuesta final es el texto del último turno.
    assert result.answer == "El archivo tiene 5 palabras."
    # Hubo 3 llamadas al LLM (2 con tool_calls + 1 final).
    assert mock.call_count == 3


def test_escenario_calculadora_y_conteo() -> None:
    """Dos herramientas distintas en una misma conversación: cálculo y conteo."""
    mock = MockLLMClient(
        [
            # Turno 1: calcular 12 % 5 (módulo) -> 2.
            LLMResponse(
                content=None,
                tool_calls=[
                    _tool_call("c1", "calculadora", operando_a=12, operando_b=5, operador="%")
                ],
            ),
            # Turno 2: contar palabras de una frase -> 3.
            LLMResponse(
                content=None,
                tool_calls=[_tool_call("c2", "contar_palabras", texto="uno dos tres")],
            ),
            # Turno 3: respuesta final.
            LLMResponse(content="El resto es 2 y la frase tiene 3 palabras."),
        ]
    )

    agent = build_agent({"llm_client": mock})
    result = agent.run("Calculá 12 % 5 y contá las palabras de 'uno dos tres'.")

    assert [s.tool_name for s in result.steps] == ["calculadora", "contar_palabras"]
    assert result.steps[0].tool_output == "2"   # 12 % 5
    assert result.steps[1].tool_output == "3"   # tres palabras
    assert result.answer == "El resto es 2 y la frase tiene 3 palabras."


def test_escenario_calculadora_division() -> None:
    """La calculadora soporta división ('/') además de módulo ('%')."""
    mock = MockLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=[
                    _tool_call("c1", "calculadora", operando_a=10, operando_b=4, operador="/")
                ],
            ),
            LLMResponse(content="10 / 4 = 2.5."),
        ]
    )

    agent = build_agent({"llm_client": mock})
    result = agent.run("¿Cuánto es 10 dividido 4?")

    assert result.steps[0].tool_name == "calculadora"
    assert result.steps[0].tool_output == "2.5"   # 10 / 4
    assert result.steps[0].error is None
    assert result.answer == "10 / 4 = 2.5."


def test_escenario_recuperacion_ante_tool_desconocida() -> None:
    """Robustez: el LLM alucina una herramienta inexistente y luego se recupera.

    El agente no debe romperse: registra el fallo como un `AgentStep` con
    `error` no nulo, le devuelve el error al LLM y sigue hasta una respuesta
    final usando una herramienta válida.
    """
    mock = MockLLMClient(
        [
            # Turno 1: el LLM inventa una herramienta que no existe.
            LLMResponse(
                content=None,
                tool_calls=[_tool_call("c1", "herramienta_magica", x=1)],
            ),
            # Turno 2: ya con el error en contexto, usa una herramienta real.
            LLMResponse(
                content=None,
                tool_calls=[
                    _tool_call("c2", "calculadora", operando_a=2, operando_b=2, operador="+")
                ],
            ),
            # Turno 3: respuesta final.
            LLMResponse(content="Listo, 2 + 2 = 4."),
        ]
    )

    agent = build_agent({"llm_client": mock})
    result = agent.run("Hacé algo y después sumá 2 + 2.")

    # Dos pasos: el fallido (tool desconocida) y el exitoso (calculadora).
    assert len(result.steps) == 2
    assert result.steps[0].error is not None        # quedó registrado el fallo
    assert result.steps[0].tool_output is None
    assert result.steps[1].error is None            # el segundo sí funcionó
    assert result.steps[1].tool_output == "4"
    assert result.answer == "Listo, 2 + 2 = 4."


def test_escenario_corte_por_max_iterations() -> None:
    """Terminación: si el LLM nunca deja de pedir herramientas, corta por tope.

    Programamos muchas respuestas con `tool_calls` (un bucle que nunca cierra).
    El agente debe hacer como máximo `max_iterations` llamadas al LLM y aún así
    devolver un `AgentResult` válido (no lanzar excepción).
    """
    # Construimos 30 respuestas que SIEMPRE piden la calculadora (bucle infinito
    # simulado). El agente por defecto trae max_iterations=10.
    respuestas = [
        LLMResponse(
            content=None,
            tool_calls=[
                _tool_call(f"c{i}", "calculadora", operando_a=1, operando_b=1, operador="+")
            ],
        )
        for i in range(30)
    ]
    mock = MockLLMClient(respuestas)

    agent = build_agent({"llm_client": mock})
    result = agent.run("entrá en bucle")

    # No superó el tope de llamadas al LLM (max_iterations=10 por defecto).
    assert mock.call_count == 10
    # Aun cortando por límite, devuelve un AgentResult válido (answer es str).
    assert isinstance(result.answer, str)
