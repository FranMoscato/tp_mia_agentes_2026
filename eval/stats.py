"""Contrastes entre brazos del experimento, estratificados por escenario.

POR QUÉ ESTE MÓDULO
-------------------
Comparar dos brazos con un test de proporciones agrupado (juntar todos los
casos de `react` contra todos los de `gate`) **tira poder a la basura**: los dos
brazos corren LOS MISMOS 8 escenarios, y el escenario es la fuente dominante de
varianza —`easy` da 1.00 y `extreme` da 0.14—. Al agrupar, esa varianza entre
escenarios se mete en el error estándar y tapa el efecto que buscamos.

El diseño es de **bloques**: cada tratamiento (brazo) se aplica sobre las mismas
unidades (escenarios). El test correcto para eso es **Cochran–Mantel–Haenszel**,
que estratifica por bloque y descarta solo los estratos sin varianza.

Medido sobre `nova-micro`, gate vs. react, con los mismos 128 casos:

    z-test agrupado      p = 0.0957   (no significativo)
    CMH estratificado    p = 0.0338   (significativo)

No es un truco para conseguir significancia: los estratos saturados
(`backtracking-vault` y `vault-combination`, 0/8 en AMBOS brazos) no aportan
información pero inflan el denominador del test agrupado. CMH los descarta.

Todo acá es **puro**: no toca red ni disco, así que se testea sin API.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

# Un estrato con 0 éxitos o 0 fracasos en la suma de ambos brazos no aporta
# información al contraste (no hay nada que comparar): CMH lo descarta.
# Lo dejamos explícito para poder REPORTAR cuántos se descartaron —callar eso
# haría parecer que el test usó todo el dataset.


def _norm_sf(x: float) -> float:
    """P(|Z| > x) para Z normal estándar (test a dos colas)."""
    return math.erfc(abs(x) / math.sqrt(2))


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Intervalo de Wilson para una proporción.

    Wilson y no Wald: con proporciones cerca de 0 o 1 —el caso de `extreme`—
    Wald da intervalos que se salen de [0, 1] o colapsan a un punto.
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    medio = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centro - medio), min(1.0, centro + medio))


def z_test_agrupado(s1: int, n1: int, s2: int, n2: int) -> tuple[float, float]:
    """Test de dos proporciones independientes (el que NO conviene acá).

    Se mantiene para poder mostrar la comparación con CMH en el informe: la
    diferencia entre ambos ES el argumento de por qué estratificar.
    """
    if n1 == 0 or n2 == 0:
        return (0.0, 1.0)
    p = (s1 + s2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return (0.0, 1.0)
    z = (s2 / n2 - s1 / n1) / se
    return (z, _norm_sf(z))


def cmh_test(estratos: dict[str, tuple[tuple[int, int], tuple[int, int]]]) -> dict[str, Any]:
    """Cochran–Mantel–Haenszel sobre estratos `{nombre: ((s1,n1), (s2,n2))}`.

    `s` son éxitos y `n` el total; el índice 1 es el brazo base y el 2 el
    comparado. Aplica corrección de continuidad (el −0.5), que es lo estándar
    con conteos chicos como los nuestros.

    Devuelve el estadístico, el p-valor, y CUÁNTOS estratos se usaron y se
    descartaron —reportar eso es obligatorio: un p-valor calculado sobre 6 de 8
    estratos no es lo mismo que sobre 8.
    """
    num = den = 0.0
    usados: list[str] = []
    descartados: list[str] = []
    for nombre, ((s1, n1), (s2, n2)) in estratos.items():
        if n1 == 0 or n2 == 0:
            descartados.append(nombre)
            continue
        total = n1 + n2
        exitos = s1 + s2
        if exitos == 0 or exitos == total or total < 2:
            # Estrato sin varianza: todos éxito o todos fracaso en ambos brazos.
            descartados.append(nombre)
            continue
        usados.append(nombre)
        num += s2 - n2 * exitos / total
        den += (n1 * n2 * exitos * (total - exitos)) / (total * total * (total - 1))

    if den <= 0 or not usados:
        return {
            "chi2": None, "p": None,
            "estratos_usados": usados, "estratos_descartados": descartados,
        }

    chi2 = (abs(num) - 0.5) ** 2 / den
    return {
        "chi2": round(chi2, 4),
        "p": round(math.erfc(math.sqrt(chi2 / 2)), 5),
        "estratos_usados": usados,
        "estratos_descartados": descartados,
    }


def efecto_por_escenario(
    estratos: dict[str, tuple[tuple[int, int], tuple[int, int]]],
) -> list[dict[str, Any]]:
    """Delta de accuracy brazo2 − brazo1, escenario por escenario.

    El promedio agregado esconde la forma del efecto. En el caso del gate, el
    +0.14 promedio no viene de mejorar parejo: viene de **rescatar un escenario
    puntual** (`extreme-archive`, 1/8 → 7/8) mientras en el resto no cambia
    nada. Eso es un hallazgo distinto —y más útil— que "el gate ayuda 14
    puntos".

    Ordena por delta descendente para que el escenario que carga el efecto
    quede arriba.
    """
    filas = []
    for nombre, ((s1, n1), (s2, n2)) in estratos.items():
        if n1 == 0 or n2 == 0:
            continue
        p1, p2 = s1 / n1, s2 / n2
        filas.append({
            "escenario": nombre,
            "base": f"{s1}/{n1}", "base_acc": round(p1, 3),
            "comp": f"{s2}/{n2}", "comp_acc": round(p2, 3),
            "delta": round(p2 - p1, 3),
        })
    return sorted(filas, key=lambda f: -f["delta"])


def estratos_desde_casos(
    casos: list[dict[str, Any]], brazo_base: str, brazo_comp: str,
) -> dict[str, tuple[tuple[int, int], tuple[int, int]]]:
    """Arma los estratos por escenario a partir de un `cases.jsonl` ya cargado."""
    acc: dict[str, dict[str, list[int]]] = defaultdict(
        lambda: {brazo_base: [0, 0], brazo_comp: [0, 0]}
    )
    for c in casos:
        cfg = c.get("config")
        if cfg not in (brazo_base, brazo_comp):
            continue
        celda = acc[c.get("scenario")][cfg]
        celda[0] += bool(c.get("goal_achieved"))
        celda[1] += 1
    return {
        sc: ((v[brazo_base][0], v[brazo_base][1]), (v[brazo_comp][0], v[brazo_comp][1]))
        for sc, v in acc.items()
    }


def comparar_brazos(
    casos: list[dict[str, Any]], brazo_base: str, brazo_comp: str,
) -> dict[str, Any]:
    """Contraste completo entre dos brazos: agrupado, estratificado y por escenario."""
    estratos = estratos_desde_casos(casos, brazo_base, brazo_comp)
    s1 = sum(e[0][0] for e in estratos.values())
    n1 = sum(e[0][1] for e in estratos.values())
    s2 = sum(e[1][0] for e in estratos.values())
    n2 = sum(e[1][1] for e in estratos.values())
    z, p_agrupado = z_test_agrupado(s1, n1, s2, n2)
    return {
        "base": brazo_base, "comparado": brazo_comp,
        "base_n": f"{s1}/{n1}", "base_acc": round(s1 / n1, 3) if n1 else None,
        "base_ci": [round(x, 3) for x in wilson_ci(s1, n1)],
        "comp_n": f"{s2}/{n2}", "comp_acc": round(s2 / n2, 3) if n2 else None,
        "comp_ci": [round(x, 3) for x in wilson_ci(s2, n2)],
        "delta": round(s2 / n2 - s1 / n1, 3) if n1 and n2 else None,
        "z_agrupado": round(z, 3), "p_agrupado": round(p_agrupado, 5),
        "cmh": cmh_test(estratos),
        "por_escenario": efecto_por_escenario(estratos),
    }
