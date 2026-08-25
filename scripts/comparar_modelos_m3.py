"""Gráficos comparativos cross-modelo/proveedor del informe de M3.

Recorre TODAS las corridas en `eval/results/` (cada una versiona su
`provider`/`model` en el meta), se queda con la corrida más completa por
modelo, y produce comparativas modelo × configuración.

Uso:
    python scripts/comparar_modelos_m3.py

Produce, en `docs/`:
  - m3_cmp_accuracy.png   (accuracy por modelo × config)
  - m3_cmp_latencia.png   (latencia p95 por modelo × config)
  - m3_cmp_judge.png      (calidad de exploración por modelo × config, si hay judge)

Pensado para "correr y comparar": cuando alguien corra con Bedrock, basta
volver a ejecutar este script para que la comparación incluya ese modelo.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt

_REPO = Path(__file__).resolve().parent.parent
_DOCS = _REPO / "docs"
_CONFIGS = ("react", "summarizer", "gate")
# Colores por modelo (se asignan por orden de aparición si hay más).
_PALETA = ["#2563eb", "#ca8a04", "#16a34a", "#db2777", "#0891b2", "#7c3aed"]


def _cargar_corridas() -> dict[str, dict]:
    """Mejor corrida por modelo: {label: {"by_config":..., "judge":...}}."""
    mejor: dict[str, dict] = {}
    for d in sorted((_REPO / "eval" / "results").glob("*/")):
        sj = d / "summary.json"
        if not sj.exists():
            continue
        data = json.loads(sj.read_text(encoding="utf-8"))
        meta = data["meta"]
        summ = data["summary"]
        # Fallback para corridas previas al versionado de provider/model.
        provider = meta.get("provider") or ("bedrock" if meta.get("bedrock_model_id") else None)
        model = meta.get("model") or meta.get("bedrock_model_id")
        if not model or not provider:
            continue  # corrida sin versionar (previa al meta de provider): la ignoramos
        label = f"{provider}/{model}"
        # Nos quedamos con la corrida de más casos por modelo (tie-break: última).
        if label not in mejor or summ["n_cases"] >= mejor[label]["n_cases"]:
            judge_path = d / "judge_summary.json"
            mejor[label] = {
                "n_cases": summ["n_cases"],
                "by_config": summ["by_config"],
                "judge": json.loads(judge_path.read_text(encoding="utf-8"))
                if judge_path.exists() else None,
            }
    return mejor


def _grouped_bar(titulo: str, ylabel: str, valor_fn, archivo: str,
                 corridas: dict[str, dict], ylim=None) -> bool:
    """Barras agrupadas: x=config, un grupo de barras por modelo."""
    modelos = list(corridas)
    series = {}  # modelo -> [valor por config]
    hay_datos = False
    for m in modelos:
        fila = []
        for cfg in _CONFIGS:
            v = valor_fn(corridas[m], cfg)
            fila.append(v if v is not None else 0)
            if v:
                hay_datos = True
        series[m] = fila
    if not hay_datos:
        return False

    x = range(len(_CONFIGS))
    n = len(modelos)
    w = 0.8 / max(n, 1)
    fig, ax = plt.subplots(figsize=(7.5, 4.4))
    for i, m in enumerate(modelos):
        offs = [xi - 0.4 + w / 2 + i * w for xi in x]
        bars = ax.bar(offs, series[m], w, label=m, color=_PALETA[i % len(_PALETA)])
        ax.bar_label(bars, fmt="%.2g", fontsize=7, padding=2)
    ax.set_xticks(list(x))
    ax.set_xticklabels(_CONFIGS)
    ax.set_ylabel(ylabel)
    ax.set_title(titulo)
    if ylim:
        ax.set_ylim(*ylim)
    ax.legend(fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(_DOCS / archivo, dpi=150)
    plt.close(fig)
    return True


def main() -> None:
    corridas = _cargar_corridas()
    if not corridas:
        raise SystemExit("No hay corridas en eval/results/.")

    _DOCS.mkdir(exist_ok=True)
    generados = []

    if _grouped_bar(
        "Accuracy por modelo × configuración", "Accuracy",
        lambda run, cfg: run["by_config"].get(cfg, {}).get("accuracy"),
        "m3_cmp_accuracy.png", corridas, ylim=(0, 1),
    ):
        generados.append("m3_cmp_accuracy.png")

    if _grouped_bar(
        "Latencia p95 por modelo × configuración", "Latencia p95 (s)",
        lambda run, cfg: run["by_config"].get(cfg, {}).get("latency_p95_s"),
        "m3_cmp_latencia.png", corridas,
    ):
        generados.append("m3_cmp_latencia.png")

    if _grouped_bar(
        "Costo en tokens por modelo × configuración", "Tokens promedio por caso",
        lambda run, cfg: (run["by_config"].get(cfg, {}).get("avg_agent_tokens") or 0)
        + (run["by_config"].get(cfg, {}).get("avg_memory_tokens") or 0),
        "m3_cmp_costo.png", corridas,
    ):
        generados.append("m3_cmp_costo.png")

    if any(run["judge"] for run in corridas.values()):
        if _grouped_bar(
            "Calidad de exploración (judge) por modelo × config", "Exploración (1–5)",
            lambda run, cfg: (run["judge"] or {}).get(cfg, {}).get("avg_exploracion"),
            "m3_cmp_judge.png", corridas, ylim=(0, 5),
        ):
            generados.append("m3_cmp_judge.png")

    print(f"Modelos comparados ({len(corridas)}): {', '.join(corridas)}")
    print(f"Generados: {', '.join(generados) or '(ninguno: falta variación de datos)'}")


if __name__ == "__main__":
    main()
