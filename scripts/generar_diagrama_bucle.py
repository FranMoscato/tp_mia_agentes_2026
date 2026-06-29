"""Genera el diagrama de flujo del bucle `run()` del M1 como PNG.

Uso:
    python scripts/generar_diagrama_bucle.py

Produce `docs/bucle_run_m1.png`. Requiere matplotlib (solo para regenerar).
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Polygon
import matplotlib.pyplot as plt

AZUL = "#dbeafe"
AZUL_B = "#2563eb"
AMARILLO = "#fef9c3"
AMARILLO_B = "#ca8a04"
VERDE = "#dcfce7"
VERDE_B = "#16a34a"
ROJO = "#fee2e2"
ROJO_B = "#dc2626"
GRIS = "#f1f5f9"
GRIS_B = "#94a3b8"


def caja(ax, x, y, w, h, texto, face, edge, fontsize=9.5, weight="normal"):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.02,rounding_size=0.06",
            linewidth=1.6, edgecolor=edge, facecolor=face, zorder=2,
        )
    )
    ax.text(x + w / 2, y + h / 2, texto, ha="center", va="center",
            fontsize=fontsize, weight=weight, zorder=3)


def rombo(ax, cx, cy, w, h, texto, face, edge, fontsize=9):
    pts = [(cx, cy + h / 2), (cx + w / 2, cy), (cx, cy - h / 2), (cx - w / 2, cy)]
    ax.add_patch(Polygon(pts, closed=True, linewidth=1.6,
                         edgecolor=edge, facecolor=face, zorder=2))
    ax.text(cx, cy, texto, ha="center", va="center", fontsize=fontsize, zorder=3)


def flecha(ax, p0, p1, texto="", color="#334155", rad=0.0, off=(0, 0), fs=8.5):
    ax.add_patch(
        FancyArrowPatch(p0, p1, connectionstyle=f"arc3,rad={rad}",
                        arrowstyle="-|>", mutation_scale=15, linewidth=1.5,
                        color=color, zorder=1)
    )
    if texto:
        mx = (p0[0] + p1[0]) / 2 + off[0]
        my = (p0[1] + p1[1]) / 2 + off[1]
        ax.text(mx, my, texto, ha="center", va="center", fontsize=fs, color=color,
                style="italic",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.9),
                zorder=4)


def main() -> None:
    fig, ax = plt.subplots(figsize=(9.5, 12))
    ax.set_xlim(0, 9.5)
    ax.set_ylim(0, 12)
    ax.axis("off")

    ax.text(4.75, 11.6, "Bucle de run(user_message)", ha="center",
            fontsize=14, weight="bold")

    cx = 4.75  # eje central

    # Inicio
    caja(ax, cx - 2.0, 10.6, 4.0, 0.7,
         "messages = [{user}]\nllamadas = 0", GRIS, GRIS_B)

    # Primera (y siguientes) llamada al LLM
    caja(ax, cx - 2.2, 9.3, 4.4, 0.9,
         "chat(messages, tools, system)\nllamadas += 1  |  acumular tokens",
         AZUL, AZUL_B)

    # Decision: hay tool_calls?
    rombo(ax, cx, 7.8, 3.6, 1.5,
          "¿response.tool_calls\ny llamadas < max?", AMARILLO, AMARILLO_B)

    # Rama NO -> respuesta final
    caja(ax, 6.7, 7.4, 2.6, 0.9,
         "answer = content or \"\"\ndevolver AgentResult", VERDE, VERDE_B)

    # Rama SI -> registrar assistant + ejecutar tools
    caja(ax, cx - 2.3, 5.7, 4.6, 0.9,
         "append assistant\n(content + tool_calls con id)", AZUL, AZUL_B)

    # Por cada tool_call: _ejecutar_tool
    rombo(ax, cx, 4.0, 4.2, 1.6,
          "_ejecutar_tool(call):\n¿existe? ¿args JSON?\n¿corre sin excepción?",
          AMARILLO, AMARILLO_B, fontsize=8.5)

    # Exito
    caja(ax, cx - 3.9, 2.2, 3.2, 1.0,
         "OK:\nstep.tool_output = str(out)\nstep.error = None", VERDE, VERDE_B,
         fontsize=8.5)
    # Error
    caja(ax, cx + 0.7, 2.2, 3.2, 1.0,
         "FALLO:\nstep.error = mensaje\nstep.tool_output = None", ROJO, ROJO_B,
         fontsize=8.5)

    # Volcado comun
    caja(ax, cx - 2.3, 0.7, 4.6, 0.9,
         "append role:\"tool\" (resultado/error)\nresultado.steps.append(step)",
         GRIS, GRIS_B)

    # === Flechas ===
    flecha(ax, (cx, 10.6), (cx, 10.2))
    flecha(ax, (cx, 9.3), (cx, 8.55))
    # decision NO
    flecha(ax, (cx + 1.8, 7.8), (6.7, 7.85), "no", off=(0.0, 0.25), color=VERDE_B)
    # decision SI
    flecha(ax, (cx, 7.05), (cx, 6.6), "sí", off=(0.35, 0.0), color=AZUL_B)
    # assistant -> ejecutar
    flecha(ax, (cx, 5.7), (cx, 4.8))
    # ejecutar -> OK
    flecha(ax, (cx - 1.3, 3.6), (cx - 2.3, 3.2), "éxito", off=(0.1, 0.25),
           color=VERDE_B)
    # ejecutar -> error
    flecha(ax, (cx + 1.3, 3.6), (cx + 2.3, 3.2), "fallo", off=(-0.1, 0.25),
           color=ROJO_B)
    # OK -> volcado
    flecha(ax, (cx - 2.3, 2.2), (cx - 1.3, 1.6), rad=-0.2)
    # error -> volcado
    flecha(ax, (cx + 2.3, 2.2), (cx + 1.3, 1.6), rad=0.2)
    # volcado -> vuelve al chat (loop). Curva por la izquierda.
    flecha(ax, (cx - 2.3, 1.15), (0.55, 1.15), color="#7c3aed")
    ax.add_patch(FancyArrowPatch((0.55, 1.15), (0.55, 9.75),
                 connectionstyle="arc3,rad=0.0", arrowstyle="-",
                 linewidth=1.5, color="#7c3aed", zorder=1))
    flecha(ax, (0.55, 9.75), (cx - 2.2, 9.75), "siguiente iteración\n(vuelve al LLM)",
           color="#7c3aed", off=(0.4, 0.3))

    fig.text(0.5, 0.02,
             "Corte del bucle: el LLM responde sin tool_calls (respuesta final) "
             "o se alcanza max_iterations.",
             ha="center", fontsize=9, style="italic")

    out = Path(__file__).resolve().parent.parent / "docs" / "bucle_run_m1.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Diagrama generado en: {out}")


if __name__ == "__main__":
    main()
