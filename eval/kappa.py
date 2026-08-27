"""Meta-eval del judge: kappa de Cohen entre el judge-LLM y una referencia.

El enunciado pide una meta-evaluación de la dimensión cualitativa. Medimos si el
**judge-LLM** (checklist binario de `eval/judge.py`) coincide con una
**referencia determinística** (`reference_verdict`, derivada de propiedades
objetivas de la traza) usando la **kappa de Cohen** por criterio. Un kappa alto
= el judge es confiable; uno ≈0 o negativo = no acuerda mejor que el azar y no
hay que confiar en sus puntajes.

Uso:
    # 1) correr el judge sobre las trazas (deja judged.jsonl)
    python eval/judge.py eval/golden/cases.jsonl --judge-model llama3.2
    # 2) computar la kappa contra la referencia
    python eval/kappa.py eval/golden/cases.jsonl

Escribe, junto a las trazas:
  - labels.jsonl        (la referencia determinística, versionable y auditable)
  - kappa_summary.json  (kappa por criterio + tasas de SÍ de cada lado)
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_JUDGE = Path(__file__).resolve().parent / "judge.py"
_spec = importlib.util.spec_from_file_location("eval_judge", _JUDGE)
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)


def _cargar(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv: list[str] | None = None) -> int:
    #  al entorno: el enunciado pide reproducibilidad sin pasos
    # manuales, y boto3 lee del entorno, no del archivo.
    from eval.run import cargar_dotenv
    cargar_dotenv()
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cases_path = Path(argv[0])
    carpeta = cases_path.parent
    cases = _cargar(cases_path)

    judged_path = carpeta / "judged.jsonl"
    if not judged_path.exists():
        print(f"Falta {judged_path}. Corré primero eval/judge.py sobre las trazas.")
        return 1
    judged = _cargar(judged_path)

    # Índice por (scenario, config, repeat) para alinear judge vs referencia.
    def clave(c: dict) -> tuple:
        return (c.get("scenario"), c.get("config"), c.get("repeat"))

    judge_por_clave = {clave(j): (j.get("verdict") or {}) for j in judged}

    # Referencia determinística, versionada como labels.jsonl.
    ref_rows = []
    for c in cases:
        ref_rows.append({
            "scenario": c.get("scenario"), "config": c.get("config"),
            "repeat": c.get("repeat"), "verdict": judge.reference_verdict(c),
        })
    (carpeta / "labels.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in ref_rows) + "\n",
        encoding="utf-8",
    )

    # Kappa por criterio (alineando por clave; ignora casos sin veredicto del judge).
    resumen: dict = {"n": 0, "by_criterion": {}}
    pares: dict[str, tuple[list[int], list[int]]] = {c: ([], []) for c in judge.CRITERIOS}
    for r in ref_rows:
        jv = judge_por_clave.get(clave(r))
        if not jv:
            continue
        resumen["n"] += 1
        for crit in judge.CRITERIOS:
            pares[crit][0].append(int(bool(r["verdict"].get(crit))))
            pares[crit][1].append(int(bool(jv.get(crit))))

    for crit, (ref_l, jud_l) in pares.items():
        k = judge.cohen_kappa(ref_l, jud_l)
        resumen["by_criterion"][crit] = {
            "kappa": k,
            "ref_yes_rate": round(sum(ref_l) / len(ref_l), 2) if ref_l else None,
            "judge_yes_rate": round(sum(jud_l) / len(jud_l), 2) if jud_l else None,
        }

    (carpeta / "kappa_summary.json").write_text(
        json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(resumen, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
