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

    Los parametros operando_a y operando_b deben ser pasados como float (no string)
    """
    # --- Errores recuperables (M2): mensajes accionables para que el LLM
    # pueda corregir los argumentos y reintentar. -------------------------

    # 1) Operandos no numéricos: indicamos QUÉ parámetro falló, QUÉ valor
    #    llegó y CÓMO debe verse uno válido. Si llega un string que
    #    representa un número ("42", "2.5") lo convertimos en lugar de
    #    fallar: es un error de formato trivial que no amerita otra vuelta.
    operandos: dict[str, float] = {}
    for nombre, valor in (("operando_a", operando_a), ("operando_b", operando_b)):
        if isinstance(valor, bool) or not isinstance(valor, (int, float, str)):
            return (
                f"Error: el parámetro '{nombre}' recibió {valor!r} "
                f"(tipo {type(valor).__name__}), que no es numérico. "
                "Enviá un número, por ejemplo 3 o 2.5."
            )
        if isinstance(valor, str):
            # String numérico ("42", "2.5"): lo convertimos en vez de fallar.
            try:
                valor = float(valor)
            except ValueError:
                return (
                    f"Error: el parámetro '{nombre}' recibió {valor!r}, que no "
                    "se puede interpretar como número. Enviá un valor numérico, "
                    "por ejemplo 3 o 2.5 (sin unidades ni texto adicional)."
                )
        operandos[nombre] = valor
    operando_a = operandos["operando_a"]
    operando_b = operandos["operando_b"]

    # 2) Operador no soportado: listamos los permitidos.
    if operador not in _OPERACIONES:
        soportados = ", ".join(_OPERACIONES.keys())
        return (
            f"Error: operador no soportado '{operador}'. "
            f"Usá exactamente uno de estos símbolos: {soportados}."
        )

    # 3) División y módulo por cero: explicamos la restricción concreta.
    if operador in _DIVIDEN_POR_CERO and operando_b == 0:
        nombre = "división" if operador == "/" else "módulo"
        return (
            f"Error: la {nombre} no está definida cuando el segundo operando "
            f"es 0 ('operando_b' recibió 0). Reintenta con un 'operando_b' "
            "distinto de cero, o revisá si la operación pedida es otra."
        )

    # Aplicamos la operación elegida y devolvemos el resultado como string,
    # tal como exige el contrato (la salida de toda herramienta es ``str``).
    resultado = _OPERACIONES[operador](operando_a, operando_b)
    return str(resultado)


calculadora_schema = ToolSchema.from_callable(calculadora)
