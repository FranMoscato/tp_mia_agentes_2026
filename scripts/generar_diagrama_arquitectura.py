"""Genera el diagrama de arquitectura del M1 como PNG.

Uso:
    python scripts/generar_diagrama_arquitectura.py

Produce `docs/arquitectura_m1.png`. Requiere matplotlib (no es dependencia de
la entrega; se instala aparte solo para regenerar la imagen).

El diagrama es declarativo: si cambia la arquitectura, se edita acá y se
regenera la imagen, manteniéndola sincronizada con el código.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # backend sin ventana (renderiza a archivo)

import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import matplotlib.pyplot as plt

# Paleta de colores por tipo de componente.
COLOR_TUYO = "#dbeafe"      # azul claro: código del grupo (student_framework)
COLOR_FIJO = "#fee2e2"      # rojo claro: código FIJO de la cátedra (no se toca)
COLOR_TOOLS = "#dcfce7"     # verde claro: herramientas
COLOR_BORDE_TUYO = "#2563eb"
COLOR_BORDE_FIJO = "#dc2626"
COLOR_BORDE_TOOLS = "#16a34a"


def caja(ax, x, y, w, h, texto, face, edge, fontsize=10, weight="normal"):
    """Dibuja una caja redondeada con texto centrado."""
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        linewidth=1.8,
        edgecolor=edge,
        facecolor=face,
        zorder=2,
    )
    ax.add_patch(box)
    ax.text(
        x + w / 2,
        y + h / 2,
        texto,
        ha="center",
        va="center",
        fontsize=fontsize,
        weight=weight,
        zorder=3,
    )


def flecha(ax, xy_from, xy_to, texto="", color="#334155", rad=0.0, offset=(0, 0)):
    """Dibuja una flecha curva con etiqueta opcional."""
    arrow = FancyArrowPatch(
        xy_from,
        xy_to,
        connectionstyle=f"arc3,rad={rad}",
        arrowstyle="-|>",
        mutation_scale=16,
        linewidth=1.6,
        color=color,
        zorder=1,
    )
    ax.add_patch(arrow)
    if texto:
        mx = (xy_from[0] + xy_to[0]) / 2 + offset[0]
        my = (xy_from[1] + xy_to[1]) / 2 + offset[1]
        ax.text(
            mx,
            my,
            texto,
            ha="center",
            va="center",
            fontsize=8.5,
            color=color,
            style="italic",
            bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85),
            zorder=4,
        )


def main() -> None:
    fig, ax = plt.subplots(figsize=(12, 8.5))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(
        6,
        8.7,
        "Arquitectura — Milestone 1 (bucle del agente y herramientas)",
        ha="center",
        va="center",
        fontsize=14,
        weight="bold",
    )

    # --- build_agent (entrada) ---
    caja(ax, 4.3, 7.3, 3.4, 0.9,
         "build_agent(config)\n[student_framework/__init__.py]",
         COLOR_TUYO, COLOR_BORDE_TUYO, fontsize=10, weight="bold")

    # --- MyAgent (centro) ---
    caja(ax, 3.6, 3.5, 4.8, 3.0, "", COLOR_TUYO, COLOR_BORDE_TUYO)
    ax.text(6.0, 6.15, "MyAgent", ha="center", fontsize=12, weight="bold")
    ax.text(6.0, 5.75, "[student_framework/agent.py]", ha="center", fontsize=8.5,
            style="italic", color="#475569")
    ax.text(
        6.0, 4.55,
        "_tools   : { nombre -> callable }\n"
        "_schemas : { nombre -> ToolSchema }\n"
        "_system, _max_iterations\n\n"
        "register_tool(callable, ToolSchema)\n"
        "run(user_message) -> AgentResult",
        ha="center", va="center", fontsize=9.5, family="monospace",
    )

    # --- LLMClient (izquierda, FIJO) ---
    caja(ax, 0.3, 3.7, 2.7, 2.6, "", COLOR_FIJO, COLOR_BORDE_FIJO)
    ax.text(1.65, 5.95, "LLMClient", ha="center", fontsize=11, weight="bold")
    ax.text(1.65, 5.6, "(FIJO — cátedra)", ha="center", fontsize=8, style="italic",
            color="#991b1b")
    ax.text(
        1.65, 4.6,
        "BedrockProvider\nOllamaProvider\nMockLLMClient\n\n"
        "to_llm_spec() por\ncada ToolSchema",
        ha="center", va="center", fontsize=9,
    )

    # --- Herramientas (derecha) ---
    caja(ax, 9.0, 3.7, 2.7, 2.6, "", COLOR_TOOLS, COLOR_BORDE_TOOLS)
    ax.text(10.35, 5.95, "Herramientas", ha="center", fontsize=11, weight="bold")
    ax.text(10.35, 5.6, "[student_framework/tools/]", ha="center", fontsize=7.5,
            style="italic", color="#166534")
    ax.text(
        10.35, 4.55,
        "calculadora\nleer_archivo\ncontar_palabras\n\n"
        "callable +\nToolSchema.from_callable",
        ha="center", va="center", fontsize=9,
    )

    # --- LLMResponse / proveedor reales (abajo izquierda) ---
    caja(ax, 0.3, 1.2, 2.7, 1.5,
         "Proveedor LLM\nAWS Bedrock / Ollama\n(o Mock en tests)",
         "#f1f5f9", "#94a3b8", fontsize=9)

    # --- AgentResult (abajo centro) ---
    caja(ax, 4.3, 1.4, 3.4, 1.1,
         "AgentResult\n(answer, steps[], tokens)",
         "#fef9c3", "#ca8a04", fontsize=10, weight="bold")

    # === Flechas ===
    # build_agent -> MyAgent (construye y registra tools)
    flecha(ax, (6.0, 7.3), (6.0, 6.5), "construye + register_tool", offset=(0, 0.0))

    # MyAgent <-> LLMClient
    flecha(ax, (3.6, 5.3), (3.0, 5.3), "chat(messages,\ntools, system)", rad=0.15,
           offset=(0.0, 0.35))
    flecha(ax, (3.0, 4.5), (3.6, 4.5), "LLMResponse\n(content / tool_calls)",
           rad=0.15, offset=(0.0, -0.4))

    # MyAgent <-> Herramientas
    flecha(ax, (8.4, 5.3), (9.0, 5.3), "callable(**args)", rad=-0.15,
           offset=(0.0, 0.32))
    flecha(ax, (9.0, 4.5), (8.4, 4.5), "str (salida)", rad=-0.15, offset=(0.0, -0.3))

    # LLMClient <-> Proveedor
    flecha(ax, (1.65, 3.7), (1.65, 2.7), "", rad=0.0)
    flecha(ax, (1.95, 2.7), (1.95, 3.7), "", rad=0.0)

    # MyAgent -> AgentResult
    flecha(ax, (6.0, 3.5), (6.0, 2.5), "devuelve")

    # --- Leyenda ---
    leg = [
        mpatches.Patch(facecolor=COLOR_TUYO, edgecolor=COLOR_BORDE_TUYO,
                       label="Código del grupo (student_framework)"),
        mpatches.Patch(facecolor=COLOR_FIJO, edgecolor=COLOR_BORDE_FIJO,
                       label="Código FIJO de la cátedra (no editable)"),
        mpatches.Patch(facecolor=COLOR_TOOLS, edgecolor=COLOR_BORDE_TOOLS,
                       label="Herramientas (3 obligatorias)"),
    ]
    ax.legend(handles=leg, loc="lower center", bbox_to_anchor=(0.5, -0.02),
              ncol=3, fontsize=8.5, frameon=False)

    out = Path(__file__).resolve().parent.parent / "docs" / "arquitectura_m1.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"Diagrama generado en: {out}")


if __name__ == "__main__":
    main()
