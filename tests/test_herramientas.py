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
# ---------------------------------------------------------------------------

def test_leer_archivo_existente(tmp_path) -> None:
    """Lee y devuelve el contenido exacto de un archivo de texto UTF-8."""
    archivo = tmp_path / "saludo.txt"
    contenido = "hola\nmundo áéí"  # incluye acentos para validar UTF-8
    archivo.write_text(contenido, encoding="utf-8")

    assert leer_archivo(str(archivo)) == contenido


def test_leer_archivo_inexistente(tmp_path) -> None:
    """Una ruta que no existe devuelve un error, no lanza excepción."""
    resultado = leer_archivo(str(tmp_path / "no_existe.txt"))
    assert resultado.startswith("Error:")
    assert "no existe" in resultado


def test_leer_archivo_directorio(tmp_path) -> None:
    """Si la ruta es un directorio (no un archivo), devuelve error."""
    resultado = leer_archivo(str(tmp_path))
    assert resultado.startswith("Error:")
    assert "no es un archivo" in resultado


def test_leer_archivo_binario(tmp_path) -> None:
    """Un archivo binario (no UTF-8) devuelve error en vez de romper."""
    archivo = tmp_path / "datos.bin"
    archivo.write_bytes(b"\xff\xfe\x00\x01binario")  # bytes no decodificables

    resultado = leer_archivo(str(archivo))
    assert resultado.startswith("Error:")
    assert "UTF-8" in resultado


def test_leer_archivo_demasiado_grande(tmp_path) -> None:
    """Un archivo que supera el tope (100 KB) devuelve error y no se carga."""
    archivo = tmp_path / "grande.txt"
    archivo.write_text("x" * 200_000, encoding="utf-8")  # > 100 KB

    resultado = leer_archivo(str(archivo))
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
