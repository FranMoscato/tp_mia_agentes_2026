"""mia_agents: interfaces fijas y tipos compartidos para el trabajo del curso.

Los estudiantes no deben editar nada en este paquete. Su implementación vive
en `student_framework/` y debe respetar los protocolos y dataclasses
definidos aquí.
"""

from mia_agents.types import (
    AgentResult,
    AgentStep,
    LLMResponse,
    ToolCall,
    ToolSchema,
)
from mia_agents.protocols import Agent, LLMClient
from mia_agents.tool_schema import FINAL_RESULT_TOOL_NAME, final_result_tool_schema

__all__ = [
    "Agent",
    "AgentResult",
    "AgentStep",
    "FINAL_RESULT_TOOL_NAME",
    "LLMClient",
    "LLMResponse",
    "ToolCall",
    "ToolSchema",
    "final_result_tool_schema",
]
