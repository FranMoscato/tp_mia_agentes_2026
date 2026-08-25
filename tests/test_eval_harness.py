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
    assert eval_run.categorize(caso, 30) == "prosa_en_vez_de_tool"


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
    assert eval_run.categorize(_case(steps=steps), 30) == "prosa_en_vez_de_tool"


def test_categorize_tool_errors() -> None:
    assert eval_run.categorize(_case(tool_calls=5, tool_error_count=2), 30) == "tool_errors"


def test_categorize_prosa_en_vez_de_tool() -> None:
    # Terminó sin goal, sin loop, sin agotar iteraciones y sin errores de tools:
    # el modelo dejó de pedir herramientas y devolvió texto (modo dominante).
    assert eval_run.categorize(_case(tool_calls=4, tool_error_count=0), 30) == "prosa_en_vez_de_tool"


# --- clasificar_prosa (variantes del modo dominante, de trazas reales) ------


def test_clasificar_prosa_inversion_de_rol() -> None:
    # Del piloto real (color-locks): imparte instrucciones a un tercero.
    assert eval_run.clasificar_prosa("Haz uso de la llave plateada en el cofre.") == "inversion_de_rol"
    assert eval_run.clasificar_prosa("Ve a la estantería y examina los volúmenes.") == "inversion_de_rol"


def test_clasificar_prosa_intencion_anunciada() -> None:
    # Del piloto real (study-with-key): anuncia lo que hará en 1ª persona.
    assert eval_run.clasificar_prosa("Volveré a examinar el escritorio.") == "intencion_anunciada"
    assert eval_run.clasificar_prosa("Ahora tengo la llave dorada en mi inventario.") == "intencion_anunciada"


def test_clasificar_prosa_otro_y_vacio() -> None:
    assert eval_run.clasificar_prosa("") == "otro"
    assert eval_run.clasificar_prosa(None) == "otro"


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


def test_summarize_passk_ci_percentiles_y_costo() -> None:
    # 2 escenarios × k=2 repeats. easy-1: 2/2 resuelto; hard-1: 0/2.
    cases = [
        _case(config="react", scenario="easy-1", difficulty="easy",
              goal_achieved=True, latency_s=1.0),
        _case(config="react", scenario="easy-1", difficulty="easy",
              goal_achieved=True, latency_s=3.0),
        _case(config="react", scenario="hard-1", difficulty="hard",
              goal_achieved=False, latency_s=2.0, llm_calls=30, tool_calls=29),
        _case(config="react", scenario="hard-1", difficulty="hard",
              goal_achieved=False, latency_s=4.0, llm_calls=30, tool_calls=29),
    ]
    m = eval_run.summarize(cases, 30)["by_config"]["react"]

    # pass^k: solo easy-1 pasa los k=2 intentos -> 1/2 escenarios.
    assert m["k"] == 2
    assert m["pass_k_scenarios"] == "1/2"
    assert m["pass_hat_k"] == 0.5
    # IC de Wilson para 2/4 resueltos: intervalo válido que rodea 0.5.
    lo, hi = m["accuracy_ci95"]
    assert 0.0 <= lo < 0.5 < hi <= 1.0
    # Latencia por percentiles, no promedio.
    assert m["latency_p50_s"] is not None
    assert m["latency_p95_s"] is not None
    # Costo por caso RESUELTO: tokens totales (incluye fallidos) / resueltos.
    # 4 casos × 150 tokens (default) = 600; / 2 resueltos = 300.
    assert m["tokens_per_solved"] == 300


def test_summarize_observabilidad_tools_invalidas_progreso() -> None:
    cases = [
        _case(config="react", tool_calls=3, tool_error_count=1,
              steps=[
                  {"tool_name": "look", "tool_input": "{}"},
                  {"tool_name": "examine", "tool_input": "{}"},
                  {"tool_name": "use", "tool_input": "{}", "error": "no lo tenés"},
              ],
              items_taken=2, rooms_visited=1, items_opened=1),
    ]
    m = eval_run.summarize(cases, 30)["by_config"]["react"]
    assert m["tool_usage"] == {"look": 1, "examine": 1, "use": 1}
    assert m["invalid_action_rate"] == round(1 / 3, 3)
    assert m["avg_progress"]["items_taken"] == 2.0
    assert m["avg_progress"]["items_opened"] == 1.0


