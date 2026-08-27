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

# Checklist BINARIO, UN CRITERIO POR LLAMADA. La clase (Evals II, 4.4) es
# explícita: "un criterio por llamada al judge; seis veredictos en una sola
# llamada los degradan a todos". Cada criterio se juzga por separado, con
# few-shot de casos límite y RAZONANDO ANTES de decidir (CoT auditable). Sigue
# siendo binario (no escala 1-5: se amontona en el medio y no se reproduce).


class CriterionVerdict(BaseModel):
    """Veredicto de UN criterio: primero el razonamiento (CoT), después el bool."""

    razonamiento: str  # se completa PRIMERO: mejora consistencia y es auditable
    cumple: bool       # el veredicto binario, recién después de razonar


# Criterios binarios, en orden fijo. El "score" derivado es cuántos dan True.
CRITERIOS = ["exploracion_ordenada", "acciones_apoyadas", "sin_redundancia_evitable"]

# Por criterio: la pregunta sí/no + few-shot etiquetado. Los ejemplos son
# ILUSTRATIVOS (no salen del dataset evaluado, para no filtrar) y definen
# CONDUCTA, no palabras. La clase: "few-shot con casos límite, incluidos los que
# el judge falló" — el judge también tiene su loop.
CRITERIOS_SPEC: dict[str, dict[str, Any]] = {
    "exploracion_ordenada": {
        "pregunta": (
            "¿El agente observó (look/examine) antes de actuar, sin saltar a "
            "ciegas a take/use/go, y con exploración SUSTANTIVA (no un único look "
            "y abandonar)?"
        ),
        "ejemplos": [
            ("look -> examine(escritorio) -> take(llave_oro)", True,
             "observó y examinó antes de tomar: exploración ordenada."),
            ("take(llave_oro)   [primera acción, sin look/examine previo]", False,
             "actuó a ciegas: tomó sin observar primero."),
            ("look   [y después solo texto, abandona]", False,
             "un único look y se rinde: no hay exploración sustantiva."),
        ],
    },
    "acciones_apoyadas": {
        "pregunta": (
            "¿Cada acción (take/use/go) se apoya en algo REALMENTE observado antes "
            "en la traza (no inventó objetos, IDs ni salidas)?"
        ),
        "ejemplos": [
            ("look revela [id: cofre] -> use(llave, cofre)", True,
             "usó un id que apareció en un resultado previo."),
            ("use(llave, puerta) -> ERROR: no tenés 'llave' en el inventario", False,
             "usó algo que no poseía: la tool devolvió error, acción no apoyada."),
            ("go(norte) -> ERROR: no existe la salida 'norte'", False,
             "inventó una salida que ningún look devolvió."),
        ],
    },
    "sin_redundancia_evitable": {
        "pregunta": (
            "¿Evitó repetir la misma acción con los mismos argumentos, o deshacer "
            "trabajo, sin una razón visible?"
        ),
        "ejemplos": [
            ("look -> examine(caja) -> take(item)", True,
             "sin repeticiones: cada acción avanza."),
            ("examine(caja) -> examine(caja) -> examine(caja)", False,
             "repite la misma acción sin que cambie nada: redundancia evitable."),
        ],
    },
}

JUDGE_SYSTEM_PROMPT = (
    "Sos un evaluador experto de agentes que resuelven salas de escape. Evaluás la "
    "CALIDAD DEL PROCESO de exploración, no si se logró el objetivo (eso se "
    "verifica por código aparte). Juzgás UN SOLO criterio por vez. Primero razonás "
    "sobre la traza y recién después emitís el booleano. Sos estricto y te basás "
    "solo en la traza provista. Respondé únicamente con la herramienta final_result."
)

_CRITERION_PROMPT = """\
Juzgá UN solo criterio de calidad de la exploración de un agente en una sala de escape.

CRITERIO ({nombre}): {pregunta}

Ejemplos etiquetados (definen conducta, no palabras):
{ejemplos}

TRAYECTORIA A EVALUAR:
{trace}

Primero completá `razonamiento` (2 oraciones, basadas en la traza) y recién
después `cumple` (true/false) para ESTE criterio únicamente.
"""


def _ejemplos_texto(crit: str) -> str:
    """Formatea el few-shot de un criterio para el prompt."""
    lines = []
    for traza, cumple, motivo in CRITERIOS_SPEC[crit]["ejemplos"]:
        lines.append(f"  - Traza: {traza}\n    cumple={str(cumple).lower()} — {motivo}")
    return "\n".join(lines)


# --- Modo single-call (default) --------------------------------------------
# La clase recomienda "un criterio por llamada", pero eso TRIPLICA las llamadas
# y, con un judge local débil (`llama3.2`), colapsa la cobertura (ver §3.4 del
# informe: pedirle razonar-antes-de-decidir lo hace responder en PROSA en vez de
# llamar la tool —el mismo fallo que el judge debería detectar—). Por eso el
# modo por defecto puntúa los 3 criterios en UNA llamada (cobertura ~96%), y el
# modo per-criterio queda como opción (`--per-criterion`) para reproducir el
# hallazgo. Ambos son binarios (no escala 1-5).


