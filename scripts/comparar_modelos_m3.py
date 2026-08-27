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
# Colores por modelo: paleta categórica validada del skill de dataviz (el
# ORDEN de los slots es el mecanismo de seguridad CVD; no reordenar ni ciclar).
_PALETA = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#4a3aa7"]


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


def _suma_tokens(cfg_data: dict | None) -> float | None:
    """Tokens totales (agente + summarizer) de un brazo, o None si no se corrió.

    Distinguir "no medido" de 0 importa: los brazos que no corrimos no deben
    dibujar barra (ver `_grouped_bar`).
    """
    if not cfg_data:
        return None
    agente = cfg_data.get("avg_agent_tokens")
    memoria = cfg_data.get("avg_memory_tokens")
    if agente is None and memoria is None:
        return None
    return (agente or 0) + (memoria or 0)


def _grouped_bar(titulo: str, ylabel: str, valor_fn, archivo: str,
                 corridas: dict[str, dict], ylim=None) -> bool:
    """Barras agrupadas: x=config, un grupo de barras por modelo."""
    modelos = list(corridas)
    series = {}  # modelo -> [valor por config]  (None = NO MEDIDO)
    hay_datos = False
    for m in modelos:
        fila = []
        for cfg in _CONFIGS:
            v = valor_fn(corridas[m], cfg)
            # None se PRESERVA: un brazo que no corrimos no es lo mismo que un
            # brazo que dio 0. Aplanarlo a 0 hacía que `nova-pro` —corrido solo
            # sobre `react`— apareciera con barra en 0 en `summarizer` y `gate`,
            # y se leyera como que ahí fracasa. Abajo esas barras se omiten.
            fila.append(v)
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
        # Dibujamos solo las posiciones CON dato. Donde no se midió no va barra
        # ni etiqueta: el hueco dice "no medido", un 0 diría "medimos y dio 0".
        pos = [o for o, v in zip(offs, series[m]) if v is not None]
        val = [v for v in series[m] if v is not None]
        bars = ax.bar(pos, val, w, label=m, color=_PALETA[i % len(_PALETA)])
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
        # Devolver None cuando el brazo NO se corrió, en vez de 0: un `or 0` acá
        # aplanaba el "no medido" a un cero que _grouped_bar ya no puede
        # distinguir, y `nova-pro` —corrido solo sobre `react`— salía con barra
        # en 0 en summarizer y gate.
        lambda run, cfg: _suma_tokens(run["by_config"].get(cfg)),
        "m3_cmp_costo.png", corridas,
    ):
        generados.append("m3_cmp_costo.png")

    if any(run["judge"] for run in corridas.values()):
        if _grouped_bar(
            "Calidad de exploración (judge) por modelo × config", "Criterios cumplidos (0–3)",
            lambda run, cfg: ((run["judge"] or {}).get("by_config", {}) or {})
            .get(cfg, {}).get("avg_score"),
            "m3_cmp_judge.png", corridas, ylim=(0, 3),
        ):
            generados.append("m3_cmp_judge.png")

    print(f"Modelos comparados ({len(corridas)}): {', '.join(corridas)}")
    print(f"Generados: {', '.join(generados) or '(ninguno: falta variación de datos)'}")


if __name__ == "__main__":
    main()
