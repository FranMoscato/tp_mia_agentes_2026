"""Diagrama del grafo de estados de un escenario, con el óptimo del BFS resaltado.

No es un gráfico de datos: es un **diagrama conceptual** que muestra qué significa
"óptimo derivado por búsqueda" (§2 del informe). Reusa la misma BFS de
`eval/optimal.py` sobre el mundo real (`make_world_tools`), así que lo que se
dibuja es literalmente el grafo que recorre el cálculo del óptimo.

Elegimos `study-with-key`: es chico (7 estados) pero ramifica, así que se ve el
camino más corto (examine → take → use = 3 acciones) **y** las ramas que la
búsqueda explora y descarta (examinar la alfombra, re-examinar el escritorio).
Esas ramas descartadas son, justamente, la *redundancia evitable* que penaliza
el overhead-vs-óptimo y que puntúa el judge.

Uso:
    python scripts/grafico_grafo_estados_m3.py

Produce `docs/m3_grafo_estados.png`.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from collections import deque
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from mia_world.goals import check_goal
from mia_world.scenarios import load_scenario
from mia_world.tools import make_world_tools

# BFS de eval/optimal.py (eval no es paquete: la cargamos por path).
_spec = importlib.util.spec_from_file_location("opt", _REPO / "eval" / "optimal.py")
_opt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_opt)

# Colores (paleta unificada, fuente única en estilo_diagramas.py): azul para el
# óptimo; gris apagado para lo descartado.
from estilo_diagramas import AZUL as _AZUL, GRIS as _GRIS, TINTA as _TINTA  # noqa: E402

_ESCENARIO = _REPO / "scenarios" / "01-study-with-key.json"
_PROFUNDIDAD = 3  # = óptimo del escenario (cross-validado con el enunciado)


def _accion_label(act: tuple[str, dict[str, str]] | None) -> str:
    if act is None:
        return "inicio\n(manos\nvacías)"
    name, kw = act
    args = ", ".join(kw.values())
    return f"{name}\n{args}"


def _construir_grafo() -> tuple[dict, str]:
    """BFS que guarda, por estado, su padre y la acción que llevó a él."""
    sc = load_scenario(_ESCENARIO)
    goal = sc.goal
    with_events = _opt._goal_uses_sequence(goal)

    start = copy.deepcopy(sc.initial_world)
    k0 = _opt._canonical(start, with_events)
    nodes: dict = {
        k0: {"d": 0, "parent": None, "act": None,
             "goal": check_goal(start, goal)[0]}
    }
    goal_key = k0 if nodes[k0]["goal"] else None
    frontier: deque = deque([(start, 0)])
    while frontier:
        w, d = frontier.popleft()
        if d >= _PROFUNDIDAD:
            continue
        for name, kw in _opt._candidate_actions(w):
            nxt = copy.deepcopy(w)
            tools = {s.name: fn for fn, s in make_world_tools(nxt)}
            fn = tools.get(name)
            if fn is None:
                continue
            try:
                fn(**kw)
            except Exception:  # noqa: BLE001
                continue
            k = _opt._canonical(nxt, with_events)
            if k in nodes:
                continue
            es_goal = check_goal(nxt, goal)[0]
            nodes[k] = {"d": d + 1, "parent": _opt._canonical(w, with_events),
                        "act": (name, kw), "goal": es_goal}
            if es_goal and goal_key is None:
                goal_key = k
            frontier.append((nxt, d + 1))
    return nodes, goal_key


def _camino_optimo(nodes: dict, goal_key: str) -> set:
    """Backtrack por punteros de padre desde el objetivo hasta el inicio."""
    en_camino = set()
    k = goal_key
    while k is not None:
        en_camino.add(k)
        k = nodes[k]["parent"]
    return en_camino


def main() -> None:
    nodes, goal_key = _construir_grafo()
    if goal_key is None:
        raise SystemExit("El escenario no se resolvió dentro de la profundidad dada.")
    en_camino = _camino_optimo(nodes, goal_key)

    # Layout por capas: x = profundidad BFS; on-path en y=0 (línea recta),
    # off-path debajo. Con ≤2 nodos por capa alcanza para que quede legible.
    pos: dict = {}
    por_capa: dict[int, list[str]] = {}
    for k, v in nodes.items():
        por_capa.setdefault(v["d"], []).append(k)
    for d, keys in por_capa.items():
        keys.sort(key=lambda k: 0 if k in en_camino else 1)
        y_off = -1.6
        for k in keys:
            pos[k] = (d, 0.0 if k in en_camino else y_off)
            if k not in en_camino:
                y_off -= 1.6

    fig, ax = plt.subplots(figsize=(9.2, 4.2))

    # Aristas (padre -> hijo) primero, para que los nodos queden encima.
    for k, v in nodes.items():
        if v["parent"] is None:
            continue
        x0, y0 = pos[v["parent"]]
        x1, y1 = pos[k]
        on = k in en_camino and v["parent"] in en_camino
        ax.add_patch(FancyArrowPatch(
            (x0 + 0.28, y0), (x1 - 0.28, y1),
            arrowstyle="-|>", mutation_scale=14,
            color=_AZUL if on else _GRIS,
            lw=2.4 if on else 1.3, zorder=1,
            shrinkA=0, shrinkB=0,
        ))

    # Nodos.
    for k, v in nodes.items():
        x, y = pos[k]
        on = k in en_camino
        es_goal = v["goal"]
        if es_goal:
            face, edge, txt_color = _AZUL, _AZUL, "white"
            label = "OBJETIVO\npuerta\nabierta"
        elif on:
            face, edge, txt_color = "white", _AZUL, _TINTA
            label = _accion_label(v["act"])
        else:
            face, edge, txt_color = "white", _GRIS, _GRIS
            label = _accion_label(v["act"])
        ax.scatter([x], [y], s=3600, facecolor=face, edgecolor=edge,
                   linewidths=2.4 if (on or es_goal) else 1.3, zorder=2)
        ax.text(x, y, label, ha="center", va="center", fontsize=7.5,
                color=txt_color, zorder=3,
                fontweight="bold" if es_goal else "normal")

    # Guías de profundidad (recesivas) y anotación del óptimo.
    for d in sorted(por_capa):
        ax.text(d, 1.15, f"paso {d}", ha="center", va="bottom",
                fontsize=8, color=_GRIS)
    ax.annotate(
        "camino más corto = óptimo (3 acciones)",
        xy=(1.5, 0), xytext=(1.5, 0.72), ha="center", fontsize=8.5,
        color=_AZUL, fontweight="bold",
    )
    ax.text(
        3.55, -3.4,
        "la llave está oculta bajo la alfombra: examinarla es el paso clave.\n"
        "las ramas grises son estados que la BFS explora y descarta —\n"
        "el escritorio es un señuelo (cajones vacíos); re-examinarlo no\n"
        "acerca al objetivo. Esa es la redundancia que penaliza el\n"
        "overhead-vs-óptimo (y que puntúa el judge).",
        ha="right", va="center", fontsize=7.5, color=_GRIS, style="italic",
    )

    ax.set_title(
        "Grafo de estados de «study-with-key»: el óptimo es el camino más corto (BFS)",
        fontsize=11, color=_TINTA,
    )
    ax.set_xlim(-0.5, 3.6)
    ax.set_ylim(-4.1, 1.5)
    ax.axis("off")
    fig.tight_layout()
    out = _REPO / "docs" / "m3_grafo_estados.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Generado: {out}")


if __name__ == "__main__":
    main()
