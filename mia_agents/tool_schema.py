"""Generación de `ToolSchema` desde callables (`Annotated` + Pydantic).

El agente registra `ToolSchema.from_callable(fn)` y en cada `chat` pasa
los `ToolSchema` al `LLMClient`; `_format_tools` aplica `to_llm_spec()`.
"""

from __future__ import annotations

import inspect
import re
from typing import Any, get_type_hints

from pydantic import BaseModel, Field, create_model

from mia_agents.types import ToolSchema

# Nombre fijo de la herramienta sintética de cierre en `structured_call` (M2).
FINAL_RESULT_TOOL_NAME = "final_result"


def _tool_description_from_docstring(doc: str | None) -> str:
    """Docstring completo (cleandoc): una sola fuente de verdad para el LLM."""
    if not doc:
        return ""
    return inspect.cleandoc(doc).strip()


def _input_model_from_callable(fn: Any) -> type[BaseModel]:
    """Construye un modelo Pydantic a partir de la firma del callable."""
    hints = get_type_hints(fn, include_extras=True)
    sig = inspect.signature(fn)
    fields: dict[str, Any] = {}

    for pname, param in sig.parameters.items():
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            raise TypeError(
                f"{fn.__name__} no puede usar *args ni **kwargs en herramientas."
            )
        annotation = hints.get(pname, str)
        if param.default is inspect.Parameter.empty:
            fields[pname] = (annotation, Field())
        else:
            fields[pname] = (annotation, Field(default=param.default))

    safe_name = re.sub(r"[^a-zA-Z0-9_]", "_", fn.__name__).strip("_") or "Tool"
    if not fields:
        return create_model(f"{safe_name}_Input")
    return create_model(f"{safe_name}_Input", **fields)


def parameters_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """JSON Schema de entrada listo para `ToolSchema.parameters`."""
    schema = model.model_json_schema()
    schema.pop("$schema", None)
    return schema


def tool_schema_from_callable(
    fn: Any,
    *,
    name: str | None = None,
    description: str | None = None,
) -> ToolSchema:
    """Arma un `ToolSchema` a partir de anotaciones y docstring del callable.

    Convenciones:
      - Tipos en la firma (`str`, `int`, ...) → tipos JSON.
      - `Annotated[..., Field(description="...")]` → descripción por parámetro.
      - Docstring completo → descripción de la herramienta.
      - `name` por defecto: `fn.__name__`.
    """
    model = _input_model_from_callable(fn)
    tool_description = (
        description
        if description is not None
        else _tool_description_from_docstring(inspect.getdoc(fn))
    )
    if not tool_description:
        tool_description = f"Herramienta {fn.__name__}."

    return ToolSchema(
        name=name or fn.__name__,
        description=tool_description,
        parameters=parameters_json_schema(model),
    )


def tool_schema_from_model(
    model: type[BaseModel],
    *,
    name: str,
    description: str,
) -> ToolSchema:
    """Arma un `ToolSchema` desde un `BaseModel` ya definido (M2+)."""
    return ToolSchema(
        name=name,
        description=description,
        parameters=parameters_json_schema(model),
    )


def final_result_tool_schema(schema: type[BaseModel]) -> ToolSchema:
    """Esquema de la tool sintética obligatoria para cerrar `structured_call`."""
    return tool_schema_from_model(
        schema,
        name=FINAL_RESULT_TOOL_NAME,
        description=(
            "Devuelve la respuesta final estructurada. Debes invocar esta "
            "herramienta (y solo esta) para terminar; no respondas con texto libre."
        ),
    )
