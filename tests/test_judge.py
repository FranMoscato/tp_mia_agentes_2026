"""Tests de la dimensión cualitativa (`eval/judge.py`).

Cubren el núcleo puro (render de traza, agregación, kappa) y `judge_case`
con un judge falso — sin necesidad de un proveedor LLM.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Cargamos el judge por path (eval no es un paquete).
_JUDGE_PATH = Path(__file__).resolve().parent.parent / "eval" / "judge.py"
_spec = importlib.util.spec_from_file_location("eval_judge", _JUDGE_PATH)
judge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge)


# --- format_trace ----------------------------------------------------------


def test_format_trace_incluye_acciones_y_meta() -> None:
    case = {
        "scenario": "study-with-key", "difficulty": "easy", "goal_achieved": False,
        "answer": "Volveré a examinar el escritorio.",
        "steps": [
            {"tool_name": "look", "tool_input": "{}", "tool_output": "Estás en el estudio", "error": None},
            {"tool_name": "take", "tool_input": '{"item": "llave"}', "tool_output": "Tomas la llave", "error": None},
        ],
    }
    txt = judge.format_trace(case)
    assert "study-with-key" in txt
    assert "look(" in txt and "take(" in txt
    assert "Volveré a examinar" in txt


def test_format_trace_sin_acciones() -> None:
    txt = judge.format_trace({"scenario": "x", "difficulty": "easy", "steps": []})
    assert "no actuó" in txt


# --- aggregate_scores ------------------------------------------------------


def test_aggregate_scores_promedio_y_distribucion() -> None:
    judged = [
        {"config": "react", "verdict": {"exploracion_metodica": 2}},
        {"config": "react", "verdict": {"exploracion_metodica": 4}},
        {"config": "gate", "verdict": {"exploracion_metodica": 5}},
    ]
    agg = judge.aggregate_scores(judged)
    assert agg["react"]["avg_exploracion"] == 3.0
    assert agg["react"]["distribucion"] == {2: 1, 4: 1}
    assert agg["gate"]["avg_exploracion"] == 5.0


def test_aggregate_scores_ignora_veredictos_none() -> None:
    judged = [
        {"config": "react", "verdict": None},
        {"config": "react", "verdict": {"exploracion_metodica": 3}},
    ]
    assert judge.aggregate_scores(judged)["react"]["avg_exploracion"] == 3.0


# --- cohen_kappa (meta-eval #16) -------------------------------------------


def test_cohen_kappa_acuerdo_perfecto_con_varianza() -> None:
    assert judge.cohen_kappa([5, 4, 3, 2], [5, 4, 3, 2]) == 1.0


def test_cohen_kappa_sin_varianza_y_coincide() -> None:
    assert judge.cohen_kappa([5, 5, 5], [5, 5, 5]) == 1.0


def test_cohen_kappa_desacuerdo_da_bajo() -> None:
    k = judge.cohen_kappa([5, 5, 1, 1], [1, 1, 5, 5])
    assert k is not None and k < 0.0  # peor que el azar


def test_cohen_kappa_largos_distintos_o_vacio() -> None:
    assert judge.cohen_kappa([1, 2], [1]) is None
    assert judge.cohen_kappa([], []) is None


# --- judge_case con judge falso --------------------------------------------


def test_judge_case_usa_structured_call() -> None:
    class _FakeVerdict:
        def model_dump(self):
            return {"exploracion_metodica": 4, "justificacion": "ordenada"}

    class _FakeAgent:
        def __init__(self):
            self.llamado = False

        def structured_call(self, prompt, schema, system=None):
            self.llamado = True
            assert "TRAYECTORIA" in prompt  # el prompt lleva la traza
            return _FakeVerdict()

    agent = _FakeAgent()
    case = {"scenario": "x", "difficulty": "easy", "steps": []}
    verdict = judge.judge_case(case, agent)
    assert agent.llamado
    assert verdict == {"exploracion_metodica": 4, "justificacion": "ordenada"}


def test_judge_case_devuelve_none_si_el_judge_falla() -> None:
    class _BoomAgent:
        def structured_call(self, prompt, schema, system=None):
            raise RuntimeError("sin respuesta estructurada")

    assert judge.judge_case({"scenario": "x", "steps": []}, _BoomAgent()) is None
