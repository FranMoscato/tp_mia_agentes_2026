"""Tests del núcleo puro del harness de evaluación (`eval/run.py`).

Cubren categorización de fallos, agregación de métricas y render del
resumen, sin necesidad de un proveedor LLM. También verifican que el mapa
`OPTIMAL_CALLS` esté sincronizado con los ids reales del dataset.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from mia_world.scenarios import list_scenarios


# El harness vive en eval/run.py; `eval` no es un paquete (evitamos sombrear el
# builtin `eval`), así que lo cargamos por path.
_RUN_PATH = Path(__file__).resolve().parent.parent / "eval" / "run.py"
_spec = importlib.util.spec_from_file_location("eval_run", _RUN_PATH)
eval_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_run)


def _case(**kw):
    """Caso mínimo con defaults; se sobreescriben los campos relevantes."""
    base = {
        "scenario": "study-with-key",
        "difficulty": "easy",
        "config": "react",
        "optimal_calls": 3,
        "goal_achieved": False,
        "crashed": False,
        "tool_calls": 3,
        "llm_calls": 4,
        "steps": [],
        "tool_error_count": 0,
        "agent_input_tokens": 100,
        "agent_output_tokens": 50,
        "memory_input_tokens": 0,
        "memory_output_tokens": 0,
        "latency_s": 1.0,
    }
    base.update(kw)
    return base


# --- categorize ------------------------------------------------------------


def test_categorize_success() -> None:
    assert eval_run.categorize(_case(goal_achieved=True), 30) == "success"


def test_categorize_crash() -> None:
    assert eval_run.categorize(_case(crashed=True), 30) == "crash"


def test_categorize_exhausted_iterations() -> None:
    """El tope se mide en llamadas al LLM, no en tool-calls.

    Regresión: comparar `tool_calls >= max_iterations` hacía la categoría
    inalcanzable, porque el bucle limita llamadas al LLM y con una tool por
    respuesta `tool_calls` se queda siempre en `max_iterations - 1`.
    """
    assert eval_run.categorize(_case(llm_calls=30, tool_calls=29), 30) == "exhausted_iterations"


def test_categorize_no_exhausted_por_tool_calls() -> None:
    """Muchas tool-calls pero sin agotar el presupuesto de llamadas: no es exhausted."""
    caso = _case(llm_calls=12, tool_calls=30, tool_error_count=0)
    assert eval_run.categorize(caso, 30) == "wrong_path"


def test_categorize_loop_detected() -> None:
    """Tres tool-calls idénticas seguidas se clasifican como loop."""
    steps = [{"tool_name": "examine", "tool_input": '{"target": "cofre"}'} for _ in range(3)]
    assert eval_run.categorize(_case(steps=steps), 30) == "loop_detected"


def test_categorize_loop_tiene_prioridad_sobre_exhausted() -> None:
    """El loop es la causa; agotar iteraciones, la consecuencia."""
    steps = [{"tool_name": "use", "tool_input": '{"item": "k1", "target": "p1"}'} for _ in range(5)]
    caso = _case(steps=steps, llm_calls=30)
    assert eval_run.categorize(caso, 30) == "loop_detected"


def test_look_repetido_intercalado_no_es_loop() -> None:
    """`look` tras cada `go` es exploración legítima en multi-sala, no un loop."""
    steps = []
    for direccion in ("norte", "sur", "este", "oeste"):
        steps.append({"tool_name": "look", "tool_input": "{}"})
        steps.append({"tool_name": "go", "tool_input": f'{{"direction": "{direccion}"}}'})
    assert eval_run.repeticiones_consecutivas(steps) == 1
    assert eval_run.categorize(_case(steps=steps), 30) == "wrong_path"


def test_categorize_tool_errors() -> None:
    assert eval_run.categorize(_case(tool_calls=5, tool_error_count=2), 30) == "tool_errors"


def test_categorize_wrong_path() -> None:
    # Terminó sin goal, sin agotar iteraciones y sin errores de tools.
    assert eval_run.categorize(_case(tool_calls=4, tool_error_count=0), 30) == "wrong_path"


# --- summarize -------------------------------------------------------------


def test_summarize_accuracy_y_breakdown() -> None:
    cases = [
        _case(config="react", goal_achieved=True, tool_calls=3, optimal_calls=3),
        _case(config="react", difficulty="hard", goal_achieved=False,
              tool_calls=29, llm_calls=30),
        _case(config="summarizer", goal_achieved=True, tool_calls=6, optimal_calls=3,
              memory_input_tokens=40, memory_output_tokens=20),
    ]
    summary = eval_run.summarize(cases, max_iterations=30)

    assert summary["n_cases"] == 3
    react = summary["by_config"]["react"]
    assert react["n"] == 2
    assert react["solved"] == 1
    assert react["accuracy"] == 0.5
    # Un resuelto en 3 calls con óptimo 3 -> overhead 1.0x.
    assert react["avg_calls_overhead_vs_optimal"] == 1.0
    # El fallo hard con tool_calls==max_iterations cae en exhausted_iterations.
    assert react["failure_breakdown"].get("exhausted_iterations") == 1
    assert react["failure_breakdown"].get("success") == 1

    summ = summary["by_config"]["summarizer"]
    assert summ["accuracy"] == 1.0
    # Resuelto en 6 calls con óptimo 3 -> overhead 2.0x.
    assert summ["avg_calls_overhead_vs_optimal"] == 2.0
    # Los tokens del resumen se agregan aparte de los del agente.
    assert summ["avg_memory_tokens"] == 60


def test_summarize_accuracy_por_dificultad() -> None:
    cases = [
        _case(config="react", difficulty="easy", goal_achieved=True),
        _case(config="react", difficulty="hard", goal_achieved=False,
              tool_calls=10, llm_calls=11),
    ]
    by_diff = eval_run.summarize(cases, 30)["by_config"]["react"]["by_difficulty"]
    assert by_diff["easy"]["accuracy"] == 1.0
    assert by_diff["hard"]["accuracy"] == 0.0


# --- report_md -------------------------------------------------------------


def test_report_md_incluye_configs() -> None:
    summary = eval_run.summarize([_case(config="react", goal_achieved=True)], 30)
    meta = {"timestamp": "20260727-000000", "module": "student_framework",
            "max_iterations": 30, "repeats": 1}
    md = eval_run.report_md(summary, meta)
    assert "# Evaluación M3" in md
    assert "react" in md
    assert "Accuracy" in md


# --- solver del óptimo (BFS) ----------------------------------------------

# Cargamos el solver por path, igual que el harness.
_OPT_PATH = Path(__file__).resolve().parent.parent / "eval" / "optimal.py"
_opt_spec = importlib.util.spec_from_file_location("eval_optimal", _OPT_PATH)
eval_optimal = importlib.util.module_from_spec(_opt_spec)
_opt_spec.loader.exec_module(eval_optimal)

# Óptimo publicado en el enunciado de M3. Acá se usa SOLO como oráculo de test
# (no como fuente de la métrica: el harness lo deriva por búsqueda). Excluimos
# los dos escenarios más lentos de resolver por BFS (~3-4s) para no encarecer
# la suite; su coincidencia con el enunciado se validó a mano.
_ENUNCIADO_FAST = {
    "study-with-key": 3,
    "color-locks": 11,
    "apartment-keys": 7,
    "library-search": 7,
    "extreme-archive": 4,
    "backtracking-vault": 18,
}


def test_bfs_optimo_coincide_con_enunciado() -> None:
    """El óptimo derivado por BFS coincide con el publicado (cross-validación)."""
    for sc in list_scenarios(eval_run.DEFAULT_SCENARIOS_DIR):
        if sc.id not in _ENUNCIADO_FAST:
            continue
        opt = eval_optimal.compute_optimal(sc)
        assert opt == _ENUNCIADO_FAST[sc.id], (
            f"{sc.id}: BFS={opt} != enunciado={_ENUNCIADO_FAST[sc.id]}"
        )


def test_report_md_sin_casos_resueltos() -> None:
    """Sin resueltos no hay overhead que reportar: se rinde como "—", no "Nonex"."""
    summary = eval_run.summarize([_case(config="react", goal_achieved=False)], 30)
    meta = {"timestamp": "20260825-000000", "module": "student_framework",
            "max_iterations": 30, "repeats": 1}
    md = eval_run.report_md(summary, meta)
    assert "Nonex" not in md
    assert "—" in md
