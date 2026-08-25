"""Diagramas de arquitectura de la solución de M3.

Produce dos PNGs en `docs/`:

  - m3_arquitectura.png : las 3 capas (entorno / agente / evaluación) y el
    flujo entre ellas, con un código de color que distingue AGENTE autónomo de
    WORKFLOW determinístico (la distinción de Anthropic, §1 del informe).
  - m3_loop_react.png   : zoom al loop ReAct del agente, marcando en cada paso
    quién decide (LLM autónomo) vs. qué es control-flow fijo (gate, memoria,
    summarizer).

Son diagramas conceptuales (no gráficos de datos), así que el foco está en la
claridad de las cajas y las flechas, no en una paleta categórica.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

_REPO = Path(__file__).resolve().parent.parent
_DOCS = _REPO / "docs"

# Código de color = la taxonomía que queremos enseñar.
AZUL = "#2a78d6"   # AGENTE autónomo: el LLM elige la próxima acción.
VERDE = "#1baf7a"  # WORKFLOW determinístico: código, 0 tokens, pasos fijos.
AMBAR = "#eb6834"  # WORKFLOW con LLM: llamada LLM que corre SIEMPRE igual (no autónoma).
GRIS = "#9aa0a8"   # ENTORNO: el mundo determinístico sobre el que se actúa.
TINTA = "#1f2328"

_FILL = {AZUL: "#eaf2fc", VERDE: "#e7f7f1", AMBAR: "#fdece4", GRIS: "#f1f2f4"}


def _caja(ax, x, y, w, h, texto, color, *, bold=False, fs=8.5):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.6",
        facecolor=_FILL[color], edgecolor=color, linewidth=1.8, zorder=2,
    ))
    ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center",
            fontsize=fs, color=TINTA, zorder=3,
            fontweight="bold" if bold else "normal")


def _banda(ax, x, y, w, h, titulo, color):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.5,rounding_size=2.2",
        facecolor="none", edgecolor=color, linewidth=1.4,
        linestyle=(0, (6, 3)), zorder=1,
    ))
    ax.text(x + 1.5, y + h - 1.4, titulo, ha="left", va="top",
            fontsize=9.5, color=color, fontweight="bold", zorder=3)


def _flecha(ax, p0, p1, color, *, lw=2.2, doble=False, estilo="-|>"):
    ax.add_patch(FancyArrowPatch(
        p0, p1, arrowstyle=("<|-|>" if doble else estilo),
        mutation_scale=15, color=color, lw=lw, zorder=4,
        shrinkA=2, shrinkB=2,
    ))


def _leyenda(ax, x, y):
    items = [
        (AZUL, "Agente autónomo — el LLM elige la próxima acción (no hay flujo prefijado)"),
        (VERDE, "Workflow determinístico — código, 0 tokens, pasos fijos que envuelven al LLM"),
        (AMBAR, "Workflow con LLM — llamada LLM que corre SIEMPRE igual (summarizer, judge): no es autónoma"),
        (GRIS, "Entorno — la sala de escape (mundo determinístico) sobre la que actúa el agente"),
    ]
    for i, (c, t) in enumerate(items):
        yy = y - i * 3.1
        ax.add_patch(FancyBboxPatch(
            (x, yy), 3, 1.8, boxstyle="round,pad=0.1,rounding_size=0.6",
            facecolor=_FILL[c], edgecolor=c, linewidth=1.6, zorder=3))
        ax.text(x + 4, yy + 0.9, t, ha="left", va="center", fontsize=7.8,
                color=TINTA, zorder=3)


# ---------------------------------------------------------------------------
# Diagrama 1: arquitectura en capas
# ---------------------------------------------------------------------------


def diagrama_arquitectura() -> None:
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_xlim(0, 100)
    ax.set_ylim(-16, 100)
    ax.axis("off")

    ax.text(50, 98.5, "Arquitectura de la solución (M3): entorno · agente · evaluación",
            ha="center", va="top", fontsize=13, color=TINTA, fontweight="bold")

    # --- ① EVALUACIÓN (workflow) --------------------------------------------
    _banda(ax, 3, 70, 94, 22, "①  EVALUACIÓN — eval/   ·   workflow determinístico", VERDE)
    _caja(ax, 7, 79, 24, 8, "Barrido\n8 escenarios × 3 configs\n× N repeats", VERDE)
    _caja(ax, 38, 79, 24, 8, "run_one()\narma mundo + agente,\ncorre y verifica", VERDE)
    _caja(ax, 69, 79, 24, 8, "Métricas\naccuracy · Wilson · pass^k\noverhead · latencia · tokens", VERDE)
    _caja(ax, 7, 71.5, 24, 5.5, "optimal.py · BFS → óptimo", VERDE, fs=8)
    _caja(ax, 69, 71.5, 24, 5.5, "judge.py · LLM-as-judge (modelo distinto)", AMBAR, fs=7.8)

    # --- ② AGENTE ------------------------------------------------------------
    _banda(ax, 3, 38, 94, 27, "②  AGENTE — student_framework · MyAgent   (loop ReAct)", AZUL)
    _caja(ax, 39, 53.5, 23, 8.5, "LLM decide\nla próxima acción\n(chat + tools)", AZUL, bold=True)
    _caja(ax, 7, 51.5, 26, 7.5, "ventana de memoria\nsliding-window + goal", VERDE, fs=8)
    _caja(ax, 39, 41.5, 23, 7.5, "_ejecutar_tool\n+ gate (if determinístico)", VERDE, fs=8)
    _caja(ax, 68, 51.5, 25, 7.5, "summarizer\nupdate_memory → GameState", AMBAR, fs=8)

    # loop interno (recencia: memoria -> LLM -> ejecutar -> [summarizer] -> LLM)
    _flecha(ax, (33, 55.5), (39, 56.5), VERDE, lw=1.8)          # memoria -> LLM
    _flecha(ax, (50.5, 53.5), (50.5, 49), AZUL)                 # LLM -> ejecutar (acción elegida)
    _flecha(ax, (62, 45), (68, 52), AMBAR, lw=1.8)              # ejecutar -> summarizer
    _flecha(ax, (80, 51.5), (58, 58), AMBAR, lw=1.8)            # summarizer -> LLM (estado inyectado)
    ax.text(88, 44, "hasta check_goal\no max_iterations", ha="center", va="center",
            fontsize=7.5, color=AZUL, style="italic")

    # --- ③ ENTORNO -----------------------------------------------------------
    _banda(ax, 3, 6, 94, 25, "③  ENTORNO — sala de escape · mia_world   (determinístico)", GRIS)
    _caja(ax, 7, 16, 26, 9, "World (estado)\nrooms · items · inventory\n· revealed", GRIS, fs=8)
    _caja(ax, 38, 16, 24, 9, "5 tools\nlook · examine · take\nuse · go", GRIS, fs=8)
    _caja(ax, 68, 16, 25, 9, "check_goal()\nverifica el objetivo\npor código", GRIS, fs=8)
    _caja(ax, 38, 8.5, 24, 5, "8 escenarios (JSON)", GRIS, fs=8)

    # --- flujo entre capas ---------------------------------------------------
    # Eval corre el agente.
    _flecha(ax, (50, 79), (50, 62), VERDE)
    ax.text(52, 70.5, "corre el agente por caso", ha="left", va="center",
            fontsize=8, color=VERDE)
    # Agente <-> Mundo: acción / observación (LA interacción ReAct).
    _flecha(ax, (50, 41.5), (50, 25), AZUL, doble=True, lw=2.6)
    ax.text(52, 33, "acción  ↓\nobservación  ↑", ha="left", va="center",
            fontsize=8.5, color=AZUL, fontweight="bold")
    # Resultado del mundo -> métricas (éxito/fracaso verificado).
    _flecha(ax, (88, 25), (90, 79), GRIS, lw=1.8)
    ax.text(91.5, 50, "resultado\nverificado", ha="left", va="center",
            fontsize=7.6, color=GRIS)
    # Trace del agente -> judge.
    _flecha(ax, (62, 57.5), (80, 71.5), AMBAR, lw=1.8)
    ax.text(72, 66, "trace", ha="center", va="center", fontsize=7.6, color=AMBAR)
    # optimal usa el mundo.
    _flecha(ax, (19, 71.5), (19, 25), VERDE, lw=1.5, estilo="-|>")
    ax.text(20.5, 48, "BFS sobre\nel mundo", ha="left", va="center",
            fontsize=7.4, color=VERDE)

    _leyenda(ax, 6, 1)  # debajo de la banda del entorno, sin chocar el título.
    fig.tight_layout()
    out = _DOCS / "m3_arquitectura.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Generado: {out}")


# ---------------------------------------------------------------------------
# Diagrama 2: el loop ReAct por dentro
# ---------------------------------------------------------------------------


def diagrama_loop() -> None:
    fig, ax = plt.subplots(figsize=(11, 7.2))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")
    ax.text(50, 97, "El loop ReAct por dentro: qué decide el LLM vs. qué es control-flow fijo",
            ha="center", va="top", fontsize=12.5, color=TINTA, fontweight="bold")

    # Ciclo de 4 pasos en cruz.
    _caja(ax, 34, 74, 32, 12,
          "1 · el LLM DECIDE\nqué tool llamar\n(chat + tools, system prompt)", AZUL, bold=True)
    _caja(ax, 66, 46, 30, 12,
          "2 · gate (if)\n¿la acción respeta las reglas?\nsi no: la bloquea con un error", VERDE)
    _caja(ax, 34, 20, 32, 12,
          "3 · el MUNDO ejecuta la tool\nlook/examine/take/use/go\n→ nueva observación", GRIS)
    _caja(ax, 4, 46, 30, 12,
          "4 · memoria + summarizer\nventana (código) + GameState (LLM)\nse prepara el próximo contexto", AMBAR)

    # Flechas del ciclo (sentido horario).
    _flecha(ax, (58, 74), (74, 58), AZUL)          # 1 -> 2
    _flecha(ax, (74, 46), (58, 32), VERDE)         # 2 -> 3
    _flecha(ax, (34, 26), (20, 46), GRIS)          # 3 -> 4
    _flecha(ax, (26, 58), (42, 74), AMBAR)         # 4 -> 1

    ax.text(50, 53, "REPETIR\nhasta abrir la puerta\n(check_goal) o agotar\nmax_iterations",
            ha="center", va="center", fontsize=9, color=TINTA, fontweight="bold")

    # Anotaciones de la taxonomía en cada paso.
    ax.text(50, 88.5, "único paso autónomo", ha="center", va="center",
            fontsize=8, color=AZUL, style="italic")
    ax.text(81, 59.5, "determinístico · 0 tokens", ha="center", va="center",
            fontsize=8, color=VERDE, style="italic")
    ax.text(50, 15.5, "determinístico (entorno)", ha="center", va="center",
            fontsize=8, color=GRIS, style="italic")
    ax.text(19, 59.5, "paso fijo (LLM + código)", ha="center", va="center",
            fontsize=8, color=AMBAR, style="italic")

    fig.tight_layout()
    out = _DOCS / "m3_loop_react.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Generado: {out}")


def main() -> None:
    _DOCS.mkdir(exist_ok=True)
    diagrama_arquitectura()
    diagrama_loop()


if __name__ == "__main__":
    main()
