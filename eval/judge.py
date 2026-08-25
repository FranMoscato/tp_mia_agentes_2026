"""Dimensión cualitativa de la evaluación: LLM-as-judge (M3).

El enunciado pide al menos una dimensión cualitativa vía rúbrica o
LLM-as-judge. La dimensión elegida es **calidad de la trayectoria**: ¿el
agente exploró con método?

Por qué esa dimensión y no "¿resolvió?": si abrió la puerta, ya lo verifica
`check_goal` por código, de forma objetiva. La regla de la clase 8 es **no
usar un judge donde hay verificación programática** — el judge aporta donde
NO la hay: en cómo se comportó el agente en el camino (exploración
sistemática, sin vueltas redundantes), más allá del éxito/fracaso binario.

El judge puntúa la trayectoria del 1 al 5 con una rúbrica explícita, sobre la
traza real de tool-calls (no sobre el output final, que muchas veces no
llega). Para versionar y auditar, guarda la justificación.

Meta-eval (#16): `cohen_kappa` compara las etiquetas del judge contra
etiquetas humanas (del golden set) para medir si el judge es confiable.

Uso:

    python eval/judge.py eval/results/<ts>/cases.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))


# ---------------------------------------------------------------------------
# Rúbrica y schema del veredicto
# ---------------------------------------------------------------------------

RUBRICA_EXPLORACION = """\
Puntuá la CALIDAD DE LA EXPLORACIÓN del 1 al 5 (no si resolvió, eso se mide aparte):
  5 — Metódica: look al entrar, examina antes de tomar, no repite acciones ni
      usa objetos que no tiene; cada acción se apoya en lo observado.
  4 — Mayormente ordenada, con alguna acción redundante o fuera de orden.
  3 — Errática: mezcla exploración con intentos a ciegas; varias redundancias.
  2 — Desordenada: repite acciones, ignora resultados, prueba cosas al azar.
  1 — Sin método: casi no explora, o entra en loop, o "habla" en vez de actuar.\
"""


class TrajectoryVerdict(BaseModel):
    """Veredicto cualitativo sobre una trayectoria."""

    exploracion_metodica: int = Field(ge=1, le=5)
    justificacion: str


JUDGE_SYSTEM_PROMPT = (
    "Sos un evaluador experto de agentes que resuelven salas de escape. "
    "Puntuás la CALIDAD DEL PROCESO de exploración, no si se logró el objetivo "
    "(eso se verifica por código aparte). Sos estricto y te basás solo en la "
    "traza provista. Respondé únicamente con la herramienta final_result."
)

JUDGE_PROMPT_TEMPLATE = """\
Evaluá la siguiente trayectoria de un agente en una sala de escape.

{rubrica}

TRAYECTORIA:
{trace}

Devolvé `exploracion_metodica` (1-5) y una `justificacion` breve basada en la traza.
"""


# ---------------------------------------------------------------------------
# Núcleo puro (testeable sin LLM)
# ---------------------------------------------------------------------------


def format_trace(case: dict[str, Any]) -> str:
    """Renderiza la traza de un caso como transcripción legible para el judge."""
    lines = [
        f"Escenario: {case.get('scenario')} (dificultad {case.get('difficulty')})",
        f"Objetivo cumplido (verificado por código): {case.get('goal_achieved')}",
        "Acciones:",
    ]
    steps = case.get("steps") or []
    if not steps:
        lines.append("  (ninguna tool-call: el agente no actuó)")
    for i, s in enumerate(steps, 1):
        resultado = s.get("error") or s.get("tool_output") or ""
        resultado = str(resultado).replace("\n", " ")[:160]
        lines.append(f"  {i}. {s.get('tool_name')}({s.get('tool_input')}) -> {resultado}")
    if case.get("answer"):
        lines.append(f"Texto final del agente: {str(case['answer'])[:200]}")
    return "\n".join(lines)


def aggregate_scores(judged: list[dict[str, Any]]) -> dict[str, Any]:
    """Promedio y distribución del puntaje de exploración por configuración."""
    out: dict[str, Any] = {}
    for config in sorted({j["config"] for j in judged}):
        sub = [j for j in judged if j["config"] == config]
        scores = [j["verdict"]["exploracion_metodica"] for j in sub if j.get("verdict")]
        out[config] = {
            "n": len(scores),
            "avg_exploracion": round(sum(scores) / len(scores), 2) if scores else None,
            "distribucion": dict(sorted(Counter(scores).items())),
        }
    return out


def cohen_kappa(labels_a: list[Any], labels_b: list[Any]) -> float | None:
    """Kappa de Cohen entre dos series de etiquetas categóricas (meta-eval #16).

    Mide acuerdo corregido por azar entre el judge y un humano. `None` si las
    series están vacías o de distinto largo. Devuelve 1.0 si no hay varianza y
    coinciden (acuerdo perfecto degenerado).
    """
    if not labels_a or len(labels_a) != len(labels_b):
        return None
    n = len(labels_a)
    cats = set(labels_a) | set(labels_b)
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    ca, cb = Counter(labels_a), Counter(labels_b)
    pe = sum((ca[c] / n) * (cb[c] / n) for c in cats)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return round((po - pe) / (1 - pe), 3)


# ---------------------------------------------------------------------------
# Judge contra el LLM real
# ---------------------------------------------------------------------------


def judge_case(case: dict[str, Any], judge_agent: Any) -> dict[str, Any] | None:
    """Puntúa una trayectoria con el judge. `None` si el judge falla."""
    prompt = JUDGE_PROMPT_TEMPLATE.format(
        rubrica=RUBRICA_EXPLORACION, trace=format_trace(case)
    )
    try:
        verdict = judge_agent.structured_call(
            prompt=prompt, schema=TrajectoryVerdict, system=JUDGE_SYSTEM_PROMPT
        )
    except Exception:  # noqa: BLE001 — un caso que el judge no puede puntuar
        return None
    return verdict.model_dump()


def judge_cases(cases: list[dict[str, Any]], module: Any) -> list[dict[str, Any]]:
    """Puntúa todos los casos. Usa un agente 'limpio' como judge LLM."""
    judge_agent = module.build_agent({"register_default_tools": False})
    judged = []
    for c in cases:
        judged.append(
            {
                "scenario": c.get("scenario"),
                "config": c.get("config"),
                "repeat": c.get("repeat"),
                "goal_achieved": c.get("goal_achieved"),
                "verdict": judge_case(c, judge_agent),
            }
        )
    return judged


def main(argv: list[str] | None = None) -> int:
    import importlib

    parser = argparse.ArgumentParser(prog="eval/judge.py")
    parser.add_argument("cases", help="Ruta al cases.jsonl de una corrida.")
    parser.add_argument("--module", default="student_framework")
    args = parser.parse_args(argv)

    cases_path = Path(args.cases)
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    module = importlib.import_module(args.module)
    judged = judge_cases(cases, module)

    out_path = cases_path.parent / "judged.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for j in judged:
            fh.write(json.dumps(j, ensure_ascii=False) + "\n")

    agg = aggregate_scores(judged)
    (cases_path.parent / "judge_summary.json").write_text(
        json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(agg, indent=2, ensure_ascii=False))
    print(f"\nVeredictos en: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
