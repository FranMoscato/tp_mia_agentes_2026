"""Tests unitarios de las tres herramientas obligatorias del M1.

A diferencia de `tests/test_escenarios_propios.py` (que prueba el BUCLE del
agente encadenando herramientas), acá probamos cada herramienta de forma
AISLADA, llamándola directamente. El foco está en las ramas de error y los
casos borde, que en los escenarios casi no se ejercitan:

  - Calculadora: cada operador, división/módulo por cero, operador inválido.
  - Lector de archivos: inexistente, directorio, binario, demasiado grande.
  - Contador de palabras: vacío, solo espacios, saltos de línea.

Todas las herramientas devuelven SIEMPRE un string y nunca lanzan excepción:
los errores de dominio se devuelven como texto que empieza con "Error:".
"""

from __future__ import annotations

import pytest

from student_framework.tools.calculator import calculadora
from student_framework.tools.file_reader import leer_archivo
from student_framework.tools.word_counter import contar_palabras


# ---------------------------------------------------------------------------
# Calculadora
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "a, b, op, esperado",
    [
        (7, 5, "+", "12"),
        (7, 5, "-", "2"),
        (7, 5, "*", "35"),
        (10, 4, "/", "2.5"),
        (12, 5, "%", "2"),
        (-3, 8, "+", "5"),       # operandos negativos
        (2.5, 0.5, "*", "1.25"),  # operandos float
    ],
)
def test_calculadora_operaciones_validas(a, b, op, esperado) -> None:
    """Cada operador soportado devuelve el resultado correcto como string."""
    assert calculadora(a, b, op) == esperado


def test_calculadora_division_por_cero() -> None:
    """Dividir por cero devuelve un error legible, no lanza ZeroDivisionError."""
    resultado = calculadora(10, 0, "/")
    assert resultado.startswith("Error:")
    assert "cero" in resultado


def test_calculadora_modulo_por_cero() -> None:
    """Módulo por cero devuelve un error legible, no lanza excepción."""
    resultado = calculadora(5, 0, "%")
    assert resultado.startswith("Error:")
    assert "cero" in resultado


def test_calculadora_operador_invalido() -> None:
    """Un operador no soportado devuelve un error sin romperse."""
    resultado = calculadora(2, 3, "^")
    assert resultado.startswith("Error:")
    assert "^" in resultado


def test_calculadora_siempre_devuelve_string() -> None:
    """El contrato exige que la salida sea siempre str."""
    assert isinstance(calculadora(1, 1, "+"), str)
    assert isinstance(calculadora(1, 0, "/"), str)  # incluso en el caso de error


# ---------------------------------------------------------------------------
# Lector de archivos
#
# Desde M2 el lector opera dentro de un SANDBOX: las rutas son relativas a un
# directorio raíz configurable. El fixture `sandbox` apunta esa raíz a
# `tmp_path` y la restaura al terminar cada test.
# ---------------------------------------------------------------------------

from student_framework.tools.file_reader import get_sandbox_root, set_sandbox_root


@pytest.fixture()
def sandbox(tmp_path):
    """Fija el sandbox del lector en `tmp_path` y lo restaura al salir."""
    anterior = get_sandbox_root()
    set_sandbox_root(tmp_path)
    yield tmp_path
    set_sandbox_root(anterior)


def test_leer_archivo_existente(sandbox) -> None:
    """Lee y devuelve el contenido exacto de un archivo de texto UTF-8."""
    contenido = "hola\nmundo áéí"  # incluye acentos para validar UTF-8
    (sandbox / "saludo.txt").write_text(contenido, encoding="utf-8")

    assert leer_archivo("saludo.txt") == contenido


def test_leer_archivo_inexistente_lista_disponibles(sandbox) -> None:
    """Una ruta que no existe devuelve error y lista los archivos del directorio."""
    (sandbox / "notas.txt").write_text("hola", encoding="utf-8")

    resultado = leer_archivo("no_existe.txt")
    assert resultado.startswith("Error:")
    assert "no existe" in resultado
    assert "notas.txt" in resultado  # M2: mensaje accionable con alternativas


def test_leer_archivo_directorio_lista_contenido(sandbox) -> None:
    """Si la ruta es un directorio, lo dice y lista su contenido."""
    subdir = sandbox / "datos"
    subdir.mkdir()
    (subdir / "informe.txt").write_text("x", encoding="utf-8")

    resultado = leer_archivo("datos")
    assert resultado.startswith("Error:")
    assert "directorio" in resultado
    assert "informe.txt" in resultado  # M2: mensaje accionable con contenido


def test_leer_archivo_ruta_vacia(sandbox) -> None:
    """Una ruta vacía explica la regla y muestra un ejemplo válido."""
    resultado = leer_archivo("")
    assert resultado.startswith("Error:")
    assert "vacía" in resultado


def test_leer_archivo_ruta_absoluta(sandbox) -> None:
    """Las rutas absolutas están prohibidas por el sandbox."""
    resultado = leer_archivo(str(sandbox / "algo.txt"))
    assert resultado.startswith("Error:")
    assert "absoluta" in resultado


def test_leer_archivo_ruta_con_punto_punto(sandbox) -> None:
    """Las rutas con '..' están prohibidas porque escapan del sandbox."""
    resultado = leer_archivo("../fuera.txt")
    assert resultado.startswith("Error:")
    assert ".." in resultado


def test_leer_archivo_binario(sandbox) -> None:
    """Un archivo binario (no UTF-8) devuelve error en vez de romper."""
    (sandbox / "datos.bin").write_bytes(b"\xff\xfe\x00\x01binario")

    resultado = leer_archivo("datos.bin")
    assert resultado.startswith("Error:")
    assert "UTF-8" in resultado


def test_leer_archivo_demasiado_grande(sandbox) -> None:
    """Un archivo que supera el tope (100 KB) devuelve error y no se carga."""
    (sandbox / "grande.txt").write_text("x" * 200_000, encoding="utf-8")

    resultado = leer_archivo("grande.txt")
    assert resultado.startswith("Error:")
    assert "grande" in resultado


# ---------------------------------------------------------------------------
# Contador de palabras
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("hola mundo esto es prueba", "5"),
        ("una", "1"),
        ("", "0"),                       # cadena vacía -> 0 palabras
        ("   ", "0"),                    # solo espacios -> 0 palabras
        ("hola    mundo", "2"),          # espacios múltiples colapsan
        ("linea1\nlinea2\tlinea3", "3"),  # saltos de línea y tabs separan
    ],
)
def test_contar_palabras(texto, esperado) -> None:
    """Cuenta correctamente, tratando cualquier espacio en blanco como separador."""
    assert contar_palabras(texto) == esperado


def test_contar_palabras_devuelve_string() -> None:
    """El contrato exige que la salida sea siempre str."""
    assert isinstance(contar_palabras("hola mundo"), str)
