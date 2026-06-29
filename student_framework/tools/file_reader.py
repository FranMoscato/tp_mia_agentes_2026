"""Herramienta obligatoria 2 (M1): lector de archivos.

Contrato del enunciado (ENUNCIADO_M1.md, sección "2. Lector de archivos"):

  - Entrada: una ruta a un archivo.
  - Comportamiento: leer y mostrar el contenido del archivo (solo archivos de
    texto; codificación UTF-8 recomendada).

Es una herramienta de E/S restringida: ante cualquier problema (archivo
inexistente, ruta que es un directorio, contenido binario no decodificable,
permisos) devuelve un mensaje de error como texto en lugar de lanzar una
excepción. Así el bucle del agente nunca se rompe por culpa de la herramienta.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field

from mia_agents.types import ToolSchema

# Tope de tamaño para evitar volcar un archivo enorme al contexto del LLM.
# 100 KB es más que suficiente para los archivos de texto de las pruebas.
_MAX_BYTES = 100_000


def leer_archivo(
    ruta: Annotated[
        str,
        Field(description="Ruta al archivo de texto que se desea leer."),
    ],
) -> str:
    """Lee un archivo de texto (UTF-8) y devuelve su contenido como string.

    Usá esta herramienta cuando necesites ver el contenido de un archivo de
    texto cuya ruta conocés. Solo funciona con archivos de texto. Si el archivo
    no existe, no es un archivo de texto o no se puede leer, devuelve un mensaje
    de error descriptivo (no lanza excepción).
    """
    # Normalizamos la ruta a un objeto Path para usar sus comprobaciones.
    archivo = Path(ruta)

    # 1) El archivo debe existir.
    if not archivo.exists():
        return f"Error: el archivo '{ruta}' no existe."

    # 2) La ruta debe apuntar a un archivo, no a un directorio.
    if not archivo.is_file():
        return f"Error: la ruta '{ruta}' no es un archivo."

    # 3) Evitamos cargar archivos demasiado grandes en memoria/contexto.
    try:
        tamano = archivo.stat().st_size
    except OSError as exc:  # p. ej. problemas de permisos al hacer stat
        return f"Error: no se pudo acceder a '{ruta}': {exc}."
    if tamano > _MAX_BYTES:
        return (
            f"Error: el archivo '{ruta}' es demasiado grande "
            f"({tamano} bytes; máximo {_MAX_BYTES})."
        )

    # 4) Lectura como texto UTF-8. Capturamos por separado:
    #    - UnicodeDecodeError: el archivo no es texto UTF-8 (probablemente binario).
    #    - OSError: errores de E/S genéricos (permisos, etc.).
    try:
        return archivo.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return f"Error: '{ruta}' no es un archivo de texto UTF-8 válido."
    except OSError as exc:
        return f"Error: no se pudo leer '{ruta}': {exc}."


# Esquema derivado automáticamente de la firma + docstring.
leer_archivo_schema = ToolSchema.from_callable(leer_archivo)
