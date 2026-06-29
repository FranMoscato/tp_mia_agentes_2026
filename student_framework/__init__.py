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

    config = config or {} #NO CAMBIAR
    llm = config.get("llm_client") or LLMClient.from_env() #NO CAMBIAR
    kwargs: dict[str, Any] = {"llm_client": llm} #NO CAMBIAR

    if "max_history_messages" in config:
        kwargs["max_history_messages"] = config["max_history_messages"]

    agent = MyAgent(**kwargs)

    # Registro de las tres herramientas obligatorias del M1. Cada una se
    # importa con su callable y su ToolSchema (derivado con
    # ToolSchema.from_callable en el propio módulo de la herramienta) y se
    # registra en el agente. A partir de acá quedan expuestas al LLM en cada
    # llamada a chat(tools=...).
    from student_framework.tools.calculator import calculadora, calculadora_schema
    from student_framework.tools.file_reader import leer_archivo, leer_archivo_schema
    from student_framework.tools.word_counter import (
        contar_palabras,
        contar_palabras_schema,
    )

    agent.register_tool(calculadora, calculadora_schema)        # 1. calculadora
    agent.register_tool(leer_archivo, leer_archivo_schema)      # 2. lector de archivos
    agent.register_tool(contar_palabras, contar_palabras_schema)  # 3. herramienta libre

    return agent
