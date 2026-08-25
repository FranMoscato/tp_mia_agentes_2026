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
import math
import os
import re
import statistics
import subprocess
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
    # Experimento #2 (gate on/off): "react" es el gate OFF; "gate" activa el
    # gate determinístico. `use_gate` lo consume run_one (construye el gate
    # cerrado sobre el world del escenario), no build_agent.
    "gate": {"use_summarizer": False, "use_gate": True},
}

# Tope de iteraciones para el eval. El default del agente (20) no alcanza para
# los escenarios extreme (vault-combination óptimo = 21); damos holgura.
DEFAULT_MAX_ITERATIONS = 30

# Precio on-demand en USD por 1M de tokens (input, output). Se matchea por
# substring del model id. Modelos locales (Ollama) o desconocidos = $0.
# Fuente: precios publicados de Amazon Bedrock (Nova). Actualizar si cambian.
_PRICING_USD_POR_1M: dict[str, tuple[float, float]] = {
    "nova-lite": (0.06, 0.24),
    "nova-micro": (0.035, 0.14),
    "nova-pro": (0.80, 3.20),
}


def costo_usd(input_tokens: int, output_tokens: int, model: str | None) -> float:
    """Costo estimado en USD de una cantidad de tokens para `model`.

    0 para modelos locales/desconocidos (Ollama). Es un estimado: sirve para
    comparar configs/modelos, no como factura.
    """
    if not model:
        return 0.0
    pin = pout = 0.0
    for clave, (i, o) in _PRICING_USD_POR_1M.items():
        if clave in model:
            pin, pout = i, o
            break
    return round(input_tokens / 1e6 * pin + output_tokens / 1e6 * pout, 6)


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


# Marcadores de las dos variantes de "prosa en vez de tool_call" (clase 7 /
# punto de análisis de errores). Se aplican al `answer` final del caso.
#   - inversión de rol: el modelo IMPARTE instrucciones a un tercero en vez de
#     actuar ("Haz uso de...", "Ve a...", "Examina...", "Haz lo siguiente:").
#   - intención anunciada: el modelo ANUNCIA lo que va a hacer, en primera
#     persona, en vez de hacerlo ("Voy a...", "Volveré a...", "Ahora tengo...").
_RE_INVERSION_ROL = re.compile(
    r"^\s*(haz\b|hac[eé]\b|us[aá]\b|utiliz[aá]\b|tom[aá]\b|v[eé]\b|and[aá]\b|"
    r"examin[aá]\b|abr[ií]\b|explor[aá]\b|prob[aá]\b|primero[,\s]|"
    r"haz lo siguiente|deber[ií]as\b|ten[eé]s que\b)",
    re.IGNORECASE,
)
_RE_INTENCION_ANUNCIADA = re.compile(
    r"^\s*(voy a\b|voyar[eé]\b|ir[eé]\b|volver[eé]\b|har[eé]\b|proceder[eé]\b|"
    r"intentar[eé]\b|ahora (tengo|voy|proceder|examinar)|"
    r"a continuaci[oó]n voy|mi (siguiente|pr[oó]xim)|deber[ií]a (ahora|ahora )?)",
    re.IGNORECASE,
)


def clasificar_prosa(answer: str | None) -> str:
    """Sub-clasifica el `answer` de un caso `prosa_en_vez_de_tool`.

    Devuelve 'inversion_de_rol' | 'intencion_anunciada' | 'otro'. Es una
    heurística sobre el texto: el modo de fallo real observado en las trazas
    tiene estas dos variantes (punto de análisis de errores de la clase 7).
    """
    texto = (answer or "").strip()
    if not texto:
        return "otro"
    if _RE_INTENCION_ANUNCIADA.match(texto):
        return "intencion_anunciada"
    if _RE_INVERSION_ROL.match(texto):
        return "inversion_de_rol"
    return "otro"


