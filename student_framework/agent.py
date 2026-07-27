"""Implementación de su agente.

Completen `register_tool` y `run` para el Milestone 1.
En el Milestone 2 amplíen `MyAgent` para que sea estatal y respete
`max_history_messages`.

Los tests de conformidad en `tests/conformance/test_m1.py` y
`test_m2.py` describen con precisión qué comportamientos deben funcionar
— léanlos antes de empezar.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from mia_agents.protocols import LLMClient
from mia_agents.types import AgentResult, AgentStep, LLMResponse, ToolCall, ToolSchema
from mia_agents.tool_schema import final_result_tool_schema,FINAL_RESULT_TOOL_NAME
import json

# ---------------------------------------------------------------------------
# Resiliencia: clasificación de errores transitorios
# ---------------------------------------------------------------------------

# Marcadores (case-insensitive) que identifican fallos transitorios en el
# nombre de la excepción o en su mensaje. Cubren timeouts, rate limits /
# throttling y errores 5xx de los proveedores (Bedrock lanza ClientError con
# códigos como "ThrottlingException" o "ServiceUnavailableException"; los
# clientes HTTP suelen incluir el status code en el mensaje).
_MARCADORES_TRANSITORIOS = (
    "timeout",
    "timed out",
    "throttl",
    "rate limit",
    "ratelimit",
    "too many requests",
    "429",
    "500",
    "502",
    "503",
    "504",
    "service unavailable",
    "serviceunavailable",
    "internal server error",
    "internalserror",
    "connection",
    "temporarily",
)


def _es_error_transitorio(exc: Exception) -> bool:
    """Decide si una excepción amerita reintento.

    Transitorios: timeouts, errores de red/conexión, rate limits y 5xx.
    Cualquier otro error (bug de programación, argumentos inválidos, 4xx
    que no sea rate limit) NO se reintenta: debe aflorar limpio.
    """
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    texto = f"{type(exc).__name__} {exc}".lower()
    return any(marca in texto for marca in _MARCADORES_TRANSITORIOS)

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
        max_retries: int = 3,
        retry_backoff_base: float = 0.5,
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
        max_retries : int
            Cantidad máxima de reintentos ante fallos transitorios
            (timeouts, 5xx, rate limits) en llamadas al LLM y a las tools.
        retry_backoff_base : float
            Espera base (en segundos) del backoff exponencial entre
            reintentos: base * 2**intento. Poner 0 en tests.
        """
        self._llm = llm_client
        self._system = system_prompt
        self._max_iterations = max_iterations
        self._max_history_messages = max_history_messages
        self._max_retries = max_retries
        self._retry_backoff_base = retry_backoff_base
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

        response = self._chat_con_reintentos(tools)
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
            response = self._chat_con_reintentos(tools)
            self._acumular_tokens(resultado, response)
            llamadas += 1

        # Guardamos en el historial la última respuesta del LLM. Solo
        # incluimos `tool_calls` si realmente los hay (si el bucle terminó
        # por max_iterations la respuesta podría traer tool_calls sin
        # ejecutar; los omitimos para no dejar tool_calls huérfanos, sin
        # su mensaje `tool` de respuesta, en el historial).
        self.messages.append(
            {
                "role": "assistant",
                "content": response.content or "",
            }
        )

        # Respuesta final: el último `content`.
        resultado.answer = response.content or ""
        return resultado

    def _chat_con_reintentos(self, tools: list[ToolSchema] | None) -> LLMResponse:
        """Llama a `chat` con la ventana de historial y reintentos."""
        ventana = self._windowed_messages()
        return self._con_reintentos(
            lambda: self._llm.chat(
                messages=ventana,
                tools=tools,
                system=self._system,
            )
        )

    def _windowed_messages(self) -> list[dict[str, Any]]:
        """Devuelve una COPIA del historial recortada al presupuesto.

        Estrategia de memoria: sliding window por recencia que además
        preserva el objetivo. Conservamos el primer mensaje de usuario (que
        suele contener la tarea/goal) y la cola más reciente; descartamos los
        turnos intermedios. Justificación: el contexto útil se concentra en
        los últimos turnos, pero el goal inicial debe seguir presente para
        que el agente no "olvide" qué está resolviendo en conversaciones
        largas.

        Invariantes que garantiza:
          - La lista devuelta nunca supera `max_history_messages`.
          - El primer mensaje de usuario (el goal) se conserva cuando el
            historial supera el presupuesto, salvo que deba ceder su lugar
            para garantizar la recencia con presupuestos mínimos.
          - El mensaje de usuario más reciente SIEMPRE está incluido
            (recencia), aunque el presupuesto sea menor que el turno actual.
          - La ventana nunca arranca con mensajes `tool` o `assistant`
            huérfanos (siempre empieza en un mensaje `user`), para no
            enviar tool_calls sin contexto a proveedores estrictos.

        Devuelve una lista NUEVA: el historial interno (`self.messages`)
        nunca se comparte mutable con el cliente LLM.
        """
        n = self._max_history_messages
        msgs = self.messages
        total = len(msgs)

        if total <= n:
            ventana = list(msgs)
        else:
            # Cola más reciente dentro del presupuesto.
            ventana = list(msgs[total - n:])

            # Goal: preservamos el primer mensaje de usuario (suele contener la
            # tarea). Si no cae ya dentro de la cola, lo anteponemos ocupando un
            # lugar del presupuesto (patrón `preserve_first_user`).
            idx_first_user = next(
                (i for i, m in enumerate(msgs) if m.get("role") == "user"),
                None,
            )
            if idx_first_user is not None and idx_first_user < total - n:
                ventana = [msgs[idx_first_user]] + ventana[1:]

            # Recencia (invariante dura): el último mensaje de usuario SIEMPRE
            # está. Si un turno actual larguísimo dejó la cola sin él, lo
            # forzamos —aun a costa del goal, porque la recencia tiene prioridad.
            idx_last_user = next(
                (i for i in range(total - 1, -1, -1)
                 if msgs[i].get("role") == "user"),
                None,
            )
            if idx_last_user is not None and msgs[idx_last_user] not in ventana:
                ventana = [msgs[idx_last_user]] + list(msgs[total - (n - 1):])

        # La ventana siempre empieza en un mensaje de usuario: descartamos
        # mensajes `tool`/`assistant` que quedaron sin su turno completo.
        while ventana and ventana[0].get("role") != "user":
            ventana.pop(0)

        return ventana

    def _con_reintentos(self, fn: Callable[[], Any]) -> Any:
        """Ejecuta `fn` reintentando solo ante fallos transitorios.

        Reintenta hasta `max_retries` veces con backoff exponencial
        (base * 2**intento). Los errores NO transitorios se propagan de
        inmediato, sin reintentos. Si se agotan los reintentos, se propaga
        el último error transitorio.
        """
        ultimo_error: Exception | None = None
        for intento in range(self._max_retries + 1):
            try:
                return fn()
            except Exception as exc:  # noqa: BLE001 — clasificamos abajo
                if not _es_error_transitorio(exc):
                    raise
                ultimo_error = exc
                if intento < self._max_retries and self._retry_backoff_base > 0:
                    time.sleep(self._retry_backoff_base * (2 ** intento))
        assert ultimo_error is not None
        raise ultimo_error

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

        # 3) Ejecución del callable, con reintentos ante fallos transitorios
        #    (p. ej. una tool que hace red y sufre un timeout). Cualquier
        #    excepción restante se convierte en error registrado, sin romper
        #    el bucle del agente.
        try:
            salida = self._con_reintentos(lambda: self._tools[call.name](**args))
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
        """Pide al LLM una respuesta validada contra `schema`.

        Obligatorio: herramienta sintética `final_result`. El agente ofrece esa tool al LLM, valida los `arguments` del
        `tool_call` y reintenta con contexto de reparación si el modelo responde con texto libre o con argumentos inválidos.

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

        messages = [
        {
            "role": "user",
            "content": prompt,
        }]

        tool = final_result_tool_schema(schema)

        for attempt in range(max_repair_attempts + 1):

            # Solo exponemos `final_result`: acá no queremos que el LLM use
            # otras tools, queremos forzar la salida estructurada. La llamada
            # va envuelta en reintentos ante fallos transitorios.
            response = self._con_reintentos(
                lambda: self._llm.chat(
                    messages=messages,
                    tools=[tool],
                    system=self._system,
                )
            )

            # CASO 1: modelo responde con texto libre
            if not response.tool_calls:

                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "La respuesta no cumple el formato requerido. Se debe utilizar unicamente la herramienta final_result."
                        ),
                    }
                )
                continue


            # CASO 2: Buscamos la tool final_result. Se termina solo cuando llega un `tool_call` a `final_result`
            final_call = None

            for call in response.tool_calls:
                if call.name == FINAL_RESULT_TOOL_NAME:
                    final_call = call
                    break


            if final_call is None:

                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {
                                "id": c.id,
                                "function": {
                                    "name": c.name,
                                    "arguments": c.arguments,
                                },
                            }
                            for c in response.tool_calls
                        ],
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Debes finalizar utilizando la herramienta final_result."
                        ),
                    }
                )

                continue


            # Caso 3: Se responde con argumentos invalidos

            try:
                arguments = json.loads(final_call.arguments)

                return schema.model_validate(arguments)

            except Exception as exc:

                last_error = str(exc)

                messages.append(
                    {
                        "role": "assistant",
                        "content": response.content or "",
                        "tool_calls": [
                            {
                                "id": final_call.id,
                                "function": {
                                    "name": final_call.name,
                                    "arguments": final_call.arguments,
                                },
                            }
                        ],
                    }
                )

                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Los argumentos enviados a final_result "
                            "no cumplen el schema esperado.\n"
                            f"Error: {last_error}\n"
                            "Corrige la respuesta usando final_result."
                        ),
                    }
                )

        raise RuntimeError(f"No se pudo obtener una respuesta estructurada valida")

