"""Genera los gráficos del informe de M3 como PNG, a partir de una corrida.

Uso:
    python scripts/generar_graficos_m3.py [--results eval/results/<timestamp>]

Si no se pasa `--results`, toma la corrida más reciente en `eval/results/`.
Produce, en `docs/`:
  - m3_latencia.png   (latencia p50/p95 por configuración)
  - m3_fallos.png     (modos de fallo por configuración, apilados)
  - m3_judge.png      (calidad de exploración del judge por configuración)

Requiere matplotlib (solo para regenerar). Lee `summary.json` y, si existe,
`judge_summary.json` del directorio de resultados.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

_REPO = Path(__file__).resolve().parent.parent
_DOCS = _REPO / "docs"

# Paleta por configuración: slots 1-3 de la paleta categórica validada del skill
# de dataviz (blue/orange/aqua). Validada contra daltonismo con
# scripts/validate_palette.js — la anterior (azul/ámbar/verde) fallaba la
# separación CVD verde↔ámbar en protanopia.
COLOR = {"react": "#2a78d6", "summarizer": "#eb6834", "gate": "#1baf7a"}
# Colores de los modos de fallo (grises/rojos para lo malo, verde para éxito).
COLOR_FALLO = {
    "success": "#16a34a",
    "prosa_en_vez_de_tool": "#ef4444",
    "loop_detected": "#f59e0b",
    "tool_errors": "#a855f7",
    "exhausted_iterations": "#64748b",
    "crash": "#111827",
}


def _latest_results() -> Path:
    dirs = [p for p in (_REPO / "eval" / "results").glob("*/") if (p / "summary.json").exists()]
    if not dirs:
        raise SystemExit("No hay corridas con summary.json en eval/results/.")
    return sorted(dirs, key=lambda p: p.name)[-1]


def _orden_configs(by_config: dict) -> list[str]:
    # Orden fijo y legible; solo los presentes.
    return [c for c in ("react", "summarizer", "gate") if c in by_config]


def grafico_latencia(by_config: dict, meta: dict) -> None:
    configs = _orden_configs(by_config)
    p50 = [by_config[c]["latency_p50_s"] or 0 for c in configs]
    p95 = [by_config[c]["latency_p95_s"] or 0 for c in configs]

    x = range(len(configs))
    w = 0.38
    fig, ax = plt.subplots(figsize=(7, 4.2))
    b1 = ax.bar([i - w / 2 for i in x], p50, w, label="p50", color="#93c5fd")
    b2 = ax.bar([i + w / 2 for i in x], p95, w, label="p95", color="#1d4ed8")
    ax.bar_label(b1, fmt="%.1f", fontsize=8, padding=2)
    ax.bar_label(b2, fmt="%.1f", fontsize=8, padding=2)
    ax.set_xticks(list(x))
    ax.set_xticklabels(configs)
    ax.set_ylabel("Latencia por caso (s)")
    ax.set_title(f"Latencia p50/p95 por configuración\n({meta.get('provider')}/{meta.get('model')}, "
                 f"repeats={meta.get('repeats')})")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_latencia.png", dpi=150)
    plt.close(fig)


def grafico_fallos(by_config: dict, meta: dict) -> None:
    configs = _orden_configs(by_config)
    # Categorías presentes, ordenadas: primero éxito, luego fallos.
    cats: list[str] = []
    for c in configs:
        for k in by_config[c]["failure_breakdown"]:
            if k not in cats:
                cats.append(k)
    orden = [c for c in COLOR_FALLO if c in cats] + [c for c in cats if c not in COLOR_FALLO]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    bottoms = [0] * len(configs)
    for cat in orden:
        vals = [by_config[c]["failure_breakdown"].get(cat, 0) for c in configs]
        ax.bar(configs, vals, bottom=bottoms, label=cat,
               color=COLOR_FALLO.get(cat, "#94a3b8"),
               edgecolor="white", linewidth=0.6)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax.set_ylabel("Casos")
    ax.set_title(f"Modos de fallo por configuración\n({meta.get('provider')}/{meta.get('model')}, "
                 f"repeats={meta.get('repeats')})")
    ax.legend(fontsize=8, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_fallos.png", dpi=150)
    plt.close(fig)


def grafico_costo(by_config: dict, meta: dict) -> None:
    """Tokens por caso, apilando agente vs summarizer (costo del resumen)."""
    configs = _orden_configs(by_config)
    agente = [by_config[c].get("avg_agent_tokens") or 0 for c in configs]
    resumen = [by_config[c].get("avg_memory_tokens") or 0 for c in configs]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    b1 = ax.bar(configs, agente, label="tokens agente", color="#2a78d6")
    b2 = ax.bar(configs, resumen, bottom=agente, label="tokens summarizer",
                color="#eb6834")
    ax.bar_label(b1, fmt="%.0f", fontsize=8, label_type="center")
    for i, r in enumerate(resumen):
        if r:
            ax.text(i, agente[i] + r + max(agente + resumen) * 0.01, f"+{r:.0f}",
                    ha="center", fontsize=8, color="#b45309")
    ax.set_ylabel("Tokens promedio por caso")
    ax.set_title(f"Costo en tokens por configuración\n({meta.get('provider')}/{meta.get('model')})")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_costo.png", dpi=150)
    plt.close(fig)


def grafico_tools(by_config: dict, meta: dict) -> None:
    """Perfil de uso de herramientas por configuración (apilado por verbo)."""
    configs = _orden_configs(by_config)
    verbos = ["look", "examine", "take", "use", "go"]
    # Slots 1-5 de la paleta categórica validada (blue/orange/aqua/yellow/
    # magenta). La anterior (4 tonos de azul) fallaba la separación en visión
    # normal: ni con visión completa se distinguían look/examine.
    colores = {"look": "#2a78d6", "examine": "#eb6834", "take": "#1baf7a",
               "use": "#eda100", "go": "#e87ba4"}

    fig, ax = plt.subplots(figsize=(7, 4.2))
    bottoms = [0] * len(configs)
    for v in verbos:
        vals = [by_config[c].get("tool_usage", {}).get(v, 0) for c in configs]
        if not any(vals):
            continue
        ax.bar(configs, vals, bottom=bottoms, label=v, color=colores.get(v, "#94a3b8"),
               edgecolor="white", linewidth=0.6)
        bottoms = [b + x for b, x in zip(bottoms, vals)]
    ax.set_ylabel("Tool-calls totales")
    ax.set_title(f"Perfil de uso de herramientas por configuración\n"
                 f"({meta.get('provider')}/{meta.get('model')})")
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_tools.png", dpi=150)
    plt.close(fig)


def grafico_latencia_desglosada(by_config: dict, meta: dict) -> None:
    """Latencia p50 desglosada: agente vs. llamada del summarizer (apilada)."""
    configs = _orden_configs(by_config)
    agente = [by_config[c].get("latency_agente_p50_s") or 0 for c in configs]
    resumen = [by_config[c].get("latency_summarizer_p50_s") or 0 for c in configs]
    if not any(resumen):
        return  # sin summarizer instrumentado: no aporta
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.bar(configs, agente, label="agente", color="#2a78d6")
    ax.bar(configs, resumen, bottom=agente, label="summarizer", color="#eb6834")
    ax.set_ylabel("Latencia p50 (s)")
    ax.set_title(f"Latencia p50 desglosada (agente vs. resumen)\n"
                 f"({meta.get('provider')}/{meta.get('model')})")
    ax.legend()
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_latencia_desglosada.png", dpi=150)
    plt.close(fig)


def grafico_redundancia(by_config: dict, meta: dict) -> None:
    """Distribución de la racha máxima de tool-calls repetidas (señal de loop)."""
    configs = _orden_configs(by_config)
    rachas = sorted({int(r) for c in configs
                     for r in by_config[c].get("redundancy_distribution", {})})
    if not rachas:
        return
    x = range(len(configs))
    n = len(rachas)
    w = 0.8 / max(n, 1)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    grises = ["#bfdbfe", "#60a5fa", "#f59e0b", "#ef4444", "#7f1d1d"]
    for i, r in enumerate(rachas):
        vals = [by_config[c].get("redundancy_distribution", {}).get(str(r), 0) for c in configs]
        offs = [xi - 0.4 + w / 2 + i * w for xi in x]
        ax.bar(offs, vals, w, label=f"racha {r}", color=grises[min(i, len(grises) - 1)])
    ax.set_xticks(list(x))
    ax.set_xticklabels(configs)
    ax.set_ylabel("Casos")
    ax.set_title(f"Redundancia: racha máx. de tool-calls repetidas\n"
                 f"({meta.get('provider')}/{meta.get('model')})")
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_redundancia.png", dpi=150)
    plt.close(fig)


def grafico_heatmap(by_config: dict, meta: dict) -> None:
    """Heatmap escenario × config de tasa de éxito (variabilidad por escenario)."""
    configs = _orden_configs(by_config)
    escenarios = sorted({s for c in configs
                         for s in by_config[c].get("solve_rate_by_scenario", {})})
    if not escenarios:
        return
    matriz = [[by_config[c].get("solve_rate_by_scenario", {}).get(s, 0.0)
               for c in configs] for s in escenarios]

    fig, ax = plt.subplots(figsize=(6.5, 5.2))
    im = ax.imshow(matriz, cmap="Greens", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(configs)), labels=configs)
    ax.set_yticks(range(len(escenarios)), labels=escenarios, fontsize=8)
    for i in range(len(escenarios)):
        for j in range(len(configs)):
            ax.text(j, i, f"{matriz[i][j]:.2f}", ha="center", va="center",
                    fontsize=8, color="#111827")
    ax.set_title(f"Tasa de éxito por escenario × config\n"
                 f"({meta.get('provider')}/{meta.get('model')}, repeats={meta.get('repeats')})")
    fig.colorbar(im, ax=ax, label="solve rate", shrink=0.8)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_heatmap.png", dpi=150)
    plt.close(fig)


def grafico_judge(judge_summary: dict, meta: dict) -> None:
    # judge_summary = {"judge_model": ..., "by_config": {...}} (checklist binario).
    judge_model = judge_summary.get("judge_model")
    by_cfg = judge_summary.get("by_config", judge_summary)
    configs = [c for c in ("react", "summarizer", "gate") if c in by_cfg]
    if not configs:
        return
    avgs = [by_cfg[c].get("avg_score") or 0 for c in configs]
    ns = [by_cfg[c]["n"] for c in configs]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(configs, avgs, color=[COLOR.get(c, "#64748b") for c in configs])
    for bar, n in zip(bars, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.03,
                f"{bar.get_height():.2f}\n(n={n})", ha="center", fontsize=8)
    ax.set_ylim(0, 3)
    ax.set_ylabel("Criterios cumplidos (0–3)")
    ax.set_title(f"Dimensión cualitativa (checklist binario)\n"
                 f"agente {meta.get('model')} · judge {judge_model}")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_judge.png", dpi=150)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", default=None, help="Directorio de resultados.")
    args = parser.parse_args()

    results = Path(args.results) if args.results else _latest_results()
    data = json.loads((results / "summary.json").read_text(encoding="utf-8"))
    meta, by_config = data["meta"], data["summary"]["by_config"]

    _DOCS.mkdir(exist_ok=True)
    grafico_latencia(by_config, meta)
    grafico_fallos(by_config, meta)
    grafico_costo(by_config, meta)
    grafico_tools(by_config, meta)
    generados = ["m3_latencia.png", "m3_fallos.png", "m3_costo.png", "m3_tools.png"]
    for fn, nombre in (
        (grafico_latencia_desglosada, "m3_latencia_desglosada.png"),
        (grafico_redundancia, "m3_redundancia.png"),
        (grafico_heatmap, "m3_heatmap.png"),
    ):
        fn(by_config, meta)
        if (_DOCS / nombre).exists():
            generados.append(nombre)

    judge_path = results / "judge_summary.json"
    if judge_path.exists():
        grafico_judge(json.loads(judge_path.read_text(encoding="utf-8")), meta)
        generados.append("m3_judge.png")
    print("Generados:", ", ".join(generados))

    print(f"Fuente: {results}")


if __name__ == "__main__":
    main()
