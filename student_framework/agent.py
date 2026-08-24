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

from pydantic import BaseModel, Field

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

Sos un agente que controla un personaje dentro de una sala de escape. Tu objetivo final es ABRIR LA PUERTA PRINCIPAL y salir de la habitación.

**OBJETIVO FINAL Y PRONCIPAL: ** ABRIR LA PUERTA PRINCIPAL y salir de la habitación. 

GOLDEN RULE: Continua hasta ABRIR LA PUERTA PRINCIPAL. Abrir otros contenedores como cofres o cajones no es cumplir tu objetivo.

Para lograrlo, debés explorar la habitación, identificar objetos, examinarlos, recoger los objetos necesarios y utilizarlos correctamente.

## REGLAS PRINCIPALES

1) DEBÉS actuar paso a paso.
2) NUNCA inventes información.
3) NUNCA inventes IDs.
4) NUNCA uses una herramienta si no tenés la información necesaria para hacerlo.
5) SIEMPRE debes respetar los schemas presentados de las tools y no proporcionar argumentos de mas o de menos para utilizarlas.

## ORDEN OBLIGATORIO DE ACCIONES

Al comenzar una partida, seguí SIEMPRE este orden:

1. Primero ejecutá `look` y ninguna otra herramienta en ese primer turno.
2. ESPERÁ el resultado de `look`.
3. Leé cuidadosamente los objetos y sus IDs que aparecen en el resultado.
4. Solo después de recibir el resultado de `look`, podés decidir qué objeto examinar.
5. Para examinar un objeto, usá `examine` y utilizá EXACTAMENTE el ID que apareció en un resultado anterior.
6. Si un objeto debe ser recogido, primero asegurate de conocer su ID y después ejecutá `take`.
7. Solo después de ejecutar `take` exitosamente podés utilizar ese objeto con `use`.
8. Continuá explorando y resolviendo los pasos necesarios hasta abrir la puerta principal.


## REGLA ABSOLUTA DE EJECUCIÓN SECUENCIAL

NUNCA generes múltiples tool_calls en una misma respuesta junto con un ´look´.

Ejemplo INCORRECTO:

1)tool_calls = [
    look(),
    go(...),
    look(),
    examine(...),
    take(...)
]

Ejemplo CORRECTO:

1) tool_calls = [
    look()
]

2) Después de recibir el resultado de look, generás UNA SOLA siguiente acción.

tool_calls = [
    go(direction="norte")
]

3)Después de recibir el resultado de go, generás UNA SOLA siguiente acción.

tool_calls = [
    look()
]

Y así sucesivamente.

## REGLA CRÍTICA SOBRE `look`

Si todavía NO ejecutaste `look` en la partida:

* La ÚNICA herramienta que podés ejecutar es `look`.
* NO ejecutes `examine`.
* NO ejecutes `take`.
* NO ejecutes `use`.
* NO ejecutes ninguna otra herramienta.

Primero `look`, después de recibir el resultado de `look`, recién podés continuar. 

NOTA: si se devuelven salidas, puedes utilizar la tool go para explorar otros ambientes.


## REGLA CRÍTICA SOBRE LOS IDs

Los objetos tienen IDs específicos, por ejemplo:

`[id: <id_real>]`

Los IDs son OBLIGATORIOS para las herramientas que los requieren y SOLO podés utilizar un ID si ese ID apareció explícitamente en un resultado anterior de una herramienta.

ESTÁ PROHIBIDO:

* inventar un ID;
* modificar un ID;
* adivinar un ID;
* usar el nombre del objeto en lugar de su ID;
* usar un ID que nunca apareció en los resultados anteriores.

Ejemplo:

Si `look` devuelve:

`objeto [id: <id_real>]`

entonces podés usar:

`take(item="<id_real>")`

Pero NO podés usar:

`take(item="objeto")` --> ese ID nunca fue proporcionado.

## REGLA SOBRE `examine`

Solo podés ejecutar `examine` sobre objetos cuyo ID hayas obtenido previamente mediante una herramienta.

`examine` SIEMPRE recibe el parámetro:

`target`

Ejemplo correcto:

`examine(target="<id_real>")`

NUNCA uses:

`examine(objeto="<id_real>")`

