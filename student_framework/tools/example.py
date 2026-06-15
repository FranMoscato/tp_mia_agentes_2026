"""Herramienta de ejemplo que ilustra el patrón de register_tool.

Este archivo es solo ilustrativo — NO cuenta como una de sus tres
herramientas obligatorias del M1 (calculadora, lector de archivos,
herramienta libre). Pueden borrarlo cuando las tres estén listas.

El patrón:
  1. Escribe un callable con tipos en la firma y un docstring (va entero
     a la descripción de la herramienta para el LLM).
  2. `ToolSchema.from_callable(callable)` genera el JSON Schema.
  3. Registra: `agent.register_tool(callable, schema)`.

Para descripciones por parámetro usá `Annotated[..., Field(description="...")]`.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from mia_agents.types import ToolSchema


def reverse_string(
    text: Annotated[str, Field(description="El texto a invertir.")],
) -> str:
    """Invierte la cadena indicada y devuelve el resultado."""
    return text[::-1]


reverse_string_schema = ToolSchema.from_callable(reverse_string)
