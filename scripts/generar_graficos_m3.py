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

# Paleta por configuración (consistente con los diagramas de M1/M2).
COLOR = {"react": "#2563eb", "summarizer": "#ca8a04", "gate": "#16a34a"}
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
               color=COLOR_FALLO.get(cat, "#94a3b8"))
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax.set_ylabel("Casos")
    ax.set_title(f"Modos de fallo por configuración\n({meta.get('provider')}/{meta.get('model')}, "
                 f"repeats={meta.get('repeats')})")
    ax.legend(fontsize=8, loc="upper right")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / "m3_fallos.png", dpi=150)
    plt.close(fig)


def grafico_judge(judge_summary: dict, meta: dict) -> None:
    configs = [c for c in ("react", "summarizer", "gate") if c in judge_summary]
    if not configs:
        return
    avgs = [judge_summary[c]["avg_exploracion"] or 0 for c in configs]
    ns = [judge_summary[c]["n"] for c in configs]

    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(configs, avgs, color=[COLOR.get(c, "#64748b") for c in configs])
    for bar, n in zip(bars, ns):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.05,
                f"{bar.get_height():.1f}\n(n={n})", ha="center", fontsize=8)
    ax.set_ylim(0, 5)
    ax.set_ylabel("Calidad de exploración (1–5)")
    ax.set_title(f"Dimensión cualitativa (LLM-as-judge)\n({meta.get('provider')}/{meta.get('model')})")
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

    judge_path = results / "judge_summary.json"
    if judge_path.exists():
        grafico_judge(json.loads(judge_path.read_text(encoding="utf-8")), meta)
        print("Generados: m3_latencia.png, m3_fallos.png, m3_judge.png")
    else:
        print("Generados: m3_latencia.png, m3_fallos.png (sin judge_summary.json)")

    print(f"Fuente: {results}")


if __name__ == "__main__":
    main()