**Nota importante**: Si el objeto de un objeto cambia, por ejemplo un cofre que se abre, debes examinarlo otra vez.

## REGLA SOBRE `take`

`take` SIEMPRE recibe el parámetro:

`item`

Debés utilizar el ID exacto del objeto. Ejemplo: `take(item="<id_real>")`

NUNCA uses: `take(objeto="<id_real>")` --> no existe el parametro objeto

## REGLA SOBRE `use`

`use` requiere EXACTAMENTE dos parámetros:

`item`
`target`

Ejemplo:

`use(item="<id_real>", target="<id_real2>")` 

El `item` debe ser un objeto que hayas recogido exitosamente con `take`. **NO** podés utilizar un objeto que simplemente hayas visto o examinado.

## REGLA CRÍTICA SOBRE `go`

* La herramienta `go` SOLO puede utilizar como parámetro una salida que haya sido devuelta explícitamente por la herramienta `look` o por un resultado anterior de la propia herramienta `go`.
* NUNCA inventes, adivines o modifiques el nombre de una salida.
* Utilizá EXACTAMENTE el nombre de la salida proporcionada por la herramienta.
* Después de utilizar `go`, ejecutá `look` nuevamente antes de interactuar con cualquier objeto.
* Solo podés interactuar con objetos que estén en el mismo cuarto en el que te encontrás actualmente.
* NO podés utilizar sobre, examinar o tomar objetos que viste en otro cuarto mientras no estés nuevamente en ese cuarto.
* Utilizá `look` para identificar las salidas y los objetos disponibles en tu ubicación actual.

### ORDEN OBLIGATORIO

`look`
↓
identificar salidas
↓
si existe una salida no explorada → `go`
↓
`look`
↓
identificar objetos y nuevas salidas
↓
explorar el ambiente
↓
repetir

Solo cuando hayas explorado los ambientes relevantes y no queden salidas nuevas por explorar, intentá abrir la puerta principal.

### REGLA ABSOLUTA

SI NO CONOCÉS UNA SALIDA POR UN RESULTADO ANTERIOR DE `look` O `go`, NO PODÉS UTILIZARLA CON `go`.

NO INVENTES NOMBRES DE SALIDAS.



## REGLA SOBRE INVENTARIO

1) Ver un objeto NO significa que lo poseas.
2) Examinar un objeto NO significa que lo poseas.
3) Solo poseés un objeto después de ejecutar exitosamente: `take(item="ID")`


Nunca hagas:

VER → USAR

ni:

EXAMINAR → USAR

sin haber ejecutado exitosamente `take`.


## REGLA SOBRE LLAVES Y CERRADURAS

Las llaves normalmente se utilizan para abrir cerraduras.

Si encontrás una llave y una cerradura, prestá atención a características como:

* color;
* descripción;
* relación entre los objetos.

Una llave suele corresponder a una cerradura del mismo color.

Sin embargo, NO asumas que una llave sirve para una cerradura únicamente por su color. Primero examiná los objetos cuando sea necesario y utilizá la información proporcionada por las herramientas.


## RESTRICCIONES ABSOLUTAS

1. `look` debe ser la primera herramienta utilizada.
2. No uses ninguna otra herramienta antes de recibir el resultado de `look`.
3. No inventes IDs.
4. Solo uses IDs que hayan aparecido explícitamente en resultados anteriores.
5. No uses objetos que no hayas recogido con `take`.
6. `examine` usa `target`.
7. `take` usa `item`.
8. `use` usa `item` y `target`.
9. No ejecutes varias acciones innecesarias a la vez.
10. Después de cada herramienta, analizá su resultado antes de decidir la siguiente acción.
11. Tu objetivo es abrir la puerta principal, no simplemente explorar indefinidamente.
12. Si ya tenés suficiente información para realizar una acción válida, ejecutala.
13. Si una herramienta devuelve un error, analizá el error y corregí la acción antes de continuar.
14. Si hay otras salidas debes explorar otros ambientes antes de intentar abrir la puerta. IMPORTANTE.
"""


# ---------------------------------------------------------------------------
# Summarizer de estado de partida (opcional, se activa con use_summarizer)
# ---------------------------------------------------------------------------
# Estructura, prompts y lógica de resumen basados en la rama de trabajo del
# equipo. Acá quedan detrás del flag `use_summarizer` (default False), de modo
# que M1/M2 y el modo ReAct puro no pagan ningún costo cuando está apagado.


class GameState(BaseModel):
    """Estado estructurado de la partida que el summarizer mantiene al día."""

    inventory: list[str] = Field(default_factory=list)
    current_location: str | None = None
    visited_locations: list[str] = Field(default_factory=list)
    succesful_actions: list[str] = Field(default_factory=list)
    failed_actions: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    known_exits: list[str] = Field(default_factory=list)


# Se ANEXA al system prompt solo cuando el summarizer está activo: le explica al
# agente que va a recibir un bloque "ESTADO ACTUAL DE LA PARTIDA" y qué contiene.
SUMMARIZER_PROMPT_ADDENDUM = """
15. Presta atencion al 'ESTADO ACTUAL DE LA PARTIDA' ya que tiene informacion util para escapar. Contine una lista de acciones realizadas, consideralas antes de proponer una siguiente accion.

