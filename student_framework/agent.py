"""Implementación de su agente.

Completen `register_tool` y `run` para el Milestone 1.
En el Milestone 2 amplíen `MyAgent` para que sea estatal y respete
`max_history_messages`.

Los tests de conformidad en `tests/conformance/test_m1.py` y
`test_m2.py` describen con precisión qué comportamientos deben funcionar
— léanlos antes de empezar.
"""

from __future__ import annotations

from typing import Any, Callable

from mia_agents.protocols import LLMClient
from mia_agents.types import AgentResult, ToolSchema, AgentStep
import json

SYSTEM_PROMPT = """
Sos un asistente útil, amable y conversacional. Respondé siempre en español.

Disponés de herramientas que pueden ayudarte a resolver tareas específicas.
Utilizalas únicamente cuando sean necesarias para responder correctamente.

Reglas:

1. Si el usuario hace una pregunta o un pedido explícito, respondelo directamente.
2. Solo utilizá herramientas cuando sean necesarias.
3. Si el usuario únicamente saluda o no hace ningún pedido o pregunta, saludalo y preguntale en qué podés ayudarlo.
4. Sé claro, conciso y cordial en todas tus respuestas.
"""


class MyAgent:
    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str = SYSTEM_PROMPT,
        max_iterations: int = 10,
        max_history_messages: int = 50,
    ) -> None:
        """Inicializa el agente.

        Parameters
        ----------
        llm_client : LLMClient
            Cliente LLM (real o mock) que el agente utilizará.
        system_prompt : str
            System prompt por defecto.
        max_iterations : int
            Tope de iteraciones del bucle del agente (M1).
        max_history_messages : int
            Número máximo de mensajes que se permiten en la lista
            `messages` enviada al LLM en una única llamada. En M1 este
            valor es ignorado; el agente sólo necesita aceptarlo en su
            constructor. En M2 deben respetarlo: la longitud de la
            lista de mensajes pasada a `self._llm.chat(...)` no puede
            superar este número en ninguna llamada, sin importar la
            estrategia de memoria que elijan.
        """
        self._llm = llm_client
        self._system = system_prompt
        self._max_iterations = max_iterations
        self._max_history_messages = max_history_messages
        self._tools={} 
        self._schemas={} 
        # TODO (M2): inicializa la estructura de historial conversacional.

    def register_tool(
        self,
        tool: Callable[..., str],
        schema: ToolSchema,
    ) -> None:
        
        """Registra una herramienta callable junto a su esquema.

        El esquema suele obtenerse con `ToolSchema.from_callable(fn)`. En
        `run`, pasá `tools=list(self._schemas.values())`; el cliente LLM
        aplica `to_llm_spec()` al llamar al proveedor.

        El callable se invoca con kwargs que coinciden con la firma.
        Debe devolver una cadena.
        """

        self._tools[schema.name] = tool
        self._schemas[schema.name] = schema

        return 

    def run(self, user_message: str) -> AgentResult:
        """Ejecuta el bucle del agente hasta una respuesta final o hasta max_iterations.

        Comportamiento esperado (consulta tests/conformance/test_m1.py
        para el contrato exacto del M1):
          - Llama a `self._llm.chat(..., tools=list(self._schemas.values()))`.
          - Si la respuesta contiene tool_calls, ejecuta cada uno y vuelca
            los resultados en la siguiente llamada al chat.
          - Si la respuesta solo contiene texto (sin `tool_calls`),
            devuélvelo en `AgentResult.answer`. En M1 no uses la tool
            sintética `final_result`; ese patrón es de M2 (ver README y
            ENUNCIADO_M2.md).
          - Limita el bucle a `self._max_iterations` y termina de forma
            limpia cuando se alcance.
          - Registra cada invocación de herramienta como un `AgentStep`
            dentro de `result.steps`.

        En el M2, además, llamadas sucesivas sobre la misma instancia
        deben continuar la conversación, y la longitud de la lista de
        mensajes enviada al LLM no debe superar `self._max_history_messages`.
        Acumula los tokens de entrada/salida reportados por los
        `LLMResponse` y exponlos en `AgentResult.input_tokens` /
        `AgentResult.output_tokens`.
        """

        #Creamos elemento de respuesta final del agente
        respuesta_final=AgentResult(answer="")
        respuesta_final.input_tokens=0
        respuesta_final.output_tokens=0
        count_llamados=1

        #Mensaje inicial del usuario
        messages = [
            {"role": "user", "content": user_message}
        ]

        response = self._llm.chat(
            messages=messages,
            tools=list(self._schemas.values()) if self._schemas else None,
            system=self._system,
        )

        if respuesta_final.input_tokens and respuesta_final.output_tokens:
            respuesta_final.input_tokens+=response.input_tokens
            respuesta_final.output_tokens+=response.output_tokens

        while not response.content and count_llamados<10:
            ### Agregamos LLM message a contexto
            messages.append({"role": "assistant", "content": response.content,
                            "tool_calls": [
                            {
                                "function": {
                                    "name": call.name,
                                    "arguments": json.loads(call.arguments),
                                }
                            }
                            for call in response.tool_calls],
                            })

            ### Corremos las tools
            for call in response.tool_calls:
                args = json.loads(call.arguments)

                ### Caso de tools desconocidas
                if call.name not in self._tools:
                    messages.append({
                        "role": "tool",
                        "content": f"Error: herramienta desconocida '{call.name}'."
                    })

                    respuesta_final.steps.append(
                        AgentStep(
                            tool_name=call.name,
                            tool_input=call.arguments,
                            tool_output=None,
                            error=f"Herramienta desconocida: {call.name}"
                        )
                    )
                    continue

                ### Para las tools conocidas
                tool_result = self._tools[call.name](**args)
                messages.append({"role": "tool",  "content": f"Tool: {call.name}\nResult: {tool_result}"})
                
                step = AgentStep(
                    tool_name=call.name,
                    tool_input=call.arguments,
                    tool_output=None,
                    error=None
                    )
                
                if str(tool_result).startswith("Error:"):
                    step.error = str(tool_result)
                
                else:
                    step.tool_output=str(tool_result)
                
                respuesta_final.steps.append(step)

            response = self._llm.chat(
                messages=messages,
                tools=list(self._schemas.values()) if self._schemas else None,
                system=self._system,
            )


            if respuesta_final.input_tokens and respuesta_final.output_tokens:
                respuesta_final.input_tokens+=response.input_tokens
                respuesta_final.output_tokens+=response.output_tokens
                
            count_llamados+=1

        respuesta_final.answer=response.content

        return respuesta_final

    def structured_call(
        self,
        prompt: str,
        schema: Any,
        max_repair_attempts: int = 2,
    ) -> Any:
        """Pide al LLM una respuesta validada contra `schema` (M2).

        Obligatorio: herramienta sintética `final_result` (ver
        `mia_agents.final_result_tool_schema` / `FINAL_RESULT_TOOL_NAME`).
        El agente ofrece esa tool al LLM, valida los `arguments` del
        `tool_call` y reintenta con contexto de reparación si el modelo
        responde con texto libre o con argumentos inválidos.

        Implementa esto en el M2:
          - Pasa `tools=[final_result_tool_schema(schema)]` en cada
            llamada a `chat` dentro de este método.
          - Termina solo cuando llega un `tool_call` a `final_result`
            cuyos argumentos validan con `schema.model_validate(...)`.
          - Reintenta hasta `max_repair_attempts` incluyendo el fallo en
            los mensajes (respuesta previa, mensaje `tool`, o user de
            reparación).
          - Si tras los reintentos sigue fallando, levanta una excepción
            limpia (no devuelvas valores parciales ni `None` sin avisar).

        El M1 deja esto como stub; los tests de M2 verifican el contrato.
        """
        raise NotImplementedError("M2: implementa salida estructurada con reparación")
