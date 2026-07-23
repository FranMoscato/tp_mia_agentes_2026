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
from mia_agents.types import AgentResult, AgentStep, LLMResponse, ToolCall, ToolSchema
import json

SYSTEM_PROMPT = """
Sos un asistente útil, amable y conversacional. Respondé siempre en español.

Disponés de herramientas que pueden ayudarte a resolver tareas específicas. Utilizalas únicamente cuando sean necesarias para responder correctamente.

Reglas:

1. Si el usuario hace una pregunta o un pedido explícito, respondelo directamente.
2. Solo utilizá herramientas cuando sean necesarias. Chequea que la respuesta no este en contexto previo o tu conocimiento general
3. Si el usuario únicamente saluda o no hace ningún pedido o pregunta, saludalo y preguntale en qué podés ayudarlo.
4. Sé claro, conciso y cordial en todas tus respuestas.
5. La información mencionada por el usuario en mensajes anteriores forma parte del contexto disponible. No utilices herramientas para recuperar información que ya aparece en la conversación.
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
        self.messages: list[dict[str, Any]] = []

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

        Comportamiento (ver tests/conformance/test_m1.py y ENUNCIADO_M1.md
        para el contrato exacto del M1):
          - Llama a `self._llm.chat(..., tools=list(self._schemas.values()))`.
          - Si la respuesta contiene `tool_calls`, ejecuta cada uno, vuelca
            sus resultados en la conversación y vuelve a llamar al LLM.
          - Si la respuesta NO contiene `tool_calls`, su `content` es la
            respuesta final (`AgentResult.answer`). En M1 no se usa la tool
            sintética `final_result` (eso es M2).
          - El bucle hace como máximo `self._max_iterations` llamadas al LLM
            y termina de forma limpia al alcanzar ese tope.
          - Cada invocación de herramienta se registra como un `AgentStep`.
          - `run` nunca lanza excepción: los errores (herramienta
            desconocida, argumentos inválidos, fallo de la herramienta) se
            capturan y quedan reflejados en el `AgentStep.error`
            correspondiente.

        En M2, además, llamadas sucesivas continúan la conversación y la
        lista de mensajes no supera `self._max_history_messages`.
        """

        resultado = AgentResult(answer="")
        self.messages.append({"role": "user", "content": user_message})
        
        # Esquemas de las herramientas a exponer al LLM
        tools = list(self._schemas.values()) if self._schemas else None

        

        # --- Primera llamada al LLM ---------------------------------------

        self._apply_sliding_window()
        response = self._llm.chat(
            messages=self.messages,
            tools=tools,
            system=self._system,
        )
        self._acumular_tokens(resultado, response)

        # Contamos las llamadas ya realizadas al LLM. El tope total es `self._max_iterations`.
        llamadas = 1

        # iteramos mientras HAYA tool_calls (y no superemos el tope).
        while response.tool_calls and llamadas < self._max_iterations:

            # Registrar en el historial el turno del assistant con los tool_calls que pidio.
            self.messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in response.tool_calls
                    ],
                }
            )

            # Ejecutar cada herramienta pedida y guardar su resultado.
            for call in response.tool_calls:
                tool_output, error = self._ejecutar_tool(call)

                # El resultado (o el error) debe volver al LLM como contexto

                contenido_tool = tool_output if error is None else error
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": contenido_tool,
                    }
                )

                # Registrar exactamente un AgentStep por herramienta invocada.
                resultado.steps.append(
                    AgentStep(
                        tool_name=call.name,
                        tool_input=call.arguments,
                        tool_output=tool_output,
                        error=error,
                    )
                )

            
            # 3) Nueva llamada al LLM con el historial actualizado.
            self._apply_sliding_window()
            response = self._llm.chat(
                messages=self.messages,
                tools=tools,
                system=self._system,
            )
            self._acumular_tokens(resultado, response)
            llamadas += 1

        #Guardamos en mensajes la ultima respuesta del LLM
        self.messages.append(
                {
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [
                        {
                            "id": call.id,
                            "function": {
                                "name": call.name,
                                "arguments": call.arguments,
                            },
                        }
                        for call in response.tool_calls
                    ],
                }
            )

        # Respuesta final: el último `content`.
        resultado.answer = response.content or ""
        return resultado
    
    def _apply_sliding_window(self) -> None:
        """Mantiene el primer turno y elimina turnos completos antiguos."""

        while len(self.messages) > self._max_history_messages:

            # Si solo queda el primer turno no hay nada más para borrar.
            if len(self.messages) <= 2:
                break

            # El segundo turno siempre empieza en el segundo mensaje "user". Va a ser mayor a 1 porq el primer turno por lo menos va a ser "user-asistant"
            start = 1

            # Buscar el siguiente mensaje de usuario
            end = len(self.messages)
            for i in range(start + 1, len(self.messages)):
                if self.messages[i]["role"] == "user":
                    end = i
                    break

            # Elimina todo el turno
            del self.messages[start:end]

    def _ejecutar_tool(self, call: ToolCall) -> tuple[str | None, str | None]:
        """Ejecuta una herramienta de forma segura.

        Devuelve una tupla `(tool_output, error)`:
          - En éxito: `(salida_str, None)`.
          - En fallo: `(None, mensaje_de_error)`.

        Captura los tres modos de fallo posibles para que `run` nunca lance
        excepción:
          1. Herramienta inexistente (el LLM alucinó un nombre).
          2. Argumentos que no son JSON válido.
          3. Excepción al ejecutar el callable de la herramienta.
        """
        # 1) Herramienta desconocida.
        if call.name not in self._tools:
            return None, f"Herramienta desconocida: '{call.name}'."

        # 2) Parseo de argumentos (vienen como string JSON).
        try:
            args = json.loads(call.arguments) if call.arguments else {}
        except json.JSONDecodeError as exc:
            return None, f"Argumentos JSON inválidos para '{call.name}': {exc}."

        # 3) Ejecución del callable. Cualquier excepción se convierte en error
        #    registrado, sin romper el bucle del agente.
        try:
            salida = self._tools[call.name](**args)
            return str(salida), None
        except Exception as exc:  # noqa: BLE001 — robustez: capturamos todo
            return None, f"Error al ejecutar '{call.name}': {exc}."

    @staticmethod
    def _acumular_tokens(resultado: AgentResult, response: LLMResponse) -> None:
        """Suma los tokens de un `LLMResponse` al `AgentResult`.

        Los contadores quedan en None mientras ningún `LLMResponse` reporte
        tokens; en cuanto uno reporta, se inicializan en 0 y se acumulan
        (tratando los None por respuesta como 0). Esto cumple el contrato de
        `AgentResult` descrito en `mia_agents/types.py`.
        """
        if response.input_tokens is not None:
            resultado.input_tokens = (resultado.input_tokens or 0) + response.input_tokens
        if response.output_tokens is not None:
            resultado.output_tokens = (
                resultado.output_tokens or 0
            ) + response.output_tokens

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
