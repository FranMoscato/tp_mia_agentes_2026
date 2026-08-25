"""Smoke de integración punta a punta del harness (`eval/run.py`).

A diferencia de los unit tests, esto ejercita el pipeline COMPLETO con un LLM
simulado que *resuelve* un escenario real: `run_one` → build_agent → tools del
mundo → check_goal → construcción del caso → summarize → report_md. De-riesga
la corrida real (si hay un bug de integración, salta acá, no en producción).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from mia_agents.testing import MockLLMClient
from mia_agents.types import LLMResponse, ToolCall

from student_framework import build_agent as sf_build_agent

_REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("eval_run", _REPO / "eval" / "run.py")
eval_run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_run)

_EASY = _REPO / "scenarios" / "01-study-with-key.json"


def _solve_responses() -> list[LLMResponse]:
    """Secuencia que resuelve study-with-key: examine → take → use → fin."""
    return [
        LLMResponse(content=None, tool_calls=[
            ToolCall(id="1", name="examine", arguments=json.dumps({"target": "alfombra"}))]),
        LLMResponse(content=None, tool_calls=[
            ToolCall(id="2", name="take", arguments=json.dumps({"item": "llave_oro"}))]),
        LLMResponse(content=None, tool_calls=[
            ToolCall(id="3", name="use",
                     arguments=json.dumps({"item": "llave_oro", "target": "puerta_principal"}))]),
        LLMResponse(content="Abrí la puerta principal."),
    ]


class _FakeModule:
    """Módulo con build_agent que inyecta un mock que resuelve el escenario."""

    ESCAPE_ROOM_SYSTEM_PROMPT = "prompt de sala de escape (test)"
    ESCAPE_ROOM_SYSTEM_PROMPT_VERSION = "test-v1"

    def build_agent(self, config):
        cfg = {**config, "llm_client": MockLLMClient(_solve_responses()),
               "retry_backoff_base": 0}
        return sf_build_agent(cfg)


def test_run_one_resuelve_escenario_end_to_end() -> None:
    case = eval_run.run_one(
        _EASY, "react", {"use_summarizer": False},
        max_iterations=30, module=_FakeModule(), repeat=0, optimal_calls=3,
    )
    assert case["goal_achieved"] is True
    assert case["tool_calls"] == 3
    assert case["config"] == "react"
    assert eval_run.categorize(case, 30) == "success"

    # Pipeline de métricas + render sobre un caso resuelto.
    summary = eval_run.summarize([case], 30)
    assert summary["by_config"]["react"]["accuracy"] == 1.0
    assert summary["by_config"]["react"]["avg_calls_overhead_vs_optimal"] == 1.0  # 3/3
    md = eval_run.report_md(summary, {
        "timestamp": "t", "module": "fake", "max_iterations": 30, "repeats": 1})
    assert "Accuracy" in md


def test_gate_no_bloquea_una_solucion_valida() -> None:
    """El gate (experimento #2) no debe romper una partida jugada correctamente."""
    case = eval_run.run_one(
        _EASY, "gate", {"use_summarizer": False, "use_gate": True},
        max_iterations=30, module=_FakeModule(), repeat=0, optimal_calls=3,
    )
    assert case["goal_achieved"] is True
    assert case["tool_calls"] == 3
    assert case["tool_error_count"] == 0  # el gate no bloqueó nada válido
