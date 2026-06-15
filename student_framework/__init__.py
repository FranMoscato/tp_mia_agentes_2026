"""Paquete propio del grupo.

Implementen el agente en `agent.py` y registren sus herramientas a
continuación, en `build_agent`. Tanto el runner de la CLI como los tests
de conformidad llaman a `build_agent`, por lo que esta es la única puerta
de entrada pública de su entrega.
"""

from __future__ import annotations

from typing import Any

from mia_agents.llm_client import LLMClient
from mia_agents.protocols import Agent

from .agent import MyAgent


def build_agent(config: dict[str, Any] | None = None) -> Agent:
    """Construye y configura su agente.

    `config` es opcional. Si se proporciona `config["llm_client"]`, el
    agente debe usarlo (así es como los tests de conformidad inyectan un
    cliente mock). Si no, se construye a partir del entorno.

    TODO (M1): instancien su agente y llamen a `agent.register_tool(...)`
    por cada una de sus herramientas antes de devolverlo.
    """
    config = config or {}
    llm = config.get("llm_client") or LLMClient.from_env()

    kwargs: dict[str, Any] = {"llm_client": llm}
    if "max_history_messages" in config:
        kwargs["max_history_messages"] = config["max_history_messages"]

    agent = MyAgent(**kwargs)

    # Ejemplo de registro (elimínenlo cuando sus herramientas estén listas):
    # from student_framework.tools.example import reverse_string, reverse_string_schema
    # agent.register_tool(reverse_string, reverse_string_schema)

    # TODO (M1): registren calculadora, lector de archivos y herramienta libre.
    # agent.register_tool(calculator, calculator_schema)
    # agent.register_tool(file_reader, file_reader_schema)
    # agent.register_tool(my_free_tool, my_free_tool_schema)
    return agent
