"""Herramienta obligatoria 1 (M1): calculadora simple.

Contrato del enunciado (sección "1. Calculadora simple"):

  - Entrada: dos operandos numéricos y un operador (string).
  - Operadores soportados: ``+``, ``-``, ``*``, ``/`` (división) y ``%`` (módulo).
    Se soportan los cinco para cubrir las dos versiones del enunciado (una pide
    ``/`` y otra ``%``); ambos son operaciones binarias simples.
  - Salida: el resultado de la operación, como ``str``.
  - Sin ``eval`` y sin expresiones arbitrarias: solo la operación binaria
    indicada.

Por eso esta implementación NO parsea expresiones (la versión anterior usaba
``ast.parse``, que justamente permite expresiones arbitrarias). En cambio,
recibe los dos operandos y el operador por separado y aplica únicamente la
operación binaria pedida.
"""

from __future__ import annotations

# ``Annotated`` permite adjuntar metadatos (el ``Field`` de Pydantic) a cada
# parámetro de la firma. ``ToolSchema.from_callable`` lee esos metadatos para
# construir el JSON Schema que se le ofrece al LLM.
from typing import Annotated

from pydantic import Field

from mia_agents.types import ToolSchema

# Tabla de operadores soportados. Cada clave es el símbolo que el LLM debe
# enviar en el argumento ``operador`` y el valor es una función pura de dos
# argumentos que aplica la operación. Mantener la lógica en un diccionario hace
# trivial validar el operador (basta con comprobar la pertenencia a las claves)
# y evita cadenas largas de ``if/elif``.
_OPERACIONES = {
    "+": lambda a, b: a + b,  # suma
    "-": lambda a, b: a - b,  # resta
    "*": lambda a, b: a * b,  # multiplicación
    "/": lambda a, b: a / b,  # división
    "%": lambda a, b: a % b,  # módulo (resto de la división entera)
}

# Operadores cuya operación no está definida cuando el segundo operando es 0
# (división y módulo). Se interceptan antes de aplicar la operación.
_DIVIDEN_POR_CERO = {"/", "%"}


def calculadora(
    operando_a: Annotated[
        float,
        Field(description="Primer operando numérico de la operación."),
    ],
    operando_b: Annotated[
        float,
        Field(description="Segundo operando numérico de la operación."),
    ],
    operador: Annotated[
        str,
        Field(description="Operador a aplicar. Uno de: '+', '-', '*', '/', '%'."),
    ],
) -> str:
    """Calcula una operación aritmética binaria entre dos números.

    Usá esta herramienta cuando necesites resolver una cuenta simple entre dos
    números: suma ('+'), resta ('-'), multiplicación ('*'), división ('/') o
    módulo ('%'). Devuelve el resultado como texto. No evalúa expresiones
    completas: solo la operación binaria indicada por ``operador``.
    """
    # Validación defensiva del operador: si el LLM alucina un símbolo que no
    # soportamos (p. ej. '/' o '^'), devolvemos un mensaje de error en vez de
    # lanzar una excepción. Así la herramienta nunca rompe el bucle del agente.
    if operador not in _OPERACIONES:
        soportados = ", ".join(_OPERACIONES.keys())
        return f"Error: operador no soportado '{operador}'. Use uno de: {soportados}."

    # La división y el módulo por cero no están definidos; los interceptamos
    # para devolver un error claro en lugar de propagar ``ZeroDivisionError``.
    if operador in _DIVIDEN_POR_CERO and operando_b == 0:
        nombre = "división" if operador == "/" else "módulo"
        return f"Error: {nombre} por cero."

    # Aplicamos la operación elegida y devolvemos el resultado como string,
    # tal como exige el contrato (la salida de toda herramienta es ``str``).
    resultado = _OPERACIONES[operador](operando_a, operando_b)
    return str(resultado)


# El esquema se deriva automáticamente de la firma + docstring de la función.
# Nunca se escribe el JSON Schema a mano (lo exige el enunciado). El nombre del
# esquema queda como "calculadora" (el nombre de la función), que es claro para
# el LLM.
calculadora_schema = ToolSchema.from_callable(calculadora)