def categorize(case: dict[str, Any], max_iterations: int) -> str:
    """Clasifica el resultado de una corrida en un modo de fallo (o éxito).

    Categorías:
      - success               — se abrió la puerta (goal cumplido).
      - crash                 — la corrida lanzó una excepción no controlada.
      - loop_detected         — repitió la misma tool-call en círculos.
      - exhausted_iterations  — agotó el tope de iteraciones sin lograr el goal.
      - tool_errors           — terminó sin goal y hubo errores de herramientas.
      - prosa_en_vez_de_tool  — terminó devolviendo TEXTO en lugar de una
                                tool-call (el modo dominante observado). Es la
                                única otra salida del bucle de `run()`: el
                                modelo dejó de pedir herramientas y "habló".
                                Sus variantes (inversión de rol / intención
                                anunciada) se desglosan con `clasificar_prosa`.

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
    return "prosa_en_vez_de_tool"


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 2) if xs else None


def _percentile(xs: list[float], p: float) -> float | None:
    """Percentil `p` (0..1) por interpolación lineal. `None` si no hay datos."""
    if not xs:
        return None
    ys = sorted(xs)
    if len(ys) == 1:
        return round(ys[0], 3)
    k = (len(ys) - 1) * p
    lo = math.floor(k)
    hi = min(lo + 1, len(ys) - 1)
    return round(ys[lo] + (ys[hi] - ys[lo]) * (k - lo), 3)


def _wilson_ci(k: int, n: int, z: float = 1.96) -> list[float | None]:
    """Intervalo de confianza de Wilson (95%) para una proporción k/n.

    Mejor que la normal para n chico / proporciones cerca de 0 o 1, que es
    justo el régimen de esta eval (8 escenarios, pocos repeats).
    """
    if n == 0:
        return [None, None]
    phat = k / n
    denom = 1 + z * z / n
    centro = (phat + z * z / (2 * n)) / denom
    margen = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return [round(max(0.0, centro - margen), 3), round(min(1.0, centro + margen), 3)]


def summarize(
    cases: list[dict[str, Any]], max_iterations: int, model: str | None = None
) -> dict[str, Any]:
    """Agrega las corridas en métricas por config, por dificultad y globales.

    `model` habilita el costo en USD (0 para modelos locales/desconocidos).
    """
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

        # Desglose de categorías de fallo + variantes de la prosa (modo
        # dominante), estas últimas sobre el `answer` real de cada caso.
        cats: dict[str, int] = {}
        prosa_variantes: dict[str, int] = {}
        for c in sub:
            cat = categorize(c, max_iterations)
            cats[cat] = cats.get(cat, 0) + 1
            if cat == "prosa_en_vez_de_tool":
                v = clasificar_prosa(c.get("answer"))
                prosa_variantes[v] = prosa_variantes.get(v, 0) + 1

        # Accuracy por dificultad.
        by_diff: dict[str, dict[str, Any]] = {}
        for diff in sorted({c["difficulty"] for c in sub}):
            d = [c for c in sub if c["difficulty"] == diff]
            by_diff[diff] = {
                "n": len(d),
                "solved": sum(1 for c in d if c["goal_achieved"]),
                "accuracy": round(sum(c["goal_achieved"] for c in d) / len(d), 3),
            }

        # pass^k: el agente actúa sin supervisión, así que la métrica relevante
        # es "resolver el escenario en TODOS los k intentos", no el promedio.
        by_scen: dict[str, list[dict[str, Any]]] = {}
        for c in sub:
            by_scen.setdefault(c["scenario"], []).append(c)
        k = max((len(v) for v in by_scen.values()), default=0)
        pass_k_scen = sum(
            1 for v in by_scen.values() if v and all(x["goal_achieved"] for x in v)
        )
        pass_hat_k = round(pass_k_scen / len(by_scen), 3) if by_scen else None

        # Costo POR CASO RESUELTO (no por corrida): tokens totales / resueltos.
        tokens_totales = sum(
            c["agent_input_tokens"] + c["agent_output_tokens"]
            + c["memory_input_tokens"] + c["memory_output_tokens"]
            for c in sub
        )
        tokens_por_resuelto = (
            round(tokens_totales / len(exitosos)) if exitosos else None
        )

        latencias = [c["latency_s"] for c in sub]

        # Costo en USD (estimado): total, por caso y por resuelto.
        total_in = sum(c["agent_input_tokens"] + c["memory_input_tokens"] for c in sub)
        total_out = sum(c["agent_output_tokens"] + c["memory_output_tokens"] for c in sub)
        cost_total = costo_usd(total_in, total_out, model)
        cost_por_caso = round(cost_total / n, 6) if n else None
        cost_por_resuelto = round(cost_total / len(exitosos), 6) if exitosos else None

        # Varianza entre repeats: tasa de éxito por escenario y su desvío.
        solve_rates = {
            sid: sum(x["goal_achieved"] for x in v) / len(v)
            for sid, v in by_scen.items()
        }
        solve_rate_std = (
            round(statistics.pstdev(solve_rates.values()), 3)
            if len(solve_rates) > 1 else 0.0
        )

        # Redundancia: distribución de la racha máxima de tool-calls repetidas.
        redundancia: dict[str, int] = {}
        for c in sub:
            r = c.get("max_consecutive_repeats", 0)
            redundancia[str(r)] = redundancia.get(str(r), 0) + 1

        # Latencia desglosada agente vs. summarizer (memory_latency_s se captura
        # en run_one; en corridas previas es 0).
        mem_lat = [c.get("memory_latency_s", 0) for c in sub]
        agente_lat = [c["latency_s"] - c.get("memory_latency_s", 0) for c in sub]

        # Observabilidad del comportamiento:
        # - uso de herramientas (¿sobre-mira?, ¿nunca usa?)
        # - tasa de acción inválida (tool_errors / tool_calls): movidas ilegales
        #   que el gate atrapa.
        tool_usage: dict[str, int] = {}
        for c in sub:
            for s in c.get("steps") or []:
                t = s.get("tool_name")
                tool_usage[t] = tool_usage.get(t, 0) + 1
        total_calls = sum(c["tool_calls"] for c in sub)
        total_err = sum(c.get("tool_error_count", 0) for c in sub)
        invalid_rate = round(total_err / total_calls, 3) if total_calls else None

        # Progreso parcial (observabilidad, para no reducir todo a 0/8): cuánto
        # avanzó el agente aunque no abriera la puerta. Presente solo en corridas
        # que lo capturan (ver run_one); en las previas queda en 0.
        prog = lambda key: _mean([c.get(key, 0) for c in sub])

        summary["by_config"][config] = {
            "n": n,
            "solved": len(exitosos),
            "accuracy": round(len(exitosos) / n, 3) if n else None,
            "accuracy_ci95": _wilson_ci(len(exitosos), n),
            "pass_hat_k": pass_hat_k,
            "k": k,
            "pass_k_scenarios": f"{pass_k_scen}/{len(by_scen)}",
            "avg_calls_overhead_vs_optimal": _mean(overhead),
            "avg_tool_calls": _mean([c["tool_calls"] for c in sub]),
            "latency_p50_s": _percentile(latencias, 0.50),
            "latency_p95_s": _percentile(latencias, 0.95),
            "latency_agente_p50_s": _percentile(agente_lat, 0.50),
            "latency_summarizer_p50_s": _percentile(mem_lat, 0.50),
            "tokens_per_solved": tokens_por_resuelto,
            "avg_agent_tokens": _mean(
                [c["agent_input_tokens"] + c["agent_output_tokens"] for c in sub]
            ),
            "avg_memory_tokens": _mean(
                [c["memory_input_tokens"] + c["memory_output_tokens"] for c in sub]
            ),
            "cost_usd_total": cost_total,
            "cost_usd_per_case": cost_por_caso,
            "cost_usd_per_solved": cost_por_resuelto,
            "solve_rate_by_scenario": {k: round(v, 3) for k, v in solve_rates.items()},
            "solve_rate_std": solve_rate_std,
            "redundancy_distribution": redundancia,
            "tool_usage": tool_usage,
            "invalid_action_rate": invalid_rate,
            "avg_progress": {
                "items_taken": prog("items_taken"),
                "rooms_visited": prog("rooms_visited"),
                "items_opened": prog("items_opened"),
            },
            "failure_breakdown": cats,
            "prosa_variant_breakdown": prosa_variantes,
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
    lines.append(f"- Provider/modelo: `{meta.get('provider')}` / `{meta.get('model')}`"
                 + (f" · perfil AWS: `{meta.get('aws_profile')}`" if meta.get('provider') == 'bedrock' else ""))
    lines.append(f"- Versión de prompt: `{meta.get('prompt_version')}` · commit: `{meta.get('git_commit')}`")
    lines.append(f"- max_iterations: {meta['max_iterations']} · repeats: {meta['repeats']}")
    lines.append(f"- Casos totales: {summary['n_cases']}")
    lines.append("")

    lines.append("## Métricas por configuración")
    lines.append("")
    lines.append("_Latencia en percentiles (nunca promedio); costo por caso resuelto; "
                 "pass^k = resolver el escenario en los k intentos._")
    lines.append("")
    header = (
        "| Config | Accuracy (IC95%) | pass^k | Overhead vs óptimo | "
        "Tokens/resuelto | Latencia p50/p95 (s) |"
    )
    lines.append(header)
    lines.append("|---|---:|---:|---:|---:|---:|")
    for config, m in summary["by_config"].items():
        overhead = m["avg_calls_overhead_vs_optimal"]
        overhead_txt = f"{overhead}x" if overhead is not None else "—"
        ci = m["accuracy_ci95"]
        ci_txt = f" [{ci[0]}, {ci[1]}]" if ci and ci[0] is not None else ""
        passk_txt = (
            f"{m['pass_hat_k']} ({m['pass_k_scenarios']}, k={m['k']})"
            if m["pass_hat_k"] is not None else "—"
        )
        lines.append(
            f"| {config} | {m['accuracy']}{ci_txt} | {passk_txt} | "
            f"{overhead_txt} | {m['tokens_per_solved'] or '—'} | "
            f"{m['latency_p50_s']} / {m['latency_p95_s']} |"
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
            if cat == "prosa_en_vez_de_tool" and m["prosa_variant_breakdown"]:
                for v, vc in sorted(
                    m["prosa_variant_breakdown"].items(), key=lambda kv: -kv[1]
                ):
                    lines.append(f"    - {v}: {vc}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Corrida contra el LLM real
# ---------------------------------------------------------------------------


def build_escape_gate(world: Any) -> Any:
    """Gate determinístico de la sala de escape (experimento #2).

    Garantiza con un `if` lo que el prompt no puede: (1) no inventar IDs —un
    argumento `item`/`target` debe ser un id que exista en el mundo—, y (2) no
    usar un objeto que no está en el inventario. Devuelve un error accionable
    (que el agente ve como observación) o None si la acción está permitida.
    """
    def gate(tool_name: str, args: dict[str, Any]) -> str | None:
        # (1) No inventar IDs: los parámetros que refieren objetos deben existir.
        for param in ("item", "target"):
            val = args.get(param)
            if val is not None and val not in world.items:
                return (
                    f"Error: no existe ningún objeto con id '{val}'. Usá "
                    f"exactamente un id que haya aparecido en un resultado previo."
                )
        # (2) No usar un objeto que no tomaste.
        if tool_name == "use":
            item = args.get("item")
            if item is not None and item not in world.inventory:
                return (
                    f"Error: no tenés '{item}' en el inventario. Primero tenés "
                    f"que tomarlo con take."
                )
        return None

    return gate


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
    # Gate determinístico (experimento #2): si el config lo pide, lo construimos
    # cerrado sobre el world de ESTE escenario y lo pasamos como callable.
    if build_config.pop("use_gate", False):
        build_config["tool_gate"] = build_escape_gate(world)

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

    # Progreso parcial (observabilidad): cuánto avanzó el mundo aunque el goal
    # no se cumpla. Se lee del estado final del world.
    rooms_visited = len({e.split(":", 1)[1] for e in world.event_log
                         if e.startswith("enter:")})
    items_opened = sum(1 for it in world.items.values() if it.open_state == "open")

    return {
        "scenario": scenario.id,
        "difficulty": scenario.difficulty,
        "config": config_name,
        "repeat": repeat,
        "optimal_calls": optimal_calls,
        "goal_achieved": bool(achieved),
        "goal_reason": reason,
        "items_taken": len(world.inventory),
        "rooms_visited": rooms_visited,
        "items_opened": items_opened,
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
        "memory_latency_s": round(getattr(agent, "memory_latency_s", 0.0), 3),
        "steps": steps,
    }


def _git_commit() -> str | None:
    """Hash corto del commit actual (para versionar la corrida). None si falla."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


def _env_value(key: str) -> str | None:
    """Valor de una variable: primero el entorno, luego el `.env` del repo.

    Así el meta queda poblado aunque el `.env` no esté exportado al entorno.
    """
    if os.environ.get(key):
        return os.environ[key]
    env_file = _REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}=") and not line.startswith("#"):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


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

    # Versionado (#14): sin esto, dos corridas de distintas máquinas/cuentas son
    # indistinguibles. Grabamos provider+modelo (el activo, respetando la misma
    # precedencia que LLMClient.from_env: OLLAMA_HOST gana), cuenta/perfil,
    # versión de prompt y commit.
    if _env_value("OLLAMA_HOST"):
        provider = "ollama"
        model = _env_value("OLLAMA_MODEL") or "llama3.1"
    else:
        provider = "bedrock"
        model = _env_value("BEDROCK_MODEL_ID")
    meta = {
        "timestamp": timestamp,
        "module": args.module,
        "max_iterations": args.max_iterations,
        "repeats": args.repeats,
        "provider": provider,
        "model": model,
        "bedrock_model_id": _env_value("BEDROCK_MODEL_ID"),
        "aws_profile": _env_value("AWS_PROFILE"),
        "aws_region": _env_value("AWS_REGION") or _env_value("AWS_DEFAULT_REGION"),
        "prompt_version": getattr(module, "ESCAPE_ROOM_SYSTEM_PROMPT_VERSION", None),
        "git_commit": _git_commit(),
    }
    summary = summarize(cases, args.max_iterations, model=model)
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
