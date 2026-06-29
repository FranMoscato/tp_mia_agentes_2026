# Informe — Milestone 1: Bucle del agente y herramientas

**Materia:** Agentes — MIA (UdeSA)
**Entrega:** Milestone 1
**Código:** `student_framework/`

---

## Índice

1. [Resumen de la entrega](#1-resumen-de-la-entrega)
2. [Diagrama de arquitectura](#2-diagrama-de-arquitectura)
3. [Diseño de la interfaz de herramientas](#3-diseño-de-la-interfaz-de-herramientas)
4. [Las tres herramientas obligatorias](#4-las-tres-herramientas-obligatorias)
5. [El bucle del agente: terminación y límites](#5-el-bucle-del-agente-terminación-y-límites)
6. [Decisiones de diseño documentadas](#6-decisiones-de-diseño-documentadas)
7. [Manejo de errores y robustez](#7-manejo-de-errores-y-robustez)
8. [Estrategia de pruebas](#8-estrategia-de-pruebas)
9. [Cómo ejecutar](#9-cómo-ejecutar)
10. [Trazabilidad contrato → implementación](#10-trazabilidad-contrato--implementación)
11. [Limitaciones conocidas](#11-limitaciones-conocidas)

---

## 1. Resumen de la entrega

El objetivo del M1 es un agente que registra herramientas, las expone al LLM,
ejecuta las que el modelo pide, observa los resultados y continúa hasta producir
una respuesta final, sin bucles infinitos.

**Mapa de archivos (lo que implementamos vs. lo que es fijo):**

| Archivo | Rol | ¿Editable? |
|---|---|---|
| `student_framework/__init__.py` | `build_agent`: punto de entrada, registra las 3 tools | **Nuestro** |
| `student_framework/agent.py` | `MyAgent`: `register_tool` + `run` (el bucle) | **Nuestro** |
| `student_framework/tools/calculator.py` | Herramienta 1: calculadora | **Nuestro** |
| `student_framework/tools/file_reader.py` | Herramienta 2: lector de archivos | **Nuestro** |
| `student_framework/tools/word_counter.py` | Herramienta 3 (libre): contador de palabras | **Nuestro** |
| `tests/test_escenarios_propios.py` | Escenarios propios (≥2 herramientas) | **Nuestro** |
| `mia_agents/` | Tipos, protocolos y `LLMClient` de la cátedra | FIJO |
| `tests/conformance/test_m1.py` | Tests de conformidad | FIJO |

**Estado:** los 5 tests de conformidad de M1 y los 4 escenarios propios pasan
(9/9 en verde).

---

## 2. Diagrama de arquitectura

![Arquitectura M1](docs/arquitectura_m1.png)

> La imagen se genera con `python scripts/generar_diagrama_arquitectura.py`
> (matplotlib). Es declarativa: si cambia la arquitectura, se edita el script y
> se regenera, manteniéndola sincronizada con el código.

**Componentes:**

- **`build_agent(config)`** — único punto de entrada público. Construye el
  `MyAgent`, inyecta el `LLMClient` (el del `config` si lo hay, o uno del
  entorno) y registra las tres herramientas. Tanto la CLI como los tests de
  conformidad entran por acá.
- **`MyAgent`** — el corazón del framework. Mantiene dos diccionarios paralelos
  (`_tools`: nombre → callable; `_schemas`: nombre → `ToolSchema`) y expone
  `register_tool` y `run`.
- **`LLMClient` (FIJO)** — abstrae el proveedor (Bedrock, Ollama o el
  `MockLLMClient` de los tests). Recibe `ToolSchema` y los traduce al formato
  nativo de cada proveedor con `to_llm_spec()`. El agente nunca habla con el
  proveedor directamente.
- **Herramientas** — un callable + un `ToolSchema` por archivo en `tools/`.

**Flujo de datos:** el agente solo intercambia con el `LLMClient` objetos
normalizados (`messages`, `tools`, `LLMResponse`); el `LLMClient` se encarga de
la traducción específica de cada proveedor. Esto es lo que permite que los tests
sustituyan el cliente real por un mock sin tocar el agente.

---

## 3. Diseño de la interfaz de herramientas

### 3.1 Definición de una herramienta

Cada herramienta es un `callable` tipado. La descripción para el LLM sale del
**docstring**; la de cada argumento, de `Annotated[..., Field(description=...)]`:

```python
from typing import Annotated
from pydantic import Field
from mia_agents.types import ToolSchema

def calculadora(
    operando_a: Annotated[float, Field(description="Primer operando numérico.")],
    operando_b: Annotated[float, Field(description="Segundo operando numérico.")],
    operador:   Annotated[str,   Field(description="Uno de: '+', '-', '*', '/', '%'.")],
) -> str:
    """Calcula una operación aritmética binaria entre dos números. ..."""
    ...

calculadora_schema = ToolSchema.from_callable(calculadora)
```

### 3.2 De la firma al JSON Schema (`ToolSchema.from_callable`)

`from_callable` **deriva el JSON Schema automáticamente** desde la firma (vía
Pydantic) — nunca se escribe a mano (lo exige el enunciado). Para `calculadora`
produce:

```json
{
  "name": "calculadora",
  "description": "Calcula una operación aritmética binaria entre dos números. ...",
  "parameters": {
    "type": "object",
    "properties": {
      "operando_a": {"type": "number", "description": "Primer operando numérico."},
      "operando_b": {"type": "number", "description": "Segundo operando numérico."},
      "operador":   {"type": "string", "description": "Uno de: '+', '-', '*', '/', '%'."}
    },
    "required": ["operando_a", "operando_b", "operador"]
  }
}
```

- `name` ← `fn.__name__`.
- `description` ← docstring completo.
- `parameters` ← JSON Schema de los argumentos (tipos, descripciones, `required`).

### 3.3 Registro: qué guarda `register_tool`

```python
def register_tool(self, tool, schema):
    self._tools[schema.name] = tool       # callable, para EJECUTAR
    self._schemas[schema.name] = schema   # ToolSchema, para OFRECER al LLM
```

Se guardan **indexados por `schema.name`**: así, cuando el LLM pide una tool por
nombre, el agente resuelve el callable en O(1) y valida que exista.

### 3.4 Exposición al LLM: qué se pasa en `chat(tools=...)`

```python
tools = list(self._schemas.values()) if self._schemas else None
response = self._llm.chat(messages=messages, tools=tools, system=self._system)
```

Se pasan los **objetos `ToolSchema`** (no los callables). En cada `run` se envían
en todas las llamadas (no solo en la primera), para que el modelo pueda decidir
usar una herramienta en cualquier turno.

### 3.5 Qué hace el `LLMClient` fijo con cada esquema

El cliente llama `to_llm_spec()` sobre cada `ToolSchema` (devuelve
`{name, description, parameters}`) y lo envuelve en el formato nativo del
proveedor:

| Proveedor | Formato de la tool |
|---|---|
| **Ollama** | `{"type": "function", "function": {name, description, parameters}}` |
| **Bedrock (Converse)** | `{"toolSpec": {name, description, inputSchema: {json: parameters}}}` |

Cuando el modelo decide usar una herramienta, el cliente normaliza la respuesta a
`LLMResponse.tool_calls` (lista de `ToolCall` con `id`, `name`, `arguments`-JSON).
El agente entonces ejecuta `self._tools[name](**json.loads(arguments))`.

---

## 4. Las tres herramientas obligatorias

### 4.1 Calculadora (`calculator.py`)

- **Firma:** `(operando_a: float, operando_b: float, operador: str) -> str`.
- **Operadores:** `+`, `-`, `*`, `/` (división) y `%` (módulo). Se soportan los
  cinco para cubrir las dos versiones del enunciado (una pide `/`, la otra `%`).
- **Decisión clave:** recibe **dos operandos y un operador por separado**, NO una
  expresión. El enunciado prohíbe expresiones arbitrarias y `eval`. Una versión
  anterior usaba `ast.parse` sobre un string — eso es justamente "evaluar
  expresiones arbitrarias", así que se descartó.
- **Implementación:** un diccionario `{símbolo: lambda a, b: ...}` evita cadenas
  de `if/elif` y hace trivial validar el operador.
- **Errores controlados:** operador no soportado, y división/módulo por cero
  devuelven un string `"Error: ..."` (no lanzan excepción).

### 4.2 Lector de archivos (`file_reader.py`)

- **Firma:** `(ruta: str) -> str`.
- **Comportamiento:** lee y devuelve el contenido de un archivo de texto UTF-8.
- **E/S restringida (decisiones):**
  - Valida que el archivo **exista** y que **sea un archivo** (no un directorio).
  - **Tope de 100 KB** para no volcar un archivo enorme al contexto del LLM.
  - Solo **texto UTF-8**: un binario produce `UnicodeDecodeError`, que se captura
    y se reporta como error legible.
  - Cualquier `OSError` (permisos, etc.) también se captura.
- Nunca lanza excepción: todos los fallos vuelven como string `"Error: ..."`.

### 4.3 Contador de palabras (`word_counter.py`) — herramienta libre

- **Firma:** `(texto: str) -> str`.
- **Por qué esta:** es cómputo puro y **combina con el lector de archivos** para
  demostrar el encadenamiento de herramientas (leer un archivo → contar sus
  palabras), que es justamente lo que piden los escenarios propios.
- **Implementación:** `len(texto.split())`. `str.split()` sin argumentos colapsa
  espacios consecutivos y descarta extremos, así que cadenas vacías o con
  espacios de más dan el conteo correcto (incluido 0).

---

## 5. El bucle del agente: terminación y límites

![Bucle de run](docs/bucle_run_m1.png)

### 5.1 Condición de parada (caso normal)

El bucle de `run` itera **mientras la respuesta del LLM contenga `tool_calls`**.
Cuando el LLM responde con texto y **sin** `tool_calls`, ese `content` es la
respuesta final (`AgentResult.answer`) y el bucle termina. Es exactamente la
condición que pide el M1.

```python
while response.tool_calls and llamadas < self._max_iterations:
    # 1) registrar el turno assistant (con los tool_calls + sus id)
    # 2) ejecutar cada tool y volcar su resultado como mensaje role:"tool"
    # 3) volver a llamar al LLM
resultado.answer = response.content or ""
```

### 5.2 Tope de iteraciones (anti-bucle infinito)

Se cuenta cada llamada al LLM en `llamadas` (empieza en 1 por la primera llamada
previa al bucle). El bucle solo continúa si `llamadas < self._max_iterations`
(por defecto **10**). Así, aunque el LLM pida herramientas indefinidamente, se
hacen **como máximo `max_iterations` llamadas** y luego se corta.

### 5.3 Qué pasa al alcanzar el límite

El bucle termina aunque la última respuesta todavía pidiera herramientas. En ese
caso `response.content` puede ser `None`; se normaliza a `""` para respetar el
tipo `str` de `answer`. **`run` siempre devuelve un `AgentResult` válido** (con
los `steps` acumulados hasta ese punto), sin lanzar excepción. Lo verifica
`test_escenario_corte_por_max_iterations`.

### 5.4 Invariantes del contrato que garantiza el bucle

| Invariante (ENUNCIADO_M1) | Cómo se garantiza |
|---|---|
| Respuesta sin tools → 1 sola llamada al LLM | El `while` no se ejecuta si no hay `tool_calls` |
| `result.steps == []` si no hubo tools | Solo se agregan `steps` dentro del bucle |
| Exactamente 1 `AgentStep` por tool invocada | Un `append` por `call` en el `for` |
| 2da llamada incluye el resultado de la tool | Se agrega mensaje `role:"tool"` antes de re-llamar |
| `step.tool_output` == valor exacto del callable | `str(salida)` sin transformar |
| `step.error is None` en éxito | `_ejecutar_tool` solo devuelve error en fallo real |
| Tool desconocida no rompe | `_ejecutar_tool` la detecta y devuelve error |
| `run` no lanza con `"hola"`, `"2+2"`, `""` | Sin tools, el `while` no corre; con tools, todo capturado |

---

## 6. Decisiones de diseño documentadas

**D1 — Corte por `tool_calls`, no por `content`.** El criterio del M1 es "el LLM
respondió sin tool_calls". Iterar sobre `response.tool_calls` es directo y
robusto. (Una versión previa cortaba con `not response.content`, que falla si el
modelo devuelve texto y `tool_calls` juntos.)

**D2 — `max_iterations` cuenta llamadas al LLM.** El enunciado dice "dejar de
llamar al LLM cuando llega a esa cantidad de llamadas". Por eso el contador es de
**llamadas a `chat`**, no de herramientas ejecutadas. Empieza en 1 (la primera
llamada ya ocurrió antes del bucle) y el `while` exige `llamadas < max`.

**D3 — `run` nunca lanza excepción.** Toda la ejecución de herramientas se aísla
en `_ejecutar_tool`, que captura los tres modos de fallo (tool inexistente, JSON
inválido, excepción del callable) y los devuelve como `(None, error)`. El bucle
nunca ve una excepción. Esto cumple "robustez" y "entradas básicas" del contrato.

**D4 — El error vuelve al LLM.** Ante un fallo, además de registrar el
`AgentStep.error`, se agrega un mensaje `role:"tool"` con el texto del error. Así
el modelo puede **recuperarse** en el siguiente turno (lo demuestra
`test_escenario_recuperacion_ante_tool_desconocida`).

**D5 — Propagar el `id` del `tool_call`.** En el mensaje `assistant` incluimos
`{"id": call.id, ...}` y en el mensaje `tool` repetimos `tool_call_id=call.id`.
Para el `MockLLMClient` da igual, pero **Bedrock (Converse) exige que cada
`toolResult` referencie el `toolUseId` de su `toolUse`**; sin el `id` el
`LLMClient` genera UUIDs aleatorios que no coinciden y la conversación real
falla. Es una mejora de robustez para el uso contra proveedores reales (CLI/M3).

**D6 — `arguments` se pasa como string JSON.** En el mensaje `assistant`
guardamos `call.arguments` tal cual (string). El `LLMClient` ya sabe convertirlo
a dict (`_arguments_to_dict`) para cada proveedor; no lo pre-parseamos para evitar
doble manejo y posibles inconsistencias.

**D7 — Acumulación de tokens fiel al contrato.** `input_tokens`/`output_tokens`
quedan en `None` mientras ningún `LLMResponse` reporte tokens; en cuanto uno
reporta, se inicializan en 0 y se acumulan (tratando los `None` por respuesta como
0). Es lo que describe el docstring de `AgentResult`. (Una versión previa nunca
acumulaba por un bug: inicializaba en 0 y la guarda `if a and b` daba siempre
falso.)

**D8 — Éxito = el callable no lanzó.** Si la herramienta corre sin excepción, su
string de retorno es `tool_output` y `error=None`, **aunque ese string empiece
con `"Error:"`**. El contrato dice "`error is None` cuando la ejecución fue
exitosa": un string de error que la herramienta *devuelve* es contenido válido,
no un fallo de ejecución. (Una versión previa usaba `startswith("Error:")` como
heurística; se descartó por frágil.)

**D9 — System prompt en español, conservador.** El prompt instruye usar
herramientas solo cuando sean necesarias y responder en español. No fuerza el uso
de herramientas para no romper el caso "saludo → respuesta directa sin tools".

**D10 — Una herramienta por archivo.** Sigue la convención del scaffold y
mantiene cada tool con su `ToolSchema.from_callable` al lado, fácil de registrar
y de testear aislada.

**D11 — Calculadora: soportar `/` y `%` a la vez.** Circulan dos versiones del
enunciado que difieren en el operador de la calculadora: una pide `+ - * /`
(división) y la otra `+ - * %` (módulo). Para no depender de cuál use la
corrección, la calculadora soporta **los cinco** operadores (`+`, `-`, `*`, `/`,
`%`). Es un superconjunto: cualquier verificación de "debe soportar X" pasa, y se
mantiene la regla de "solo operación binaria, sin expresiones". División y módulo
por cero se interceptan y devuelven `"Error: ..."` sin lanzar excepción.

---

## 7. Manejo de errores y robustez

`_ejecutar_tool(call) -> (tool_output, error)` centraliza los tres modos de fallo:

| Caso | Detección | Resultado |
|---|---|---|
| Herramienta inexistente | `call.name not in self._tools` | `(None, "Herramienta desconocida: ...")` |
| Argumentos no-JSON | `json.JSONDecodeError` | `(None, "Argumentos JSON inválidos: ...")` |
| Excepción del callable | `except Exception` | `(None, "Error al ejecutar ...: ...")` |
| Éxito | — | `(str(salida), None)` |

Además, **cada herramienta** maneja sus propios errores de dominio devolviendo
strings `"Error: ..."` (operador inválido, módulo por cero, archivo inexistente,
binario, etc.), de modo que ni siquiera llegan a lanzar.

---

## 8. Estrategia de pruebas

**Conformidad (FIJO):** `tests/conformance/test_m1.py` — 5 tests que verifican el
contrato mínimo con el `MockLLMClient`.

**Escenarios propios:** `tests/test_escenarios_propios.py` — 4 escenarios
deterministas (sin API), guionando las respuestas del mock:

1. **Leer archivo + contar palabras** — dos herramientas encadenadas.
2. **Calculadora + contador** — dos herramientas distintas en una conversación.
3. **Recuperación ante tool desconocida** — robustez: el LLM alucina una tool y
   se recupera con una real.
4. **Corte por `max_iterations`** — el LLM nunca para; el agente corta en 10
   llamadas y devuelve un `AgentResult` válido.

Resultado: **9/9 tests en verde**.

---

## 9. Cómo ejecutar

```bash
# Tests (no requieren clave de API; usan MockLLMClient)
pytest tests/conformance/test_m1.py
pytest tests/test_escenarios_propios.py

# Agente contra un LLM real (requiere proveedor configurado, ver README)
python -m mia_agents.cli run --module student_framework \
  --message "¿Cuánto es 17 * 23? Usá la calculadora."

# Regenerar los diagramas del informe (requiere matplotlib)
python scripts/generar_diagrama_arquitectura.py
python scripts/generar_diagrama_bucle.py
```

---

## 10. Trazabilidad contrato → implementación

| Requisito (ENUNCIADO_M1) | Dónde se cumple |
|---|---|
| `build_agent(config)` devuelve un `Agent` | `student_framework/__init__.py` |
| Usa `config["llm_client"]` si está | `__init__.py` (`config.get("llm_client") or from_env()`) |
| `register_tool(callable, ToolSchema)` | `agent.py: register_tool` |
| `chat(tools=...)` con esquemas (no None) | `agent.py: run` (`list(self._schemas.values())`) |
| 3 herramientas obligatorias | `tools/calculator.py`, `file_reader.py`, `word_counter.py` |
| `ToolSchema.from_callable` (sin JSON a mano) | al pie de cada archivo de tool |
| Bucle razonar→tool→observar→continuar | `agent.py: run` |
| Corte sin tool_calls / por `max_iterations` | `agent.py: run` (condición del `while`) |
| 1 `AgentStep` por tool, con `tool_output`/`error` | `agent.py: run` + `_ejecutar_tool` |
| Tool desconocida no rompe | `agent.py: _ejecutar_tool` |
| `run` no lanza con `""`, `"hola"`, `"2+2"` | bucle + `_ejecutar_tool` |
| Informe (4 secciones) | este documento |
| Escenarios con ≥2 herramientas | `tests/test_escenarios_propios.py` |

---

## 11. Limitaciones conocidas

- **Conversación de un solo turno.** `run` arranca el historial desde cero en cada
  llamada; no hay memoria entre invocaciones. La conversación multiturno y el
  respeto de `max_history_messages` son de M2 (el constructor ya acepta el
  parámetro, pero en M1 se ignora).
- **`structured_call` no implementado.** Queda como *stub* que lanza
  `NotImplementedError`; la salida estructurada con la tool sintética
  `final_result` y la reparación con reintentos son de M2.
- **Sin reintentos ante fallos transitorios del LLM.** Si `LLMClient.chat` lanza
  (p. ej. error de red), `run` no reintenta. Los reintentos resilientes son de M2.
- **Calculadora acotada a operaciones binarias.** Solo una operación entre dos
  números (`+`, `-`, `*`, `/`, `%`); sin paréntesis, precedencia ni potencia.
- **Lector de archivos restringido.** Solo texto UTF-8 de hasta 100 KB; binarios o
  archivos más grandes devuelven error. Usa la ruta tal cual (no resuelve un
  directorio base configurable).
- **Heurística de "respuesta final".** Un turno sin `tool_calls` se asume final;
  si un modelo devolviera texto *y* `tool_calls` juntos, se priorizan las
  `tool_calls` y se sigue iterando (comportamiento esperado para M1).
- **Tokens dependientes del proveedor.** `input_tokens`/`output_tokens` solo se
  completan si el proveedor los reporta; con `MockLLMClient` sin tokens quedan en
  `None`.