SCHEMA DE 'ESTADO ACTUAL DE LA PARTIDA':

    -inventory: lista de objetos que tomamos (hay que agregarlos SOLO cuando la tool/function ´take´ se realiza con exito. NO agregues un objeto si solo se menciono como resultado de ´look´ o de ´examine´)
    -current_location: ubicacion actual
    -visited_locations: lugares que visitamos (devueltos por tool ´look´)
    -succesful_actions: lista de tools ejecutadas en la partida con exito. (esto seria las tools que utilizamos y su resultado). Se deben aggregar elementos, pero no borrar los anteriores.
    -failed_actions: lista de tools ejecutadas en la partida SIN exito. (esto seria las tools que utilizamos y su resultado). Se deben aggregar elementos, pero no borrar los anteriores.
    -observations: Objetos que sabemos que existen y donde estan
    -known_exits: salidas que se pueden tomar y desde donde
"""


MEMORY_SYSTEM_PROMPT = """
        Sos un sistema de memoria para un agente que resuelve una sala de escape.

        Tu única función es actualizar el estado estructurado de la partida.

        NO tomes decisiones.
        NO ejecutes herramientas.
        NO propongas acciones.
        NO inventes información.

        Recibís:
        1. un estado anterior;
        2. uno o más eventos producidos por herramientas reales.

        Schma:
        -inventory: lista de objetos que tomamos (hay que agregarlos SOLO cuando la tool/function ´take´ se realiza con exito. NO agregues un objeto si solo se menciono como resultado de ´look´ o de ´examine´)
        -current_location: ubicacion actual
        -visited_locations: lugares que visitamos (devueltos por tool ´look´)
        -succesful_actions: lista de tools ejecutadas en la partida con exito. (esto seria las tools que utilizamos y su resultado). Se deben aggregar elementos, pero no borrar los anteriores.
        -failed_actions: lista de tools ejecutadas en la partida SIN exito. (esto seria las tools que utilizamos y su resultado). Se deben aggregar elementos, pero no borrar los anteriores.
        -observations: Objetos que sabemos que existen y donde estan
        -known_exits: salidas que se pueden tomar y desde donde


        Debés devolver el estado COMPLETO actualizado mediante la herramienta final_result.

        Reglas:

        - look:  registrar la ubicación actual, objetos visibles, sus IDs y salidas.
        - examine:   registrar la información descubierta sobre el objeto.
        - take exitoso:   agregar el objeto al inventario.
        - take fallido: no  agregar el objeto al inventario.
        - go exitoso: actualizar la ubicación actual y registrar el movimiento.
        - go fallido: no cambiar la ubicación.
        - use: registrar la acción y si tuvo éxito o falló.
        - Conservar acciones fallidas.
        - Nunca inventar IDs.
        - Nunca inventar objetos.
        - Nunca inventar ubicaciones.
        - Nunca inventar salidas.
        - Mantener toda la información previa que siga siendo válida.
        - NUNCA agregar un objeto al inventario si no se realizo un ´take´
        """


class MyAgent:
    def __init__(
        self,
        llm_client: LLMClient,
        system_prompt: str = SYSTEM_PROMPT,
        max_iterations: int = 20,
        max_history_messages: int = 50,
        max_retries: int = 3,
        retry_backoff_base: float = 0.5,
        use_summarizer: bool = False,
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
        use_summarizer : bool
            Si es True, antes de cada llamada al LLM se re-deriva un
            `GameState` estructurado (con una llamada LLM extra) y se inyecta
            como contexto. Es la memoria "resumida" para M3. Por defecto está
            APAGADO: M1/M2 y el modo ReAct puro no pagan ese costo. La
            estrategia es ortogonal al tamaño de ventana (`max_history_messages`
            se configura por separado).
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

        # Summarizer de estado (M3): apagado por defecto. Cuando está activo,
        # anexamos el addendum al system prompt para que el agente sepa leer el
        # bloque "ESTADO ACTUAL DE LA PARTIDA".
        self._use_summarizer = use_summarizer
        self._state = GameState()
        if use_summarizer:
            self._system = system_prompt + SUMMARIZER_PROMPT_ADDENDUM

        # Costo del summarizer contabilizado APARTE del agente principal, para
        # que el experimento (resumen on/off) compare costos de forma justa.
        # Se reinicia en cada `run()`. El eval lee estos campos tras `run()`.
        self.memory_input_tokens = 0
        self.memory_output_tokens = 0

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

        # Costo del summarizer de ESTA corrida (ver __init__): arranca en 0.
        self.memory_input_tokens = 0
        self.memory_output_tokens = 0

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

            # Summarizer (M3): re-derivar el estado estructurado a partir de la
            # última interacción de herramientas, antes de la próxima llamada.
            if self._use_summarizer:
                self._state = self.update_memory()

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

        # Summarizer (M3): anteponemos el estado estructurado de la partida
        # como contexto. Solo cuando el flag está activo; en el modo ReAct puro
        # la ventana viaja intacta (M1/M2 no se ven afectados).
        if self._use_summarizer:
            state_message = {
                "role": "user",
                "content": (
                    "ESTADO ACTUAL DE LA PARTIDA:\n"
                    f"{self._state.model_dump_json(indent=2)}"
                ),
            }
            ventana = [state_message] + ventana

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
        preserva el objetivo. Conservamos el **turno inicial completo** (el
        primer mensaje de usuario —la tarea/goal— junto con la respuesta del
        asistente y los `tool` que le siguieron) y la cola de turnos más
        recientes; descartamos los turnos intermedios. Preservar el turno
        entero, y no solo el mensaje de usuario, mantiene la coherencia
        conversacional (nada de dos `user` seguidos ni `tool_calls` sin su
        respuesta) y respeta la alternancia de roles que exigen proveedores
        como Bedrock Converse.

        Invariantes que garantiza:
          - La lista devuelta nunca supera `max_history_messages`.
          - El turno inicial completo (el goal) se conserva cuando el
            historial supera el presupuesto, salvo que sea tan grande que
            deba cederse para garantizar la recencia.
          - El mensaje de usuario más reciente SIEMPRE está incluido
            (recencia).
          - La ventana se compone de turnos COMPLETOS: siempre empieza en un
            mensaje `user` y no deja `tool`/`assistant` huérfanos.

        Devuelve una lista NUEVA: el historial interno (`self.messages`)
        nunca se comparte mutable con el cliente LLM.
        """
        n = self._max_history_messages
        msgs = self.messages
        total = len(msgs)

        if total <= n:
            return list(msgs)

        # Índices donde arranca cada turno (los mensajes `user`).
        user_idxs = [i for i, m in enumerate(msgs) if m.get("role") == "user"]
        if not user_idxs:
            return list(msgs[total - n:])

        # Turno inicial COMPLETO (el goal): del primer `user` al segundo
        # `user` (exclusivo) — la tarea con su respuesta del asistente.
        fin_primer_turno = user_idxs[1] if len(user_idxs) > 1 else total
        first_turn = list(msgs[:fin_primer_turno])

        # Cola: el turno-boundary más antiguo cuyo bloque hasta el final entra
        # en el presupuesto restante. Así sumamos turnos COMPLETOS y
        # garantizamos el último `user` (recencia).
        espacio = n - len(first_turn)
        cola_start = next(
            (idx for idx in user_idxs
             if idx >= fin_primer_turno and total - idx <= espacio),
            None,
        )
        if cola_start is not None:
            return first_turn + list(msgs[cola_start:])

        # Turno inicial tan grande que no deja lugar a un turno reciente
        # completo: priorizamos la recencia con la cola cruda que arranque en
        # un `user`.
        ventana = list(msgs[total - n:])
        while ventana and ventana[0].get("role") != "user":
            ventana.pop(0)
        if not ventana:
            ventana = [msgs[user_idxs[-1]]]
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
        system: str | None = None,
        on_usage: Callable[[LLMResponse], None] | None = None,
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
                    system=system or self._system,
                )
            )

            # Contabilización opcional de tokens (p. ej. el summarizer suma su
            # costo APARTE del agente principal).
            if on_usage is not None:
                on_usage(response)

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

    # -----------------------------------------------------------------------
    # Summarizer de estado (M3) — solo se usa con use_summarizer=True
    # -----------------------------------------------------------------------

    def _acumular_memory_tokens(self, response: LLMResponse) -> None:
        """Suma los tokens de una llamada del summarizer a su contador aparte."""
        if response.input_tokens is not None:
            self.memory_input_tokens += response.input_tokens
        if response.output_tokens is not None:
            self.memory_output_tokens += response.output_tokens

    def _last_tool_interaction(self) -> list[dict]:
        """Obtiene el último bloque assistant(tool_calls) + tool results."""

        last_assistant_idx = None

        # Buscar desde el final el último assistant con tool_calls
        for i in range(len(self.messages) - 1, -1, -1):
            message = self.messages[i]

            if (
                message.get("role") == "assistant"
                and message.get("tool_calls")
            ):
                last_assistant_idx = i
                break

        if last_assistant_idx is None:
            return []

        events = []

        # Tomamos el assistant que realizó las tools
        assistant_message = self.messages[last_assistant_idx]

        events.append({
            "role": "assistant",
            "tool_calls": assistant_message["tool_calls"],
        })

        # Tomamos los tool results posteriores
        for message in self.messages[last_assistant_idx + 1:]:
            if message.get("role") == "tool":
                events.append({
                    "role": "tool",
                    "tool_call_id": message.get("tool_call_id"),
                    "content": message.get("content"),
                })
            else:
                # Llegamos al siguiente turno del agente
                break

        return events

    def update_memory(self) -> GameState:
        """Re-deriva el `GameState` a partir de la última interacción de tools.

        Hace una llamada LLM extra (vía `structured_call` con
        `MEMORY_SYSTEM_PROMPT`), cuyo costo se contabiliza APARTE mediante
        `_acumular_memory_tokens`. Si no hubo eventos nuevos, devuelve el
        estado sin cambios.
        """
        events = self._last_tool_interaction()

        if not events:
            return self._state

        prompt = f"""
        Actualizá el estado de una partida de escape room.

        ESTADO ACTUAL:
        {self._state.model_dump_json(indent=2)}

        ÚLTIMOS EVENTOS DE HERRAMIENTAS:
        {json.dumps(events, indent=2, ensure_ascii=False)}

        Actualizá el estado utilizando únicamente la información proporcionada.

        Reglas:

        - Devolvé el estado COMPLETO actualizado.
        - No inventes información.
        - Una acción solo es exitosa si el resultado de la tool indica que tuvo éxito.
        - Un take exitoso agrega el objeto al inventario.
        - Un take fallido NO agrega el objeto.
        - Un go exitoso actualiza current_location.
        - Un go fallido NO cambia current_location.
        - Registrá los go exitosos en movement_history.
        - Registrá las acciones realizadas en actions (tool mas objeto/s)
        - Registrá información obtenida mediante look y examine en observations. (objetos visibles y donde estan)
        - Registrá las salidas conocidas obtenidas mediante look o go.
        - Conservá las acciones fallidas en actions.
        - Conservá los IDs exactamente como aparecen.
        - No inventes IDs.
        """

        return self.structured_call(
            prompt=prompt,
            schema=GameState,
            system=MEMORY_SYSTEM_PROMPT,
            max_repair_attempts=3,
            on_usage=self._acumular_memory_tokens,
        )

