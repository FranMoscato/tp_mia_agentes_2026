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

# Checklist BINARIO (no escala 1-5): la clase recomienda varios sí/no por
# defecto —una escala ordinal se amontona en el medio (tendencia central) y
# cuesta reproducirla; los sí/no son reproducibles y dicen QUÉ falló—. Cada ítem
# es un juicio holístico sobre el trace (no algo que el código ya verifica).
RUBRICA_EXPLORACION = """\
Respondé SÍ/NO a cada criterio de CALIDAD DE LA EXPLORACIÓN (no si resolvió, eso
se verifica por código aparte):
  - exploracion_ordenada: ¿observó (look/examine) antes de actuar, sin saltar a
    ciegas a take/use/go?
  - acciones_apoyadas: ¿cada acción se apoya en algo observado antes (no inventó
    ni adivinó objetos, IDs o salidas)?
  - sin_redundancia_evitable: ¿evitó repetir la misma acción o deshacer trabajo
    sin una razón visible?\
"""


class TrajectoryVerdict(BaseModel):
    """Veredicto cualitativo: checklist binario + justificación."""

    exploracion_ordenada: bool
    acciones_apoyadas: bool
    sin_redundancia_evitable: bool
    justificacion: str


# Criterios binarios, en orden fijo. El "score" derivado es cuántos dan True.
CRITERIOS = ["exploracion_ordenada", "acciones_apoyadas", "sin_redundancia_evitable"]


JUDGE_SYSTEM_PROMPT = (
    "Sos un evaluador experto de agentes que resuelven salas de escape. "
    "Evaluás la CALIDAD DEL PROCESO de exploración con un checklist SÍ/NO, no si "
    "se logró el objetivo (eso se verifica por código aparte). Sos estricto y te "
    "basás solo en la traza provista. Respondé únicamente con la herramienta "
    "final_result."
)

JUDGE_PROMPT_TEMPLATE = """\
Evaluá la siguiente trayectoria de un agente en una sala de escape.

{rubrica}

TRAYECTORIA:
{trace}

Devolvé cada criterio como booleano (true/false) y una `justificacion` breve
basada en la traza.
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
    """Por config: tasa de SÍ por criterio + score derivado (0-3) promedio.

    El score de un caso es cuántos criterios dan True (0 a 3). Reportamos el
    promedio y la **tasa de SÍ por criterio**, que es diagnóstica: dice *qué*
    falló, no solo cuánto.
    """
    out: dict[str, Any] = {}
    for config in sorted({j["config"] for j in judged}):
        sub = [j for j in judged if j["config"] == config and j.get("verdict")]
        n = len(sub)
        if not n:
            out[config] = {"n": 0, "avg_score": None, "yes_rate": {}}
            continue
        yes_rate = {
            crit: round(sum(1 for j in sub if j["verdict"].get(crit)) / n, 2)
            for crit in CRITERIOS
        }
        scores = [sum(1 for crit in CRITERIOS if j["verdict"].get(crit)) for j in sub]
        out[config] = {
            "n": n,
            "avg_score": round(sum(scores) / n, 2),  # 0-3
            "yes_rate": yes_rate,
        }
    return out


def reference_verdict(case: dict[str, Any]) -> dict[str, bool]:
    """Referencia **determinística** de los 3 criterios, desde la traza.

    Para la meta-eval (kappa) necesitamos un baseline INDEPENDIENTE del judge-LLM
    y no circular. En vez de etiquetar "a ojo" (otro juicio subjetivo), derivamos
    los criterios de propiedades **objetivas** de la traza —la regla de la clase de
    empujar el juicio a código donde se pueda—. No reemplaza a un humano; es un
    proxy reproducible y auditable contra el cual medir si el judge es confiable.

    Reglas:
      - exploracion_ordenada: no saltó a `take/use/go` antes de observar, Y hizo
        exploración sustantiva (al menos un `examine`, o ≥2 `look`) —un único
        `look` y abandonar no es exploración ordenada—.
      - acciones_apoyadas: ninguna tool-call falló (`tool_error_count == 0`); si
        el agente hubiera inventado un ID/salida, la tool habría devuelto error.
      - sin_redundancia_evitable: sin repeticiones consecutivas
        (`max_consecutive_repeats <= 1`).
    """
    tools = [s.get("tool_name") for s in (case.get("steps") or [])]
    idx_obs = next((i for i, t in enumerate(tools) if t in ("look", "examine")), None)
    idx_act = next((i for i, t in enumerate(tools) if t in ("take", "use", "go")), None)
    no_ciego = idx_act is None or (idx_obs is not None and idx_obs < idx_act)
    sustantiva = ("examine" in tools) or (tools.count("look") >= 2)
    return {
        "exploracion_ordenada": bool(no_ciego and sustantiva),
        "acciones_apoyadas": (case.get("tool_error_count") or 0) == 0,
        "sin_redundancia_evitable": (case.get("max_consecutive_repeats") or 0) <= 1,
    }


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


def judge_cases(
    cases: list[dict[str, Any]], module: Any, judge_model: str | None = None
) -> list[dict[str, Any]]:
    """Puntúa todos los casos con un judge 'limpio'.

    `judge_model` fuerza un modelo **distinto del agente** (evita self-preference;
    idealmente más capaz). Sin él, usa el proveedor del entorno.
    """
    config: dict[str, Any] = {"register_default_tools": False}
    if judge_model:
        from mia_agents.llm_client import LLMClient, OllamaProvider

        config["llm_client"] = LLMClient(OllamaProvider(model=judge_model))
    judge_agent = module.build_agent(config)
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
    parser.add_argument(
        "--judge-model", default=None,
        help="Modelo del judge (Ollama). DEBE ser distinto del agente evaluado.",
    )
    args = parser.parse_args(argv)

    cases_path = Path(args.cases)
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    module = importlib.import_module(args.module)
    judged = judge_cases(cases, module, judge_model=args.judge_model)

    out_path = cases_path.parent / "judged.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for j in judged:
            fh.write(json.dumps(j, ensure_ascii=False) + "\n")

    agg = {"judge_model": args.judge_model, "by_config": aggregate_scores(judged)}
    (cases_path.parent / "judge_summary.json").write_text(
        json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(agg, indent=2, ensure_ascii=False))
    print(f"\nVeredictos en: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