class TrajectoryVerdict(BaseModel):
    """Veredicto single-call: los 3 criterios binarios + justificación."""

    exploracion_ordenada: bool
    acciones_apoyadas: bool
    sin_redundancia_evitable: bool
    justificacion: str


_RUBRICA_SINGLE = "\n".join(
    f"  - {crit}: {CRITERIOS_SPEC[crit]['pregunta']}" for crit in CRITERIOS
)

JUDGE_SYSTEM_PROMPT_SINGLE = (
    "Sos un evaluador experto de agentes que resuelven salas de escape. Evaluás "
    "la CALIDAD DEL PROCESO de exploración con un checklist SÍ/NO, no si se logró "
    "el objetivo (eso se verifica por código aparte). Sos estricto y te basás solo "
    "en la traza. Respondé únicamente con la herramienta final_result."
)

_SINGLE_PROMPT = """\
Evaluá la trayectoria de un agente en una sala de escape con este checklist SÍ/NO
(no si resolvió, eso se verifica por código aparte):
{rubrica}

TRAYECTORIA:
{trace}

Devolvé cada criterio como booleano (true/false) y una `justificacion` breve.
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
    steps = case.get("steps") or []
    tools = [s.get("tool_name") for s in steps]
    idx_obs = next((i for i, t in enumerate(tools) if t in ("look", "examine")), None)
    idx_act = next((i for i, t in enumerate(tools) if t in ("take", "use", "go")), None)
    no_ciego = idx_act is None or (idx_obs is not None and idx_obs < idx_act)
    sustantiva = ("examine" in tools) or (tools.count("look") >= 2)
    return {
        "exploracion_ordenada": bool(no_ciego and sustantiva),
        "acciones_apoyadas": _acciones_apoyadas(case, steps),
        "sin_redundancia_evitable": (case.get("max_consecutive_repeats") or 0) <= 1,
    }


def _args_de(step: dict[str, Any]) -> dict[str, Any]:
    """Argumentos de un step, tolerante al formato (string JSON o dict)."""
    crudo = step.get("tool_input")
    if isinstance(crudo, dict):
        return crudo
    try:
        parseado = json.loads(crudo or "{}")
        return parseado if isinstance(parseado, dict) else {}
    except (TypeError, ValueError):
        return {}


def _acciones_apoyadas(case: dict[str, Any], steps: list[dict[str, Any]]) -> bool:
    """¿Cada acción se apoya en lo que el agente efectivamente consiguió?

    Dos condiciones:
      1. Ninguna tool-call falló (`tool_error_count == 0`).
      2. Todo `use(item=X)` viene después de un `take(item=X)` **exitoso**.

    La condición 2 es el endurecimiento que faltaba. Con solo la 1, la
    referencia decía "sí" en el **96 %** de los casos —los modelos capaces casi
    no producen tool-errors— y un criterio que casi nunca dice "no" **no puede
    discriminar**: la kappa contra él colapsa a ~0 aunque el judge acierte el
    73 % de las veces (la paradoja de kappa, §3.4). Con la condición 2 el "sí"
    baja a **0.75** y la meta-eval vuelve a ser informativa.

    Por qué esta condición y no otra: es exactamente la garantía que el gate
    impone por código (§4.2), así que es una propiedad del dominio y no un
    umbral arbitrario elegido para mover el número.
    """
    if (case.get("tool_error_count") or 0) != 0:
        return False
    tomados: set[Any] = set()
    for step in steps:
        args = _args_de(step)
        nombre = step.get("tool_name")
        if nombre == "take" and not step.get("error"):
            tomados.add(args.get("item"))
        elif nombre == "use" and args.get("item") not in tomados:
            return False
    return True


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


def _judge_case_single(case: dict[str, Any], judge_agent: Any) -> dict[str, Any] | None:
    """Single-call: los 3 criterios en UNA llamada (default, ~96% de cobertura)."""
    prompt = _SINGLE_PROMPT.format(rubrica=_RUBRICA_SINGLE, trace=format_trace(case))
    try:
        v = judge_agent.structured_call(
            prompt=prompt, schema=TrajectoryVerdict, system=JUDGE_SYSTEM_PROMPT_SINGLE
        )
    except Exception:  # noqa: BLE001 — un caso que el judge no puede puntuar
        return None
    return v.model_dump()


def _judge_case_per_criterion(case: dict[str, Any], judge_agent: Any) -> dict[str, Any] | None:
    """Una llamada por criterio (regla 4.4 de la clase). Con un judge local débil
    la cobertura COLAPSA (el prompt de razonar-antes-de-decidir lo hace responder
    en prosa; ver §3.4). Reintenta cada criterio 2 veces; devuelve `None` solo si
    ninguno se pudo puntuar.
    """
    trace = format_trace(case)
    verdict: dict[str, Any] = {}
    razones: list[str] = []
    obtenidos = 0
    for crit in CRITERIOS:
        spec = CRITERIOS_SPEC[crit]
        prompt = _CRITERION_PROMPT.format(
            nombre=crit, pregunta=spec["pregunta"],
            ejemplos=_ejemplos_texto(crit), trace=trace,
        )
        verdict[crit] = None
        for _ in range(2):
            try:
                r = judge_agent.structured_call(
                    prompt=prompt, schema=CriterionVerdict, system=JUDGE_SYSTEM_PROMPT
                )
                verdict[crit] = bool(r.cumple)
                razones.append(f"{crit}: {r.razonamiento}")
                obtenidos += 1
                break
            except Exception:  # noqa: BLE001 — reintentamos; si persiste queda None
                continue
    if obtenidos == 0:
        return None
    verdict["justificacion"] = " | ".join(razones)
    return verdict


def judge_case(
    case: dict[str, Any], judge_agent: Any, per_criterion: bool = False
) -> dict[str, Any] | None:
    """Puntúa una trayectoria. `per_criterion=True` activa el modo 4.4 (una
    llamada por criterio); por defecto usa single-call (más robusto)."""
    if per_criterion:
        return _judge_case_per_criterion(case, judge_agent)
    return _judge_case_single(case, judge_agent)


def judge_cases(
    cases: list[dict[str, Any]], module: Any, judge_model: str | None = None,
    per_criterion: bool = False, judge_provider: str = "ollama",
) -> list[dict[str, Any]]:
    """Puntúa todos los casos con un judge 'limpio'.

    `judge_model` fuerza un modelo **distinto del agente** (evita self-preference;
    idealmente más capaz). `judge_provider` elige el proveedor de ese judge
    (`ollama` u `bedrock`), de modo que se pueda correr el próximo paso #1 del
    informe —un judge **fuerte** en Bedrock (`nova-pro` juzgando a `nova-lite`)—.
    Sin `judge_model`, usa el proveedor del entorno (mismo modelo que el agente,
    NO recomendado: self-preference). `per_criterion` activa el modo 4.4.
    """
    config: dict[str, Any] = {"register_default_tools": False}
    if judge_model:
        from mia_agents.llm_client import LLMClient, BedrockProvider, OllamaProvider

        if judge_provider == "bedrock":
            provider = BedrockProvider(model=judge_model)
        else:
            provider = OllamaProvider(model=judge_model)
        config["llm_client"] = LLMClient(provider)
    judge_agent = module.build_agent(config)
    judged = []
    for c in cases:
        judged.append(
            {
                "scenario": c.get("scenario"),
                "config": c.get("config"),
                "repeat": c.get("repeat"),
                "goal_achieved": c.get("goal_achieved"),
                "verdict": judge_case(c, judge_agent, per_criterion=per_criterion),
            }
        )
    return judged


def main(argv: list[str] | None = None) -> int:
    #  al entorno: el enunciado pide reproducibilidad sin pasos
    # manuales, y boto3 lee del entorno, no del archivo.
    from eval.run import cargar_dotenv
    cargar_dotenv()
    import importlib

    parser = argparse.ArgumentParser(prog="eval/judge.py")
    parser.add_argument("cases", help="Ruta al cases.jsonl de una corrida.")
    parser.add_argument("--module", default="student_framework")
    parser.add_argument(
        "--judge-model", default=None,
        help="Modelo del judge. DEBE ser distinto del agente evaluado. "
             "Ej: llama3.2 (ollama) o us.amazon.nova-pro-v1:0 (bedrock).",
    )
    parser.add_argument(
        "--judge-provider", default="ollama", choices=["ollama", "bedrock"],
        help="Proveedor del judge. Usá 'bedrock' con --judge-model nova-pro para "
             "el judge fuerte del próximo paso #1 (nova-pro juzgando a nova-lite).",
    )
    parser.add_argument(
        "--per-criterion", action="store_true",
        help="Modo 4.4 de la clase: una llamada por criterio. OJO: con judge "
             "local débil colapsa la cobertura (ver §3.4). Default: single-call.",
    )
    args = parser.parse_args(argv)

    cases_path = Path(args.cases)
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    module = importlib.import_module(args.module)
    judged = judge_cases(cases, module, judge_model=args.judge_model,
                         per_criterion=args.per_criterion,
                         judge_provider=args.judge_provider)

    out_path = cases_path.parent / "judged.jsonl"
    with out_path.open("w", encoding="utf-8") as fh:
        for j in judged:
            fh.write(json.dumps(j, ensure_ascii=False) + "\n")

    # Versionamos el judge (la clase: "el judge también se versiona:
    # prompt+few-shot+modelo"). Sin esto, un veredicto no dice qué judge lo produjo.
    agg = {
        "judge_model": args.judge_model,
        "judge_provider": args.judge_provider if args.judge_model else "env",
        "mode": "per_criterion" if args.per_criterion else "single_call",
        "by_config": aggregate_scores(judged),
    }
    (cases_path.parent / "judge_summary.json").write_text(
        json.dumps(agg, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(agg, indent=2, ensure_ascii=False))
    print(f"\nVeredictos en: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
