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

# Sandbox (M2): todas las rutas son RELATIVAS a este directorio raíz. Por
# defecto es el directorio de trabajo del proceso; los tests (o el runner)
# pueden cambiarlo con `set_sandbox_root(...)`.
_sandbox_root: Path = Path.cwd()


def set_sandbox_root(root: str | Path) -> None:
    """Fija el directorio raíz del sandbox del lector de archivos."""
    global _sandbox_root
    _sandbox_root = Path(root).resolve()


def get_sandbox_root() -> Path:
    """Devuelve el directorio raíz actual del sandbox."""
    return _sandbox_root


def _listar(directorio: Path) -> str:
    """Lista los nombres dentro de `directorio` (para mensajes accionables)."""
    try:
        nombres = sorted(
            p.name + ("/" if p.is_dir() else "") for p in directorio.iterdir()
        )
    except OSError:
        return "(no se pudo listar el directorio)"
    if not nombres:
        return "(directorio vacío)"
    return ", ".join(nombres)


def leer_archivo(
    ruta: Annotated[
        str,
        Field(
            description=(
                "Ruta RELATIVA (dentro del sandbox) al archivo de texto que "
                "se desea leer. No se aceptan rutas absolutas ni '..'."
            )
        ),
    ],
) -> str:
    """Lee un archivo de texto (UTF-8) y devuelve su contenido como string.

    Usá esta herramienta cuando necesites ver el contenido de un archivo de
    texto. La ruta debe ser RELATIVA al directorio de trabajo (sandbox), por
    ejemplo 'notas.txt' o 'datos/informe.txt'. Si el archivo no existe, no es
    un archivo de texto o no se puede leer, devuelve un mensaje de error
    descriptivo (no lanza excepción).
    """
    raiz = _sandbox_root

    # --- Validación de la ruta (M2): errores recuperables con mensajes
    # accionables que explican la regla violada. -------------------------

    # 1) Ruta vacía o solo espacios.
    if not ruta or not ruta.strip():
        return (
            "Error: la ruta está vacía. Enviá una ruta relativa al archivo, "
            "por ejemplo 'notas.txt' o 'datos/informe.txt'."
        )
    ruta = ruta.strip()

    # 2) Ruta absoluta: fuera de contrato — solo rutas relativas al sandbox.
    if Path(ruta).is_absolute():
        return (
            f"Error: la ruta '{ruta}' es absoluta y no está permitida. "
            "Usá una ruta relativa al directorio de trabajo, "
            "por ejemplo 'notas.txt' o 'datos/informe.txt'."
        )

    # 3) Componentes '..': prohibidos porque permiten escapar del sandbox.
    if ".." in Path(ruta).parts:
        return (
            f"Error: la ruta '{ruta}' contiene '..', que no está permitido "
            "porque permite salir del directorio de trabajo. Usá una ruta "
            "relativa sin '..', por ejemplo 'datos/informe.txt'."
        )

    # 4) Resolución final: si aun así la ruta escapa del sandbox (p. ej. vía
    #    un symlink), la rechazamos.
    archivo = (raiz / ruta).resolve()
    raiz_resuelta = raiz.resolve()
    if raiz_resuelta != archivo and raiz_resuelta not in archivo.parents:
        return (
            f"Error: la ruta '{ruta}' apunta fuera del directorio de trabajo "
            "permitido. Solo se pueden leer archivos dentro del sandbox."
        )

    # 5) El archivo debe existir. Si no existe pero su directorio contenedor
    #    sí, listamos los archivos disponibles para que el LLM elija bien.
    if not archivo.exists():
        contenedor = archivo.parent
        if contenedor.is_dir():
            return (
                f"Error: el archivo '{ruta}' no existe. Archivos disponibles "
                f"en '{contenedor.relative_to(raiz_resuelta) if contenedor != raiz_resuelta else '.'}': "
                f"{_listar(contenedor)}. Elegí uno de esos nombres."
            )
        return (
            f"Error: el archivo '{ruta}' no existe (tampoco existe su "
            "directorio contenedor). Verificá la ruta completa."
        )

    # 6) La ruta debe apuntar a un archivo, no a un directorio.
    if not archivo.is_file():
        return (
            f"Error: la ruta '{ruta}' es un directorio, no un archivo. "
            f"Contiene: {_listar(archivo)}. Indicá la ruta de uno de esos "
            "archivos."
        )

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
