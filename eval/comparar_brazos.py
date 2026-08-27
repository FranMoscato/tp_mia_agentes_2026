"""Contrastes entre brazos de una corrida, estratificados por escenario.

Aplica `eval/stats.py` a los tres experimentos de M3 y reporta, para cada uno,
el test agrupado y el estratificado (CMH) uno al lado del otro, más el efecto
escenario por escenario.

Uso:

    python eval/comparar_brazos.py eval/results/<timestamp>/cases.jsonl

    # varias corridas del mismo modelo, agregadas:
    python eval/comparar_brazos.py eval/results/A/cases.jsonl eval/results/B/cases.jsonl

Salidas: `comparaciones.json` y `comparaciones.md` junto al primer cases.jsonl.
No toca la red: lee JSONL y calcula.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.stats import comparar_brazos

# Los tres experimentos del informe, como (base, comparado, qué aísla).
# El baseline siempre es `react`: es el "OFF" de los tres.
EXPERIMENTOS: list[tuple[str, str, str]] = [
    ("react", "summarizer", "Experimento 1 — resumen de estado on/off"),
    ("react", "gate", "Experimento 2 — gate determinístico on/off"),
    ("react", "react_generico", "Experimento 3 — prompt escape-v1 vs. genérico"),
]


def _cargar(paths: list[Path]) -> list[dict[str, Any]]:
    casos: list[dict[str, Any]] = []
    for p in paths:
        casos.extend(
            json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()
        )
    return casos


def _fmt_p(p: float | None) -> str:
    if p is None:
        return "—"
    return f"{p:.4f}" + (" *" if p < 0.05 else "")


def _render_md(resultados: list[dict[str, Any]], n_casos: int, fuentes: list[str]) -> str:
    out = ["# Contrastes entre brazos (estratificados por escenario)", ""]
    out.append(f"- Casos analizados: **{n_casos}**")
    out.append(f"- Fuentes: {', '.join(f'`{f}`' for f in fuentes)}")
    out.append("")
    out.append(
        "> El test **agrupado** junta todos los casos de un brazo contra los del "
        "otro. El **CMH** estratifica por escenario, que es el diseño real: los "
        "dos brazos corren los mismos escenarios, y el escenario es la fuente "
        "dominante de varianza. `*` marca p < 0.05."
    )
    out.append("")
    out.append("| Experimento | base | comparado | Δ | p agrupado | p CMH | estratos |")
    out.append("|---|---:|---:|---:|---:|---:|---:|")
    for r in resultados:
        if r.get("_vacio"):
            continue
        cmh = r["cmh"]
        estr = f"{len(cmh['estratos_usados'])}/{len(cmh['estratos_usados']) + len(cmh['estratos_descartados'])}"
        out.append(
            f"| {r['_titulo']} | `{r['base']}` {r['base_acc']:.3f} | "
            f"`{r['comparado']}` {r['comp_acc']:.3f} | {r['delta']:+.3f} | "
            f"{_fmt_p(r['p_agrupado'])} | {_fmt_p(cmh['p'])} | {estr} |"
        )
    out.append("")

    for r in resultados:
        if r.get("_vacio"):
            continue
        cmh = r["cmh"]
        out.append(f"## {r['_titulo']}")
        out.append("")
        out.append(
            f"`{r['base']}` {r['base_n']} = {r['base_acc']:.3f} "
            f"IC95% [{r['base_ci'][0]:.3f}, {r['base_ci'][1]:.3f}] · "
            f"`{r['comparado']}` {r['comp_n']} = {r['comp_acc']:.3f} "
            f"IC95% [{r['comp_ci'][0]:.3f}, {r['comp_ci'][1]:.3f}]"
        )
        out.append("")
        if cmh["estratos_descartados"]:
            out.append(
                f"Estratos descartados por no tener varianza (mismo resultado en "
                f"ambos brazos): {', '.join(f'`{e}`' for e in cmh['estratos_descartados'])}. "
                f"No aportan al contraste pero sí inflarían el denominador del test agrupado."
            )
            out.append("")
        out.append("| Escenario | base | comparado | Δ |")
        out.append("|---|---:|---:|---:|")
        for f in r["por_escenario"]:
            out.append(
                f"| `{f['escenario']}` | {f['base']} ({f['base_acc']:.3f}) | "
                f"{f['comp']} ({f['comp_acc']:.3f}) | {f['delta']:+.3f} |"
            )
        out.append("")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    paths = [Path(a) for a in argv]
    faltan = [p for p in paths if not p.exists()]
    if faltan:
        print(f"No existen: {', '.join(str(p) for p in faltan)}")
        return 1

    casos = _cargar(paths)
    configs = {c.get("config") for c in casos}

    resultados = []
    for base, comp, titulo in EXPERIMENTOS:
        if base not in configs or comp not in configs:
            resultados.append({"_titulo": titulo, "_vacio": True,
                               "_motivo": f"falta `{base}` o `{comp}` en los datos"})
            continue
        r = comparar_brazos(casos, base, comp)
        r["_titulo"] = titulo
        resultados.append(r)

    destino = paths[0].parent
    (destino / "comparaciones.json").write_text(
        json.dumps(resultados, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    md = _render_md(resultados, len(casos), [str(p) for p in paths])
    (destino / "comparaciones.md").write_text(md, encoding="utf-8")
    print(md)
    omitidos = [r for r in resultados if r.get("_vacio")]
    if omitidos:
        print("\nOmitidos:")
        for r in omitidos:
            print(f"  - {r['_titulo']}: {r['_motivo']}")
    print(f"\nEscrito en: {destino}/comparaciones.{{json,md}}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
