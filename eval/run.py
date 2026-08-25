"""Infraestructura de evaluación de M3 (reproducible).

Corre el agente sobre el dataset de salas de escape, captura por caso las
entradas/salidas/llamadas a herramientas/errores, y produce un informe
resumen con métricas y desglose por categoría de fallo.

Uso:

    # Todo el dataset, ambos brazos del experimento (react vs summarizer):
    python eval/run.py

    # Un subconjunto y una sola config:
    python eval/run.py --scenarios study-with-key,color-locks --configs react

    # Repetir cada caso N veces (para pass@k / varianza):
    python eval/run.py --repeats 3

Requiere un proveedor LLM configurado (igual que `mia_world.cli`, por
defecto Bedrock con `BEDROCK_MODEL_ID`). Las funciones de agregación y
categorización son puras y están cubiertas por `tests/test_eval_harness.py`
(no requieren API).

Salidas (en `eval/results/<timestamp>/`):
  - `cases.jsonl`  — un objeto por corrida, con la traza completa.
  - `summary.json` — métricas agregadas.
  - `summary.md`   — el mismo resumen, legible para el informe.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

# Permite `python eval/run.py` (sys.path[0] es eval/): agregamos la raíz del
# repo para poder importar `mia_world` y `eval.optimal`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.optimal import optimal_for_path
from mia_world.goals import check_goal
from mia_world.scenarios import load_scenario
from mia_world.tools import make_world_tools


_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCENARIOS_DIR = _REPO_ROOT / "scenarios"
DEFAULT_RESULTS_DIR = _REPO_ROOT / "eval" / "results"

# El óptimo de tool-calls por escenario NO se hardcodea: se deriva por
# búsqueda (BFS sobre el grafo de estados) en `eval/optimal.py`, cacheado por
# escenario. Sirve para la métrica "calls-to-solve vs. óptimo": cuánto se aleja
# el agente del camino ideal.

# Brazos de experimento. Cada uno es un `config` extra para `build_agent`.
# El experimento #1 de M3 (resumen on/off) sale de comparar "react" vs
# "summarizer". Agregá acá otras variantes (ventana, max_iterations, etc.).
CONFIGS: dict[str, dict[str, Any]] = {
    "react": {"use_summarizer": False},
    "summarizer": {"use_summarizer": True},
}

# Tope de iteraciones para el eval. El default del agente (20) no alcanza para
# los escenarios extreme (vault-combination óptimo = 21); damos holgura.
DEFAULT_MAX_ITERATIONS = 30


# ---------------------------------------------------------------------------
# Núcleo puro (testeable sin LLM): categorización y agregación
# ---------------------------------------------------------------------------


# Cuántas tool-calls idénticas CONSECUTIVAS (misma tool + mismos argumentos)
# cuentan como loop. Repetir `look` es legítimo en los escenarios multi-sala
# —va intercalado con `go`—, por eso exigimos que sean consecutivas y no un
# simple conteo global.
LOOP_THRESHOLD = 3


def repeticiones_consecutivas(steps: list[dict[str, Any]]) -> int:
    """Racha más larga de tool-calls idénticas seguidas (tool + argumentos).

    Es la señal de loop de la clase 7: "repetición de la firma tool +
    argumentos". Se calcula sobre el trace, que es donde el modo de fallo es
    visible — una eval de output final no lo ve, porque el caso nunca llega a
    producir output.
    """
    mejor = actual = 0
    anterior = None
    for step in steps:
        firma = (step.get("tool_name"), str(step.get("tool_input")))
        actual = actual + 1 if firma == anterior else 1
        anterior = firma
        mejor = max(mejor, actual)
    return mejor


def categorize(case: dict[str, Any], max_iterations: int) -> str:
    """Clasifica el resultado de una corrida en un modo de fallo (o éxito).

    Categorías:
      - success              — se abrió la puerta (goal cumplido).
      - crash                — la corrida lanzó una excepción no controlada.
      - loop_detected        — repitió la misma tool-call en círculos.
      - exhausted_iterations — agotó el tope de iteraciones sin lograr el goal.
      - tool_errors          — terminó sin goal y hubo errores de herramientas.
      - wrong_path           — terminó "tranquilo" sin goal (razonó mal el camino).

    `loop_detected` va ANTES que `exhausted_iterations` a propósito: una
    corrida en loop casi siempre agota también las iteraciones, y el loop es
    la causa mientras que agotar el tope es la consecuencia.

    El tope se compara contra `llm_calls`, no contra `tool_calls`: el bucle
    de `run()` limita LLAMADAS AL LLM, y un `assistant` puede pedir varias
    tools en una sola respuesta. Comparar tool-calls dejaba la categoría
    inalcanzable (con una tool por respuesta, `tool_calls` nunca llega al
    tope).
    """
    if case["goal_achieved"]:
        return "success"
    if case.get("crashed"):
        return "crash"
    if repeticiones_consecutivas(case.get("steps") or []) >= LOOP_THRESHOLD:
        return "loop_detected"
    if case.get("llm_calls", 0) >= max_iterations:
        return "exhausted_iterations"
    if case["tool_error_count"] > 0:
        return "tool_errors"
    return "wrong_path"


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def summarize(cases: list[dict[str, Any]], max_iterations: int) -> dict[str, Any]:
    """Agrega las corridas en métricas por config, por dificultad y globales."""
    summary: dict[str, Any] = {"n_cases": len(cases), "by_config": {}}

    configs = sorted({c["config"] for c in cases})
    for config in configs:
        sub = [c for c in cases if c["config"] == config]
        n = len(sub)
        exitosos = [c for c in sub if c["goal_achieved"]]

        # calls-to-solve vs. óptimo: solo sobre los casos resueltos (en los no
        # resueltos el número de calls no es comparable con el óptimo).
        overhead = [
            c["tool_calls"] / c["optimal_calls"]
            for c in exitosos
            if c.get("optimal_calls")
        ]

        # Desglose de categorías de fallo.
        cats: dict[str, int] = {}
        for c in sub:
            cat = categorize(c, max_iterations)
            cats[cat] = cats.get(cat, 0) + 1

        # Accuracy por dificultad.
        by_diff: dict[str, dict[str, Any]] = {}
        for diff in sorted({c["difficulty"] for c in sub}):
            d = [c for c in sub if c["difficulty"] == diff]
            by_diff[diff] = {
                "n": len(d),
                "solved": sum(1 for c in d if c["goal_achieved"]),
                "accuracy": round(sum(c["goal_achieved"] for c in d) / len(d), 3),
            }

        summary["by_config"][config] = {
            "n": n,
            "solved": len(exitosos),
            "accuracy": round(len(exitosos) / n, 3) if n else None,
            "avg_calls_overhead_vs_optimal": _mean(overhead),
            "avg_tool_calls": _mean([c["tool_calls"] for c in sub]),
            "avg_latency_s": _mean([c["latency_s"] for c in sub]),
            "avg_agent_tokens": _mean(
                [c["agent_input_tokens"] + c["agent_output_tokens"] for c in sub]
            ),
            "avg_memory_tokens": _mean(
                [c["memory_input_tokens"] + c["memory_output_tokens"] for c in sub]
            ),
            "failure_breakdown": cats,
            "by_difficulty": by_diff,
        }

    return summary


def report_md(summary: dict[str, Any], meta: dict[str, Any]) -> str:
    """Renderiza el resumen a Markdown para pegar en el informe."""
    lines: list[str] = []
    lines.append("# Evaluación M3 — resumen")
    lines.append("")
    lines.append(f"- Fecha: {meta['timestamp']}")
    lines.append(f"- Módulo del agente: `{meta['module']}`")
    lines.append(f"- max_iterations: {meta['max_iterations']} · repeats: {meta['repeats']}")
    lines.append(f"- Casos totales: {summary['n_cases']}")
    lines.append("")

    lines.append("## Métricas por configuración")
    lines.append("")
    header = (
        "| Config | Accuracy | Resueltos | Overhead vs óptimo | "
        "Tokens agente | Tokens resumen | Latencia (s) |"
    )
    lines.append(header)
    lines.append("|---|---:|---:|---:|---:|---:|---:|")
    for config, m in summary["by_config"].items():
        # El overhead solo existe si hubo casos resueltos; sin eso, "—".
        overhead = m["avg_calls_overhead_vs_optimal"]
        overhead_txt = f"{overhead}x" if overhead is not None else "—"
        lines.append(
            f"| {config} | {m['accuracy']} | {m['solved']}/{m['n']} | "
            f"{overhead_txt} | {m['avg_agent_tokens']} | "
            f"{m['avg_memory_tokens']} | {m['avg_latency_s']} |"
        )
    lines.append("")

    for config, m in summary["by_config"].items():
        lines.append(f"### {config}")
        lines.append("")
        lines.append("**Accuracy por dificultad:**")
        lines.append("")
        lines.append("| Dificultad | Resueltos | Accuracy |")
        lines.append("|---|---:|---:|")
        for diff, d in m["by_difficulty"].items():
            lines.append(f"| {diff} | {d['solved']}/{d['n']} | {d['accuracy']} |")
        lines.append("")
        lines.append("**Modos de fallo:**")
        lines.append("")
        for cat, count in sorted(m["failure_breakdown"].items(), key=lambda kv: -kv[1]):
            lines.append(f"- `{cat}`: {count}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Corrida contra el LLM real
# ---------------------------------------------------------------------------


def run_one(
    scenario_path: Path,
    config_name: str,
    config: dict[str, Any],
    max_iterations: int,
    module: Any,
    repeat: int,
    optimal_calls: int | None,
) -> dict[str, Any]:
    """Corre un escenario con una config y devuelve el caso capturado.

    Recarga el escenario (mundo prístino) en cada corrida para no filtrar
    estado entre modos/repeticiones. `optimal_calls` es el óptimo derivado por
    búsqueda (ver `eval/optimal.py`), computado una vez por escenario.
    """
    scenario = load_scenario(scenario_path)
    world = scenario.initial_world

    build_config: dict[str, Any] = {
        "register_default_tools": False,
        "max_iterations": max_iterations,
        **config,
    }
    # Inyectamos el system prompt de la sala de escape (el default del agente es
    # genérico). Si el módulo no lo expone, el config no lo fuerza.
    escape_prompt = getattr(module, "ESCAPE_ROOM_SYSTEM_PROMPT", None)
    if escape_prompt is not None and "system_prompt" not in build_config:
        build_config["system_prompt"] = escape_prompt

    agent = module.build_agent(build_config)
    for fn, schema in make_world_tools(world):
        agent.register_tool(fn, schema)

    crashed = False
    error_repr = None
    t0 = time.perf_counter()
    try:
        result = agent.run(scenario.user_message)
    except Exception as exc:  # noqa: BLE001 — queremos registrar cualquier fallo
        crashed = True
        error_repr = repr(exc)
        result = None
    latency = round(time.perf_counter() - t0, 3)

    achieved, reason = check_goal(world, scenario.goal)

    steps = [asdict(s) for s in result.steps] if result else []
    tool_errors = [s for s in steps if s.get("error")]

    return {
        "scenario": scenario.id,
        "difficulty": scenario.difficulty,
        "config": config_name,
        "repeat": repeat,
        "optimal_calls": optimal_calls,
        "goal_achieved": bool(achieved),
        "goal_reason": reason,
        "crashed": crashed,
        "error": error_repr,
        "answer": result.answer if result else None,
        "tool_calls": len(steps),
        "llm_calls": getattr(agent, "llm_calls", 0),
        "max_consecutive_repeats": repeticiones_consecutivas(steps),
        "tool_error_count": len(tool_errors),
        "agent_input_tokens": (result.input_tokens or 0) if result else 0,
        "agent_output_tokens": (result.output_tokens or 0) if result else 0,
        "memory_input_tokens": getattr(agent, "memory_input_tokens", 0),
        "memory_output_tokens": getattr(agent, "memory_output_tokens", 0),
        "latency_s": latency,
        "steps": steps,
    }


def _iter_scenario_paths(scenarios_dir: Path, only: set[str] | None) -> list[Path]:
    paths = sorted(scenarios_dir.glob("*.json"))
    if only is None:
        return paths
    selected = []
    for p in paths:
        sid = load_scenario(p).id
        if sid in only:
            selected.append(p)
    return selected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval/run.py")
    parser.add_argument(
        "--scenarios-dir", default=str(DEFAULT_SCENARIOS_DIR),
        help="Directorio de escenarios (por defecto: scaffold/scenarios).",
    )
    parser.add_argument(
        "--scenarios", default=None,
        help="Lista de ids separados por coma. Por defecto, todos.",
    )
    parser.add_argument(
        "--configs", default=",".join(CONFIGS),
        help=f"Configs a correr, separadas por coma. Disponibles: {', '.join(CONFIGS)}.",
    )
    parser.add_argument(
        "--repeats", type=int, default=1,
        help="Cuántas veces correr cada (escenario, config). Default 1.",
    )
    parser.add_argument(
        "--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS,
        help=f"Tope de iteraciones del agente. Default {DEFAULT_MAX_ITERATIONS}.",
    )
    parser.add_argument(
        "--module", default="student_framework",
        help="Módulo que expone build_agent. Default: student_framework.",
    )
    parser.add_argument(
        "--results-dir", default=str(DEFAULT_RESULTS_DIR),
        help="Dónde escribir los resultados.",
    )
    args = parser.parse_args(argv)

    scenarios_dir = Path(args.scenarios_dir)
    only = set(args.scenarios.split(",")) if args.scenarios else None
    scenario_paths = _iter_scenario_paths(scenarios_dir, only)
    if not scenario_paths:
        raise SystemExit(f"No se encontraron escenarios en {scenarios_dir}.")

    config_names = [c.strip() for c in args.configs.split(",") if c.strip()]
    for name in config_names:
        if name not in CONFIGS:
            raise SystemExit(f"Config desconocida: {name!r}. Disponibles: {', '.join(CONFIGS)}.")

    module = importlib.import_module(args.module)
    if not hasattr(module, "build_agent"):
        raise SystemExit(f"El módulo {args.module!r} no exporta `build_agent`.")

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.results_dir) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    # Óptimo por escenario, derivado por búsqueda (una vez, cacheado).
    print("Computando óptimos (BFS sobre el grafo de estados)...", flush=True)
    optima: dict[Path, int | None] = {}
    for path in scenario_paths:
        optima[path] = optimal_for_path(path)
        print(f"  {load_scenario(path).id}: óptimo = {optima[path]}", flush=True)
    print()

    cases: list[dict[str, Any]] = []
    total = len(scenario_paths) * len(config_names) * args.repeats
    hecho = 0
    cases_path = out_dir / "cases.jsonl"
    with cases_path.open("w", encoding="utf-8") as fh:
        for path in scenario_paths:
            for name in config_names:
                for r in range(args.repeats):
                    hecho += 1
                    sid = load_scenario(path).id
                    print(f"[{hecho}/{total}] {sid} · {name} · repeat {r}", flush=True)
                    case = run_one(
                        path, name, CONFIGS[name], args.max_iterations,
                        module, r, optima[path],
                    )
                    cases.append(case)
                    fh.write(json.dumps(case, ensure_ascii=False) + "\n")
                    marca = "✓" if case["goal_achieved"] else "✗"
                    print(
                        f"    {marca} goal={case['goal_achieved']} "
                        f"calls={case['tool_calls']} latency={case['latency_s']}s",
                        flush=True,
                    )

    meta = {
        "timestamp": timestamp,
        "module": args.module,
        "max_iterations": args.max_iterations,
        "repeats": args.repeats,
    }
    summary = summarize(cases, args.max_iterations)
    (out_dir / "summary.json").write_text(
        json.dumps({"meta": meta, "summary": summary}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "summary.md").write_text(report_md(summary, meta), encoding="utf-8")

    print()
    print(report_md(summary, meta))
    print()
    print(f"Resultados en: {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