def test_costo_usd_pricing_y_local() -> None:
    # nova-lite: 0.06 in / 0.24 out por 1M.
    assert eval_run.costo_usd(1_000_000, 0, "amazon.nova-lite-v1:0") == 0.06
    assert eval_run.costo_usd(0, 1_000_000, "amazon.nova-lite-v1:0") == 0.24
    # modelo local / desconocido -> $0.
    assert eval_run.costo_usd(1_000_000, 1_000_000, "qwen2.5:3b") == 0.0
    assert eval_run.costo_usd(1_000_000, 1_000_000, None) == 0.0


def test_summarize_costo_varianza_redundancia() -> None:
    cases = [
        _case(config="react", scenario="s1", goal_achieved=True, repeat=0,
              agent_input_tokens=1_000_000, agent_output_tokens=0,
              max_consecutive_repeats=1),
        _case(config="react", scenario="s1", goal_achieved=False, repeat=1,
              max_consecutive_repeats=3),
    ]
    m = eval_run.summarize(cases, 30, model="amazon.nova-lite-v1:0")["by_config"]["react"]
    # Costo: 1M input a 0.06 sobre 2 casos.
    assert m["cost_usd_total"] == 0.06
    assert m["cost_usd_per_case"] == 0.03
    assert m["cost_usd_per_solved"] == 0.06  # 1 resuelto
    # Varianza: s1 resuelto 1/2 -> un solo escenario, std 0.
    assert m["solve_rate_by_scenario"] == {"s1": 0.5}
    # Redundancia: rachas 1 y 3.
    assert m["redundancy_distribution"] == {"1": 1, "3": 1}


def test_summarize_desglosa_variantes_de_prosa() -> None:
    cases = [
        _case(config="react", scenario="s1", goal_achieved=False, tool_calls=2,
              answer="Haz uso de la llave en el cofre."),
        _case(config="react", scenario="s2", goal_achieved=False, tool_calls=2,
              answer="Volveré a examinar el escritorio."),
    ]
    m = eval_run.summarize(cases, 30)["by_config"]["react"]
    assert m["failure_breakdown"]["prosa_en_vez_de_tool"] == 2
    vb = m["prosa_variant_breakdown"]
    assert vb.get("inversion_de_rol") == 1
    assert vb.get("intencion_anunciada") == 1


# --- gate determinístico (experimento #2) ----------------------------------


class _FakeWorld:
    def __init__(self, item_ids, inventory):
        self.items = {i: object() for i in item_ids}
        self.inventory = list(inventory)


def test_gate_bloquea_id_inventado() -> None:
    gate = eval_run.build_escape_gate(_FakeWorld(["llave", "puerta"], []))
    msg = gate("examine", {"target": "fantasma"})
    assert msg is not None and "no existe" in msg


def test_gate_bloquea_use_de_item_no_tomado() -> None:
    gate = eval_run.build_escape_gate(_FakeWorld(["llave", "puerta"], []))
    msg = gate("use", {"item": "llave", "target": "puerta"})
    assert msg is not None and "inventario" in msg


def test_gate_permite_use_de_item_en_inventario() -> None:
    gate = eval_run.build_escape_gate(_FakeWorld(["llave", "puerta"], ["llave"]))
    assert gate("use", {"item": "llave", "target": "puerta"}) is None


def test_gate_no_toca_go_ni_ids_validos() -> None:
    gate = eval_run.build_escape_gate(_FakeWorld(["llave", "puerta"], []))
    assert gate("go", {"direction": "norte"}) is None
    assert gate("examine", {"target": "puerta"}) is None
    assert gate("take", {"item": "llave"}) is None


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
