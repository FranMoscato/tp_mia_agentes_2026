"""Genera los diagramas del informe de M2 como PNG.

Uso:
    python scripts/generar_diagramas_m2.py

Produce, en `docs/`:
  - memoria_m2.png          (sliding window por recencia)
  - structured_call_m2.png  (flujo de reparación de structured_call)
  - resiliencia_m2.png      (reintentos ante fallos transitorios)

Requiere matplotlib (solo para regenerar). Reutiliza la paleta y los helpers
del generador de M1 para mantener un estilo consistente.
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
VIOLETA = "#ede9fe"
VIOLETA_B = "#7c3aed"

DOCS = Path(__file__).resolve().parent.parent / "docs"


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


def _guardar(fig, nombre: str) -> None:
    DOCS.mkdir(parents=True, exist_ok=True)
    out = DOCS / nombre
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Diagrama generado en: {out}")


# ---------------------------------------------------------------------------
# 1) Memoria: sliding window por recencia
# ---------------------------------------------------------------------------


def diagrama_memoria() -> None:
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 5)
    ax.axis("off")

    ax.text(5.5, 4.6, "Gestión de memoria: sliding window por recencia",
            ha="center", fontsize=14, weight="bold")

    # Fila de mensajes del historial (self.messages), del más viejo al actual.
    etiquetas = [
        ("user 0", AZUL, AZUL_B), ("assist 0", GRIS, GRIS_B),
        ("user 1", AZUL, AZUL_B), ("assist 1", GRIS, GRIS_B),
        ("user 2", AZUL, AZUL_B), ("assist 2", GRIS, GRIS_B),
        ("user 3", AZUL, AZUL_B), ("assist 3", GRIS, GRIS_B),
        ("user\nAHORA", VERDE, VERDE_B),
    ]
    x0, y0, w, h, gap = 0.5, 2.6, 1.05, 0.8, 0.1
    xs = []
    for i, (txt, face, edge) in enumerate(etiquetas):
        x = x0 + i * (w + gap)
        xs.append(x)
        caja(ax, x, y0, w, h, txt, face, edge, fontsize=8.5,
             weight="bold" if "AHORA" in txt else "normal")

    ax.text(x0, y0 + h + 0.35, "self.messages  (historial completo, persiste entre run)",
            ha="left", fontsize=9.5, style="italic", color="#334155")
    ax.annotate("", xy=(xs[-1] + w, y0 - 0.35), xytext=(x0, y0 - 0.35),
                arrowprops=dict(arrowstyle="->", color=GRIS_B, lw=1.3))
    ax.text(x0, y0 - 0.6, "más antiguo", ha="left", fontsize=8, color=GRIS_B)
    ax.text(xs[-1] + w, y0 - 0.6, "más reciente", ha="right", fontsize=8, color=GRIS_B)

    # Ventana: cubre la cola más reciente (últimos N = max_history_messages).
    win_left = xs[5] - gap / 2
    win_right = xs[-1] + w + 0.05
    ax.add_patch(FancyBboxPatch(
        (win_left, y0 - 0.18), win_right - win_left, h + 0.36,
        boxstyle="round,pad=0.02,rounding_size=0.05",
        linewidth=2.2, edgecolor=VIOLETA_B, facecolor="none", zorder=5,
    ))
    ax.text((win_left + win_right) / 2, y0 + h + 0.72,
            "ventana enviada al LLM  (≤ max_history_messages)",
            ha="center", fontsize=10, weight="bold", color=VIOLETA_B)

    # Zona descartada.
    ax.text((x0 + win_left) / 2, y0 + h + 0.72, "descartado\n(más antiguo)",
            ha="center", fontsize=9, color=ROJO_B, style="italic")

    # Notas de invariantes.
    caja(ax, 0.5, 0.35, 10.0, 1.35,
         "_windowed_messages()  →  devuelve una COPIA de la cola (self.messages nunca se comparte mutable)\n\n"
         "• Recencia: si la cola no incluye ningún 'user', se fuerza el último mensaje de usuario dentro de la ventana.\n"
         "• La ventana siempre empieza en un mensaje 'user' (se descartan tool/assistant huérfanos del frente).",
         VIOLETA, VIOLETA_B, fontsize=9.5)

    _guardar(fig, "memoria_m2.png")


# ---------------------------------------------------------------------------
# 2) structured_call: flujo de reparación
# ---------------------------------------------------------------------------


def diagrama_structured_call() -> None:
    fig, ax = plt.subplots(figsize=(10, 12))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 12)
    ax.axis("off")

    ax.text(5, 11.6, "structured_call: salida estructurada con reparación",
            ha="center", fontsize=14, weight="bold")

    cx = 5.0

    caja(ax, cx - 2.4, 10.5, 4.8, 0.8,
         "chat(messages, tools=[final_result], system)\n(envuelto en reintentos)",
         AZUL, AZUL_B, fontsize=9)

    rombo(ax, cx, 9.1, 3.4, 1.3, "¿hay tool_calls?", AMARILLO, AMARILLO_B)

    # Rama texto libre (no tool_calls)
    caja(ax, 0.3, 8.75, 3.0, 0.9,
         "CASO 1 · texto libre\nappend: 'usá final_result'", ROJO, ROJO_B,
         fontsize=8.5)

    rombo(ax, cx, 7.0, 3.6, 1.3, "¿la tool es\nfinal_result?", AMARILLO, AMARILLO_B)

    # Rama tool equivocada
    caja(ax, 0.3, 6.65, 3.0, 0.9,
         "CASO 2 · tool equivocada\nappend: 'finalizá con\nfinal_result'", ROJO, ROJO_B,
         fontsize=8.5)

    rombo(ax, cx, 4.8, 4.0, 1.5,
          "schema.model_validate(args)\n¿valida?", AMARILLO, AMARILLO_B, fontsize=8.5)

    # Rama args inválidos
    caja(ax, 0.3, 4.45, 3.0, 1.0,
         "CASO 3 · args inválidos\nappend: error de\nvalidación concreto", ROJO, ROJO_B,
         fontsize=8.5)

    # Éxito
    caja(ax, cx - 2.0, 2.9, 4.0, 0.9,
         "return  instancia Pydantic  ✓", VERDE, VERDE_B, fontsize=10, weight="bold")

    # Control de reintentos / fallo
    rombo(ax, cx, 1.4, 3.2, 1.3,
          "¿quedan intentos?\n(max_repair_attempts)", AMARILLO, AMARILLO_B, fontsize=8.5)
    caja(ax, 6.95, 1.0, 2.5, 0.85,
         "raise RuntimeError\n(fallo limpio)", ROJO, ROJO_B, fontsize=9, weight="bold")

    # Flechas verticales
    flecha(ax, (cx, 10.5), (cx, 9.75))
    flecha(ax, (cx, 8.45), (cx, 7.65), "sí", off=(0.3, 0))
    flecha(ax, (cx, 6.35), (cx, 5.55), "sí", off=(0.3, 0))
    flecha(ax, (cx, 4.05), (cx, 3.8), "sí", off=(0.3, 0), color=VERDE_B)

    # Ramas a la izquierda (fallos → reparación)
    flecha(ax, (cx - 1.7, 9.1), (3.3, 9.2), "no", off=(0, 0.25), color=ROJO_B)
    flecha(ax, (cx - 1.8, 7.0), (3.3, 7.1), "no", off=(0, 0.25), color=ROJO_B)
    flecha(ax, (cx - 2.0, 4.8), (3.3, 4.95), "no", off=(0, 0.25), color=ROJO_B)

    # Los tres casos bajan a "¿quedan intentos?"
    for yb in (8.75, 6.65, 4.45):
        ax.add_patch(FancyArrowPatch((1.8, yb), (1.8, 2.0),
                     connectionstyle="arc3,rad=0.0", arrowstyle="-",
                     linewidth=1.3, color=ROJO_B, zorder=1, alpha=0.5))
    flecha(ax, (1.8, 2.0), (cx - 1.6, 1.4), color=ROJO_B)

    # ¿quedan intentos? no -> raise (flecha corta, etiqueta fuera de la caja)
    flecha(ax, (cx + 1.6, 1.4), (6.9, 1.4), "no", off=(-0.05, 0.28), color=ROJO_B)

    # ¿quedan intentos? sí -> reintenta: sube por la derecha al chat inicial
    ax.add_patch(FancyArrowPatch((cx, 2.05), (cx, 2.5),
                 arrowstyle="-", linewidth=1.5, color=VIOLETA_B, zorder=1))
    ax.text(cx + 0.28, 2.32, "sí", fontsize=8.5, color=VIOLETA_B, style="italic",
            ha="left", va="center")
    ax.add_patch(FancyArrowPatch((cx, 2.5), (9.7, 2.5),
                 arrowstyle="-", linewidth=1.5, color=VIOLETA_B, zorder=1))
    ax.add_patch(FancyArrowPatch((9.7, 2.5), (9.7, 10.9),
                 arrowstyle="-", linewidth=1.5, color=VIOLETA_B, zorder=1))
    flecha(ax, (9.7, 10.9), (cx + 2.4, 10.9),
           "reintenta con\ncontexto de reparación", color=VIOLETA_B, off=(-0.15, 0.4))

    _guardar(fig, "structured_call_m2.png")


# ---------------------------------------------------------------------------
# 3) Resiliencia: reintentos ante fallos transitorios
# ---------------------------------------------------------------------------


def diagrama_resiliencia() -> None:
    fig, ax = plt.subplots(figsize=(9.5, 9))
    ax.set_xlim(0, 9.5)
    ax.set_ylim(0, 9)
    ax.axis("off")

    ax.text(4.75, 8.6, "_con_reintentos: resiliencia ante fallos transitorios",
            ha="center", fontsize=13.5, weight="bold")

    cx = 4.75

    caja(ax, cx - 1.6, 7.5, 3.2, 0.7, "intento = 0", GRIS, GRIS_B)
    caja(ax, cx - 2.0, 6.2, 4.0, 0.8,
         "fn()  →  chat() o tool()", AZUL, AZUL_B, fontsize=10)

    rombo(ax, cx, 4.9, 2.8, 1.2, "¿lanzó\nexcepción?", AMARILLO, AMARILLO_B)

    caja(ax, 6.6, 4.5, 2.6, 0.9, "return resultado  ✓", VERDE, VERDE_B,
         fontsize=10, weight="bold")

    rombo(ax, cx, 3.1, 3.8, 1.3,
          "_es_error_transitorio?\n(timeout/5xx/429/red)", AMARILLO, AMARILLO_B,
          fontsize=8.5)

    caja(ax, 6.4, 2.7, 3.0, 0.9,
         "raise  (aflora limpio)\nbug / 4xx / args", ROJO, ROJO_B, fontsize=9)

    rombo(ax, cx, 1.2, 3.4, 1.2,
          "¿intento < max_retries?", AMARILLO, AMARILLO_B, fontsize=8.5)

    caja(ax, 0.3, 0.85, 2.6, 0.9,
         "raise último error\n(reintentos agotados)", ROJO, ROJO_B, fontsize=8.5)

    # Flechas
    flecha(ax, (cx, 7.5), (cx, 7.0))
    flecha(ax, (cx, 6.2), (cx, 5.5))
    flecha(ax, (cx + 1.4, 4.9), (6.6, 4.95), "no", off=(0, 0.25), color=VERDE_B)
    flecha(ax, (cx, 4.3), (cx, 3.75), "sí", off=(0.3, 0), color=ROJO_B)
    flecha(ax, (cx + 1.9, 3.1), (6.4, 3.15), "no", off=(0, 0.25), color=ROJO_B)
    flecha(ax, (cx, 2.45), (cx, 1.8), "sí", off=(0.3, 0), color=AMARILLO_B)
    flecha(ax, (cx - 1.7, 1.2), (2.9, 1.3), "no", off=(0, 0.25), color=ROJO_B)

    # sí: sleep backoff y vuelve a fn()
    ax.add_patch(FancyArrowPatch((cx + 1.7, 1.2), (8.7, 1.2),
                 arrowstyle="-", linewidth=1.5, color=VIOLETA_B, zorder=1))
    ax.add_patch(FancyArrowPatch((8.7, 1.2), (8.7, 6.6),
                 arrowstyle="-", linewidth=1.5, color=VIOLETA_B, zorder=1))
    flecha(ax, (8.7, 6.6), (cx + 2.0, 6.6),
           "sleep(base·2^intento)\nintento += 1", color=VIOLETA_B, off=(-0.1, 0.4))

    _guardar(fig, "resiliencia_m2.png")


def main() -> None:
    diagrama_memoria()
    diagrama_structured_call()
    diagrama_resiliencia()


if __name__ == "__main__":
    main()
