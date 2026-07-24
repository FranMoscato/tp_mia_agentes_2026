"""Herramienta obligatoria 3 (M1): herramienta libre — contador de palabras.

El enunciado (ENUNCIADO_M1.md, sección "3. Herramienta libre") permite
cualquier utilidad que demuestre el mismo patrón (callable tipado +
``ToolSchema.from_callable`` + registro). Elegimos un contador de palabras
porque:

  - Es cómputo puro (sin E/S, sin dependencias externas).
  - Combina naturalmente con el lector de archivos para los escenarios de
    prueba: el agente puede leer un archivo y luego contar sus palabras,
    encadenando dos herramientas.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from mia_agents.types import ToolSchema


def contar_palabras(
    texto: Annotated[
        str,
        Field(description="El texto cuyas palabras se desean contar."),
    ],
) -> str:
    """Cuenta cuántas palabras tiene un texto y devuelve el número como string.

    Usá esta herramienta cuando necesites saber la cantidad de palabras de un
    texto. Una "palabra" es cualquier secuencia de caracteres separada por
    espacios en blanco (espacios, tabulaciones o saltos de línea). El texto
    vacío o de solo espacios cuenta como 0 palabras.

    No utilices esta funcion cuando no se requiera saber el largo de un texto
    """
    # ``str.split()`` sin argumentos divide por cualquier cantidad de espacios
    # en blanco consecutivos y descarta los extremos, así que cadenas vacías o
    # con espacios de más dan la cantidad correcta de palabras (incluido 0).
    cantidad = len(texto.split())
    return str(cantidad)


# Esquema derivado automáticamente de la firma + docstring.
contar_palabras_schema = ToolSchema.from_callable(contar_palabras)
