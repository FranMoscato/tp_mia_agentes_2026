# Informe — Milestone 3: Evaluación sobre salas de escape

> **Serie — el hilo del escape room.** Tres milestones hacia un agente que
> **juega y se evalúa en una sala de escape** (*gamification* como banco de
> pruebas): [M1](INFORME_M1.md) ▸ el agente y sus herramientas · [M2](INFORME_M2.md)
> ▸ memoria y robustez · **M3 ▸ evaluación en el juego**. Índice:
> [INFORMES.md](INFORMES.md).

> **Estado del documento.** Las 5 secciones están completas con datos reales de
> una corrida local (`ollama` / `qwen2.5:3b`, 8 escenarios × 3 configs × **3
> repeats** = 72 casos). Marcamos con `†` los números que se refrescan con la
> corrida en Bedrock (modelo fuerte), pendiente del lease de AWS. Las
> conclusiones ya son estables.

---

## Índice

- [Resumen](#resumen)
1. [Aproximación](#1-aproximación)
2. [Métricas](#2-métricas)
3. [Resultados](#3-resultados)
4. [Experimentos](#4-experimentos)
5. [Limitaciones y próximos pasos](#5-limitaciones-y-próximos-pasos)
- [Apéndice A — Cómo reproducir](#apéndice-a--cómo-reproducir)

---

## Resumen

Aplicamos nuestro framework de M1+M2 a un **mundo simulado tipo sala de
escape** (inspirado en ALFWorld): el agente debe abrir la puerta principal
usando cinco verbos (`look`, `examine`, `take`, `use`, `go`). Construimos una
**infraestructura de evaluación reproducible** ([`eval/run.py`](eval/run.py))
que corre el agente sobre los 8 escenarios, captura la traza completa por caso
y produce métricas cuantitativas y una dimensión cualitativa vía LLM-as-judge
([`eval/judge.py`](eval/judge.py)). Comparamos dos ejes del framework mediante
experimentos controlados —**resumen de estado on/off** y **gate determinístico
on/off**— y categorizamos los modos de fallo sobre trazas reales.

---

## 1. Aproximación

### 1.1 Reutilización del framework M1+M2

El agente de M3 es **el mismo `MyAgent`** de M1+M2, sin bifurcar. En el lenguaje
de la clase de patrones de composición, **M1+M2 son el "patrón 0" (un *augmented
LLM* —system prompt + tools + memoria— dentro de un loop ReAct con condiciones de
corte)**, y M3 no lo reemplaza: lo aplica. Es además un **agente autónomo**, no un
*workflow*, según la distinción de *Building Effective Agents* (Anthropic, 2024):
la decisión del control-flow la toma **la LLM en runtime** (elige qué tool llamar
y cuándo parar), no nuestro código. Esa es la elección correcta para la sala de
escape —un espacio **abierto y de pasos impredecibles**, donde la clase ubica a
la agencia sobre el workflow—; el precio, que asumimos, es **más varianza y
debugging más difícil** que un pipeline determinístico. Lo resolvemos registrando
las herramientas del mundo y dejando operar el bucle ReAct de M1 (sense → decide
→ act), apoyado en el estado y la memoria de M2:

- **Bucle y herramientas (M1).** El runner registra los verbos del mundo con
  `agent.register_tool(...)` ([`mia_world/cli.py`](mia_world/cli.py),
  [`eval/run.py`](eval/run.py)). El agente los expone al LLM en cada llamada y
  ejecuta el `tool_call` elegido. Los **errores de las herramientas vuelven
  como observaciones** (no rompen el bucle), lo que permite que el modelo
  corrija sobre la marcha —clave en un dominio donde equivocarse de llave o de
  ID es esperable.
- **Estado y memoria (M2).** La sala de escape es un problema **estado-full**:
  lo que se puede hacer depende de lo ya observado, tomado y abierto. Aplicamos
  *context engineering* (Anthropic, *Effective context engineering for AI
  agents*): la ventana deslizante de M2 **preserva** el ancla (el goal/turno
  inicial) y **descarta** los turnos del medio —no solo por costo, sino porque
  *"más contexto no es mejor contexto"* (Context Rot, uno de los cuatro
  problemas del contexto de la clase: límite, costo, latencia, calidad)—. En la
  taxonomía CoALA, esto es **memoria de trabajo** (la ventana); los escenarios
  multi-sala (`apartment-keys`, `office-sequence`) la ejercitan: hay que
  **navegar, recordar el mapa y volver**.

**Arquitectura en una imagen.** El sistema son tres capas —entorno, agente y
evaluación— y la distinción *agente vs. workflow* se ve al colorearlas: el único
componente **autónomo** (donde la LLM decide en runtime) es el núcleo del loop
ReAct; todo lo que lo rodea es **workflow determinístico** (código de 0 tokens:
gate, ventana de memoria, harness, BFS) o **workflow con LLM en paso fijo**
(summarizer y judge: llaman al LLM, pero corren siempre igual, no deciden el
control-flow).

![Arquitectura de la solución: entorno, agente y evaluación](docs/m3_arquitectura.png)

El corazón del agente es el loop ReAct. Visto de cerca, un solo paso del ciclo es
autónomo (la LLM elige la tool); los otros tres son control-flow fijo:

![El loop ReAct por dentro: qué decide el LLM vs. qué es control-flow fijo](docs/m3_loop_react.png)

### 1.2 Especializaciones para M3

Lo mínimo, y todo **detrás de config/flags** para no contaminar M1/M2:

- **System prompt inyectable.** El default de `MyAgent` es genérico; el runner
  de M3 inyecta `ESCAPE_ROOM_SYSTEM_PROMPT` por config
  ([`agent.py`](student_framework/agent.py),
  [`__init__.py`](student_framework/__init__.py)). Así una corrida de M1/M2
  nunca arranca "creyéndose" en una sala de escape. El prompt está **versionado**
  (`ESCAPE_ROOM_SYSTEM_PROMPT_VERSION`) y ese identificador viaja en el meta de
  cada corrida.
- **Summarizer de estado (opcional).** Un `GameState` estructurado que, antes de
  cada llamada, re-deriva el estado de la partida (inventario, ubicación,
  acciones, salidas) con una llamada LLM extra y lo inyecta como contexto. Parte
  de tratar el *contexto como recurso escaso* (clase): la ventana es limitante y
  **qué inyectar es una decisión de ingeniería con costo**. Elegimos memoria
  **estructurada** y no un resumen de texto libre a propósito —la clase señala
  que *"la estructura fuerza a curar, con menos pérdida que un resumen libre"*—.
  Activable con `use_summarizer`; su costo se contabiliza **aparte** para que el
  experimento compare de forma justa.
- **Gate determinístico (opcional).** Es el **patrón de gate** de la clase (el
  chequeo determinístico entre pasos del *prompt chaining*): *"ningún prompt
  garantiza 'monto ≤ límite'; un gate sí"*. Cumple las tres funciones que la
  clase le asigna —**reglas exactas** (no usar un objeto fuera del inventario, no
  inventar IDs son un `if`, no una probabilidad), **cortar temprano** y **registro
  auditable** (el error accionable)— a **0 tokens y 100 % determinístico**
  ([`_ejecutar_tool`](student_framework/agent.py); gate específico en
  [`eval/run.py`](eval/run.py)). Detrás de flag: el contrato de M1 (`run` puede
  terminar con texto sin tools) se mantiene.

Ninguna de estas piezas es el comportamiento por defecto: el agente "base" de
M3 es ReAct puro con el prompt de escape. Seguimos la **regla de simplicidad
composable** de la clase (Anthropic): empezar por lo más simple y subir en
complejidad solo con evidencia; por eso el resumen y el gate son *opcionales* y
se evalúan como experimentos, no se asumen.

---

## 2. Métricas

Medimos sobre el **estado del mundo**, no sobre el texto del agente: un
escenario cuenta como resuelto solo si `check_goal` verifica el cambio físico
(p. ej. `puerta_principal.open_state == "open"`). Esto da una señal objetiva e
inmune a que el agente "diga" que resolvió.

**Marco conceptual (clase de evaluación de agentes).** Tratamos la eval como una
*especificación ejecutable* —"de 'lo probé y anda' a una spec"—, no como un test
de igualdad: en un agente *"correcto es un juicio, no una igualdad verificable"*.
De ahí tres decisiones que fundamentan lo que sigue: (1) reportamos un **vector
de dimensiones**, no un score único, porque *"la calidad no es un escalar"* y *"un
score único es cómodo para un dashboard y desastroso para diagnosticar"*; (2) las
restricciones **duras** (el goal, verificado por `check_goal`) son un **gate
binario**, no un término de un promedio ponderado *("las duras son un gate, no un
término de una suma")*; (3) como *"una corrida es una anécdota, no una medición"*,
cada métrica viaja con su dispersión (pass^k, IC de Wilson, repeats).

### 2.1 Cuantitativas

| Métrica | Qué mide | Por qué la elegimos |
|---|---|---|
| **Accuracy** (con **IC de Wilson 95%**) | Fracción de casos resueltos | Es la medida directa de éxito. Reportamos el intervalo de Wilson porque *"una corrida no es una medición"*: con 8 escenarios y pocos repeats, el intervalo es más honesto que un puntaje pelado (y Wilson se porta mejor que la normal cerca de 0/1). |
| **pass^k** | Resolver el escenario en **todos** los k intentos | El agente actúa **sin supervisión**, así que lo relevante no es "alguna vez lo logró" sino "lo logra de forma consistente". pass^k castiga la varianza que la accuracy promedio esconde. |
| **Overhead vs. óptimo** | `tool_calls / óptimo`, sobre los resueltos | Mide **eficiencia**: cuánto se aleja del camino ideal. El óptimo **no se hardcodea**: se **deriva por BFS** sobre el grafo de estados ([`eval/optimal.py`](eval/optimal.py)), y coincide con el enunciado en los 8/8 escenarios (cross-validación). |
| **Tokens por caso resuelto** | Tokens totales (incl. fallidos) / resueltos | El costo relevante es *"cuánto cuesta un éxito"*, no el promedio por corrida: un agente que falla barato no es más barato si nunca resuelve. Lo medimos en **tokens** (moneda independiente del proveedor) porque con Ollama el costo en USD es $0; el USD es un derivado directo que se "enciende" solo al correr con un proveedor pago (Bedrock). Separamos tokens de **agente** vs. **summarizer**. |
| **Latencia p50 / p95** | Percentiles de wall-clock por caso | La clase es explícita: *"nunca promedio"*. Los percentiles muestran la cola (p95), que es donde vive la mala experiencia. |

**Qué significa "óptimo derivado por BFS".** El overhead se mide contra un óptimo
que no copiamos del enunciado: lo buscamos. Cada arista del grafo de estados del
mundo es una tool-call y el óptimo es el camino más corto desde el estado inicial
hasta uno que cumple `check_goal`. El siguiente diagrama es ese grafo para
`study-with-key` (reusa la BFS real de [`eval/optimal.py`](eval/optimal.py) sobre
`make_world_tools`):

![Grafo de estados de study-with-key con el óptimo del BFS resaltado](docs/m3_grafo_estados.png)

El camino azul (`examine alfombra` → `take llave_oro` → `use` = 3 acciones) es el
óptimo; las ramas grises son estados que la búsqueda explora y descarta. El
escritorio es un **señuelo** (cajones vacíos): re-examinarlo no acerca al
objetivo. Esa exploración descartada es exactamente la *redundancia evitable* que
penaliza el overhead-vs-óptimo y que puntúa el judge (§2.2). El BFS coincide con
el enunciado en los 8/8 escenarios, así que la métrica queda cross-validada.

### 2.2 Dimensión cualitativa (LLM-as-judge)

La dimensión es **calidad de la trayectoria**: *¿el agente exploró con método?*
(Usamos los términos con precisión: la **trayectoria** es la secuencia de
decisiones —el concepto—; el **trace** es su registro instrumentado —el
artefacto— que el judge lee.) La elegimos así deliberadamente: si el agente
**abrió la puerta**, eso ya lo verifica `check_goal` **por código**, y la regla
de la clase es **no usar un judge donde hay verificación programática**. El judge
aporta donde no la hay: en *cómo* se comportó en el camino (look al entrar,
examinar antes de tomar, no repetir acciones, no usar objetos que no tiene), más
allá del éxito binario.

- **Cómo.** El judge puntúa la trayectoria con una rúbrica explícita
  ([`eval/judge.py`](eval/judge.py)), sobre la **traza real de tool-calls** (no
  sobre el output final, que muchas veces no llega). Devuelve el puntaje **y su
  justificación** —CoT que hace el veredicto auditable—. Es *pointwise* (puntúa
  una trayectoria), lo apropiado para **monitorear** (la clase reserva *pairwise*
  para *elegir* entre candidatas).
- **Cuándo NO usar el judge.** Seguimos la regla de la clase: *"empujá todo lo
  que puedas hacia código; el judge es para donde de verdad hace falta juicio"*.
  El **éxito** (abrir la puerta) es verificación programática (`check_goal`), así
  que **no** lo juzga el LLM; el judge solo cubre la calidad de exploración, donde
  no hay verificación por código.
- **Confiabilidad (meta-eval).** *"Un judge es un instrumento, no un oráculo: hay
  que calibrarlo contra ground truth."* Comparamos las trazas del golden set
  contra una **referencia determinística** (`reference_verdict`, derivada de la
  traza) y medimos el **kappa de Cohen** (`cohen_kappa`), que corrige el acuerdo
  por azar —un judge que siempre dice lo mismo puede tener 95% de accuracy y
  κ = 0—. Bandas: κ < 0.4 recalibrar, 0.4–0.6 tolerable, 0.6–0.8 trabajable. Si el
  kappa es bajo, no usamos sus números aunque el judge ya esté construido (es lo
  que pasó: κ ≈ 0, §3.4).

### 2.3 Cómo se computan (reproducibilidad)

Todo sale de `python eval/run.py` sin pasos manuales. Cada corrida escribe
`cases.jsonl` (traza por caso), `summary.json` y `summary.md`, y **versiona** en
el meta: modelo (`BEDROCK_MODEL_ID`), cuenta/perfil AWS, versión de prompt y
commit de git —sin esto, dos corridas de distintas máquinas serían
indistinguibles. El núcleo de métricas, la búsqueda del óptimo y el judge están
**testeados sin LLM** ([`tests/test_eval_harness.py`](tests/test_eval_harness.py),
[`tests/test_judge.py`](tests/test_judge.py)).

---

## 3. Resultados

> Corrida: `python eval/run.py --repeats 3` con `ollama` / `qwen2.5:3b`, prompt
> `escape-v1`, `max_iterations=30`, 8 escenarios × 3 configs × 3 repeats = 72
> casos. Un piloto previo en `nova-lite-v1:0` (Bedrock, config `react`) dio el
> mismo cuadro (0/8, prosa dominante), lo que corrobora que el hallazgo no es
> artefacto de un modelo.

### 3.1 Tabla principal por configuración

Cada config corre los 8 escenarios × 3 repeats = 24 casos.

| Config | Accuracy (IC95%) | pass^k | Varianza (std) | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|
| `react` | 0/24 [0.0, 0.14]† | 0/8† | 0.0 | 2.7 / 6.1 |
| `summarizer` | 0/24 [0.0, 0.14]† | 0/8† | 0.0 | **25.9 / 50.1** |
| `gate` | 0/24 [0.0, 0.14]† | 0/8† | 0.0 | 3.6 / 5.3 |

Con este modelo **ninguna configuración abre una puerta**, y la **varianza entre
repeats es 0**: no es *flaky*, falla de forma **consistente**. El techo lo pone
la disciplina de tool-calling, no el framework (§3.3). (El único éxito que vimos
—`study-with-key` en un smoke suelto— no se repitió en 3 intentos: 0/3.)

### 3.2 Accuracy por dificultad y por escenario

Todas las celdas dan 0 con `qwen2.5:3b`. La vista escenario × config lo hace
explícito y sirve para leer *dónde* falla cada config (con Bedrock, dónde
empieza a resolver):

![Tasa de éxito por escenario × config](docs/m3_heatmap.png)

El interés no está en la accuracy —uniformemente 0— sino en **cómo** falla cada
config, que es donde los experimentos separan aguas (§3.3, §4).

**Óptimo por escenario (BFS, = enunciado):** study-with-key 3 · color-locks 11 ·
apartment-keys 7 · library-search 7 · office-sequence 13 · extreme-archive 4 ·
vault-combination 21 · backtracking-vault 18.

### 3.3 Análisis de errores (sobre trazas reales)

**Método (deductivo → inductivo).** Siguiendo la clase, las dimensiones de fallo
tienen dos orígenes: *deductivo* (a priori, del dominio) e *inductivo* (a
posteriori, de mirar salidas reales). Arrancamos con categorías genéricas
razonables (`crash`, `exhausted_iterations`, `tool_errors`…), pero la categoría
que domina —`prosa_en_vez_de_tool`, con sus variantes— **no se podía imaginar de
antemano**: salió de mirar los traces. Es la advertencia de la clase: *"si
empezás con categorías, vas a encontrar solo lo que ya sabías"*. Por eso las
categorías que reportamos están **definidas y verificadas mirando trazas**, no a
priori:
`success` · `crash` · `loop_detected` · `exhausted_iterations` · `tool_errors` ·
`prosa_en_vez_de_tool`.

![Modos de fallo por configuración](docs/m3_fallos.png)

Sobre 24 casos por config (8 escenarios × 3 repeats):

| Config | prosa_en_vez_de_tool | loop_detected | tool_errors |
|---|---:|---:|---:|
| `react` | 24 | 0 | 0 |
| `summarizer` | 19 | **3** | **2** |
| `gate` | 24 | **0** | **0** |

**Modo dominante: `prosa_en_vez_de_tool`.** El agente **deja de llamar
herramientas y "habla"** en lugar de actuar. Dos variantes, tomadas de las
trazas reales:

- **inversión de rol:** imparte instrucciones a un tercero
  (*"Haz uso de la llave plateada en el cofre…"*).
- **intención anunciada:** anuncia en primera persona lo que hará
  (*"Volveré a examinar el escritorio…"*).

El fallo es de **disciplina de tool-calling**, no de razonamiento espacial: el
agente entiende qué hacer pero lo **describe** en vez de emitir el `tool_call`.
En términos del protocolo de tool use (Clase 3), **falla el "Turn 1"**: en vez de
emitir un `toolUse` (`stopReason = tool_use`), devuelve texto
(`stopReason = end_turn`), lo que **cierra el loop** antes de actuar. Es,
literalmente, una falla del **mecanismo de tool-use que construimos en M1** (ver
[INFORME_M1](INFORME_M1.md) §1): el motor está bien; el modelo chico no lo
acciona. Por eso el gate (§4.2) no lo elimina —el gate valida un `toolUse` que acá
**nunca llega**; solo limpia los fallos por uso inválido cuando el modelo sí actúa.

**Redundancia (señal de loop).** Medimos la racha máxima de tool-calls idénticas
por caso:

![Redundancia: racha máxima de tool-calls repetidas](docs/m3_redundancia.png)

`react` y `gate` casi no repiten (racha 1); el **`summarizer` es el que más
loopea** (casos con rachas de 3 y hasta 5). Consistente con que re-inyectar un
estado resumido a veces **refuerza** una acción equivocada en lugar de
corregirla —otro costo del resumen, además de la latencia.

**Prioridad = frecuencia × costo, no frecuencia sola.** La clase advierte que
priorizar por frecuencia esconde los modos raros pero caros. Lo computamos
(`failure_priority` en el `summary.json`, costo = latencia total atribuible):

| Modo de fallo | Frecuencia | Latencia media | **Costo total (freq × costo)** |
|---|---:|---:|---:|
| `prosa_en_vez_de_tool` | 67 | 9.4 s | 628 s |
| `loop_detected` | **3** | **155.7 s** | **467 s** |
| `tool_errors` | 2 | 49.5 s | 99 s |

Por **frecuencia** manda la prosa (67 vs 3). Pero los **loops**, con solo 3
casos, cuestan casi lo mismo en total (467 s) porque cada uno es **17× más caro**
(155 s vs 9 s). Priorizar por frecuencia sola habría descartado los loops; por
frecuencia × costo, son un objetivo de primera —y quien los produce es el
`summarizer`, lo que refuerza la conclusión del Experimento 1.

### 3.4 Resultados cualitativos (LLM-as-judge)

Checklist binario de 3 criterios (§2.2), **judge = `llama3.2`, distinto del
agente `qwen2.5:3b`**. El score es cuántos criterios se cumplen (0–3); la tasa de
SÍ por criterio es lo diagnóstico.

| Config | Casos puntuados | Score (0–3) | ordenada | apoyadas | sin redundancia |
|---|---:|---:|---:|---:|---:|
| `react` | 24/24 | 0.96† | 0.00 | 0.12 | 0.83 |
| `gate` | 24/24 | 1.00† | 0.08 | 0.12 | 0.79 |
| `summarizer` | 23/24 | 0.96† | 0.13 | 0.22 | 0.61 |

![Calidad de exploración por configuración](docs/m3_judge.png)

Los scores son **bajos** (~1/3) y el desglose por criterio es coherente con el
modo de fallo: casi nunca hay **exploración ordenada** (0.00–0.13) ni **acciones
apoyadas** en lo observado (0.12–0.22), pero sí **poca redundancia** (0.61–0.83)
—porque el agente **abandona temprano** (prosa), no porque explore bien—. El
`summarizer` es el único con algo más de redundancia (0.61 vs 0.79–0.83), lo que
concuerda con que loopea más (§3.3).

**Sobre la cobertura del judge (honesto).** El `llama3.2` pudo puntuar
**23–24/24** de las trazas; cuando el judge fue `qwen2.5:3b` (§3.5), solo pudo
puntuar **9–12/24**. La lectura correcta **no** es "un judge distinto cura el
self-preference" —eso es un sesgo de *puntaje*, que no medimos—, sino que
**`llama3.2` es un judge más confiable para *emitir* el veredicto estructurado**
(un modelo mejor en tool-calling).

**Meta-eval: ¿es confiable el judge? (kappa, medido).** Corrimos la meta-eval del
enunciado sobre el golden set (8 trazas reales del piloto `nova-lite`,
[`eval/golden/`](eval/golden/)): comparamos el veredicto del judge (`llama3.2`)
contra una **referencia determinística** derivada de propiedades objetivas de la
traza —orden `look`/`examine` antes de actuar, `tool_error_count`, repeticiones—
(`reference_verdict` en [`eval/judge.py`](eval/judge.py)), con la **kappa de
Cohen** por criterio. La referencia es código, no otro juicio subjetivo ni el
mismo LLM: evita la circularidad. Resultado: **κ ≈ 0 en los tres criterios**
(`exploracion_ordenada` **0.0**, `acciones_apoyadas` **0.0**,
`sin_redundancia_evitable` **−0.2**). El judge **no acuerda con la referencia
mejor que el azar**: satura marcando `exploracion_ordenada`=NO en las 8 trazas
(no discrimina) y hasta reporta "acciones sin apoyo" en trazas con **cero
tool-errors** (alucina el defecto). Es **evidencia medida** del techo de capacidad
que sospechábamos —un judge tan débil como el agente no es confiable—, así que los
scores de la tabla de arriba hay que tomarlos con pinzas.

*Caveats del kappa.* n=8 y todas fallidas (trayectorias cortas): la referencia
satura en algunos criterios (p. ej. `acciones_apoyadas` da SÍ en las 8 porque
ninguna acción falló), así que parte de los κ=0 son **degenerados por falta de
varianza**, no solo desacuerdo genuino. El self-preference (mismas trazas bajo
judge propio vs. ajeno) **sigue sin medirse** (§5). Una calibración definitiva
necesita un judge fuerte (`nova-pro`) y trazas con variación real (éxitos,
trayectorias largas). Reproducible: `python eval/kappa.py eval/golden/cases.jsonl`.

### 3.5 Comparación cross-modelo / proveedor

Como los resultados de accuracy están acotados por el modelo, comparamos **el
mismo framework sobre varios modelos** para separar *límites del modelo* de
*límites del framework*. Esto es también una técnica de **error analysis
inductivo** de la clase —*"otro modelo haciendo la tarea sirve para descubrir qué
se rompe"*—: correr un segundo modelo destapó modos de fallo que uno solo
escondía. Cada corrida versiona su `provider`/`model`, y
`scripts/comparar_modelos_m3.py` arma la comparativa a partir de todas las
corridas presentes —basta correr un modelo nuevo y volver a ejecutarlo. Corrimos
`qwen2.5:3b` y `llama3.2` (Ollama, repeats-3); queda pendiente `nova-lite`
(Bedrock, modelo fuerte).

**Hallazgo 1 — los dos modelos fallan de forma distinta.** No es el mismo 0/8:

| | `qwen2.5:3b` | `llama3.2` |
|---|---|---|
| Modo de fallo dominante | **prosa** (no actúa) | **tool_errors** (actúa, pero inválido) |
| Uso de `use`/`go` | ~0 | usa `use` y `go`, pero con errores |

`qwen` se queda en describir la acción; `llama3.2` sí la intenta pero se
equivoca de objeto/argumento. **El "0/8" esconde dos patologías opuestas** —solo
visibles porque medimos el comportamiento, no un número.

**Hallazgo 2 — el efecto del resumen es *dependiente del modelo*.**

![Accuracy por modelo × configuración](docs/m3_cmp_accuracy.png)

La **única accuracy no-cero de toda la evaluación** es `llama3.2` + `summarizer`
(**2/24 ≈ 0.083**). El resumen **ayuda** a un modelo que *actúa* (`llama3.2`:
le da estado para no repetir), pero **perjudica** a uno que *no actúa*
(`qwen`: §4.1, más latencia y loops, sin beneficio). Es decir, **la conclusión
del Experimento 1 se invierte según el modelo** —un resultado que un solo modelo
habría ocultado, y el argumento más fuerte para la comparación cross-modelo.

La lectura para Bedrock: con un modelo que llame herramientas de forma
confiable, esperamos que la accuracy despegue y que estos efectos
(costo/limpieza/beneficio del resumen) se puedan medir sobre casos resueltos.

### 3.6 Observabilidad: perfil de comportamiento

Para no reducir todo a "0/8", instrumentamos **qué hace** el agente:

![Perfil de uso de herramientas por configuración](docs/m3_tools.png)

- **Perfil de uso de herramientas.** El agente **explora pero rara vez
  ejecuta**: domina `look`/`examine`, hace poco `take`, y en esta corrida
  `use`=0 (react/gate) y `go`=0 en todos. Como abrir la puerta requiere `use`
  (y los multi-sala requieren `go`), este perfil *es* la cara agregada del 0/8.
  El mecanismo se ve en las trazas: en el punto de ejecutar, el agente
  **describe la acción en prosa** en vez de emitirla —p. ej. escribe *"Haz uso
  de la llave plateada en el cofre"* o *"`go(norte)`"* como texto, sin llamar la
  herramienta. Es el mismo `prosa_en_vez_de_tool` visto desde el uso de tools.
  **No es incapacidad:** en un smoke aislado el agente sí emitió
  `use(llave, puerta)` y resolvió `study-with-key`; es **inconsistencia**, con
  varianza entre corridas —otra razón para medir `pass^k` y no una sola corrida.
- **Tasa de acción inválida** (`tool_errors/tool_calls`): `react` 0.0, `gate`
  0.0, `summarizer` 0.03. Baja en todos porque el agente apenas llega a
  intentar acciones que un gate rechazaría; el gate la mantiene en 0 por
  construcción (el `summarizer`, que sí intenta más `use`, es el único con
  acciones inválidas).
- **Progreso parcial** (`items_taken`, `rooms_visited`, `items_opened`): con
  `qwen2.5:3b` es ~0 (el agente se traba antes de avanzar). Esta métrica se
  captura por corrida y será informativa con un modelo que sí actúe (Bedrock):
  permite medir *cuánto* avanzó aunque no abra la puerta.

**Costo en tokens** (agente vs. summarizer):

![Costo en tokens por configuración](docs/m3_costo.png)

El summarizer suma **~6.100 tokens/caso (+65%)** sin resolver nada más. Además
del conteo de tokens, el harness estima el **costo en USD** por caso y por caso
resuelto (`cost_usd_*` en el `summary.json`), usando el pricing on-demand del
modelo —$0 para modelos locales como `qwen2.5:3b`, y con precio real en Bedrock
(`nova-lite`), donde el sobrecosto del resumen se traduce directamente en
dólares.†

Los **tokens por caso resuelto** son la métrica más honesta de eficiencia, pero
exigen que haya éxitos: en la corrida canónica (`qwen2.5:3b`, 0/8) quedan
**indefinidos** (división por cero) —lo cual, en sí, dice algo: no hay eficiencia
que medir si nunca se resuelve—. El único punto con éxitos en todo el barrido es
`llama3.2 + summarizer` (2/24), donde da **162.824 tokens por éxito**: un número
enorme que muestra el precio real de "arrancar a resolver" con un modelo chico.
Es justamente la métrica que se vuelve central con un modelo capaz en Bedrock.

---

## 4. Experimentos

Dos experimentos, cada uno aislando **una** pieza del framework. Todos corren
sobre el mismo dataset y con el mismo `max_iterations`; solo cambia el eje bajo
estudio (los demás quedan fijos).

### 4.1 Experimento 1 — Resumen de estado (summarizer on/off)

- **Qué cambiamos.** `react` (sin resumen) vs. `summarizer` (re-deriva el
  `GameState` y lo inyecta cada paso). `--configs react,summarizer`.
- **Hipótesis.** El resumen **ayuda solo cuando el contexto crudo no entra**
  (p. ej. `extreme-archive`, diseñado para no caber en 16 K tokens) y **perjudica
  cuando entra** (easy/medium): agrega costo y una re-derivación *lossy* que puede
  corromper IDs/llaves, justo donde el estado exacto es todo.
- **Qué miramos.** Accuracy por dificultad, latencia (¿cuánto cuesta el resumen?)
  y modos de fallo.

![Latencia p50/p95 por configuración](docs/m3_latencia.png)

- **Resultado.** Accuracy **sin cambios** (0/24 vs 0/24), pero el resumen
  **multiplica la latencia ~8×**: p95 **50.1 s** vs 6.1 s de `react` (la llamada
  LLM extra por paso). Además **empeora los modos de fallo**: introduce 2
  `tool_errors` y **3 `loop_detected`** que `react` no tiene (0 y 0) —re-inyectar
  el estado resumido a veces refuerza una acción equivocada. No pudimos confirmar
  la parte "ayuda en `extreme-archive`" de la hipótesis: con este modelo el
  agente falla **aguas arriba** (prosa) y nunca llega a desbordar el contexto,
  que es donde el resumen pagaría.
- **Conclusión.** Con `qwen2.5:3b` el resumen es **costo puro** (perjudica). Pero
  el efecto es **dependiente del modelo**: con `llama3.2` —que sí actúa— el
  resumen **ayuda** y da la única accuracy no-cero de la evaluación (2/24, §3.5).
  La lectura no es "el resumen es malo" sino "el resumen ayuda a un modelo que
  actúa y estorba a uno que no" —lo que motiva el **summarizer selectivo** de §5.
  La comparación cross-modelo fue clave para no sacar la conclusión equivocada
  desde un solo modelo.

### 4.2 Experimento 2 — Gate determinístico (gate on/off)

- **Qué cambiamos.** `react` (gate off) vs. `gate` (un `if` bloquea, antes de
  ejecutar, usar objetos fuera del inventario o IDs inexistentes).
  `--configs react,gate`.
- **Hipótesis.** *"Ningún prompt garantiza X; un gate sí."* El prompt tiene
  ~200 líneas de "REGLAS ABSOLUTAS" que **no** evitan el uso inválido; un gate de
  ~15 líneas y **0 tokens** debería eliminar `tool_errors`/uso inválido.
- **Qué miramos.** Accuracy y desglose de modos de fallo (¿baja el uso inválido?),
  latencia (el gate no gasta tokens).
- **Resultado.** Accuracy **sin cambios** (0/24): el gate **no puede forzar** que
  el modelo emita un `tool_call` —solo bloquea las inválidas—, así que no cura la
  prosa. **Pero deja el perfil de fallos más limpio de los tres:** `tool_errors`
  **0** y `loop_detected` **0** sobre 24 casos, frente al `summarizer` (2
  tool_errors + 3 loops). Y es incluso **ligeramente más rápido** que `react`
  (p95 5.3 vs 6.1 s), a 0 tokens de costo.
- **Conclusión.** El gate **entrega lo que el prompt no puede**: elimina por
  construcción los fallos de uso inválido y los loops. No genera éxitos por sí
  solo —eso requiere un modelo que llame herramientas—, pero es un **piso de
  garantías gratis** sobre el que ese modelo rendiría mejor. Confirma la máxima:
  *un `if` garantiza lo que ningún prompt garantiza*.

---

## 5. Limitaciones y próximos pasos

**Limitaciones asumidas.**

- **Modelo chico.** Con modelos chicos (`qwen2.5:3b` local; el piloto en
  `nova-lite` mostró lo mismo), el modo de fallo dominante es de **disciplina de
  tool-calling** (prosa en vez de acción), no de razonamiento espacial. Nuestros
  resultados de accuracy están acotados por el modelo, no por el framework: por
  eso el aporte de los experimentos se ve en **cómo** falla (latencia del resumen,
  limpieza del gate), no en el 0/8. Un modelo más capaz debería mover el techo.
- **Óptimo como referencia de eficiencia.** El overhead es relativo al óptimo
  **derivado por búsqueda**; es una medida de eficiencia, no una afirmación de
  minimalidad absoluta (aunque coincide con el enunciado en los 8/8).
- **Judge = LLM: dos anti-patrones que identificamos y corregimos, y lo que
  queda.** Una primera versión usaba **el mismo modelo como agente y judge** y una
  **escala ordinal 1–5** —dos anti-patrones de la clase (self-preference y
  tendencia central; las notas se amontonaban en 3)—. Los **corregimos**: judge
  **distinto** del agente (`llama3.2` juzga a `qwen`) y **checklist binario** (§2.2,
  §3.4). Además **corrimos la meta-eval (kappa)** contra una referencia
  determinística: **κ ≈ 0** en los tres criterios (§3.4) — evidencia *medida* de
  que el judge chico no es confiable. *Lo que queda* como limitación honesta:
  (a) **capacidad del judge** — con modelos locales chicos el judge no es *más
  capaz* que el agente, solo distinto; lo correcto es un judge fuerte (`nova-pro`
  juzgando a `nova-lite`); (b) el **kappa medido es frágil**: con 8 trazas fallidas
  la referencia satura y parte de los κ=0 son degenerados por falta de varianza —una
  kappa definitiva necesita trazas con variación real; (c) **no medimos
  self-preference** (requiere comparar puntajes de las mismas trazas bajo judge
  propio vs ajeno). Con un judge chico, sus puntajes son indicativos, no confiables.
- **Escala del dataset.** 8 escenarios: los intervalos de confianza son anchos.
  pass^k y Wilson lo hacen explícito, pero no lo eliminan.
- **`max_iterations = 30` es del harness**, no del enunciado: lo subimos para que
  el techo de iteraciones no sesgue la accuracy (`vault-combination` necesita 21).

**Qué construiríamos a continuación.**

1. **Gate más rico** (si el Experimento 2 lo respalda): extender las garantías
   determinísticas a más precondiciones del mundo, y medir hasta dónde el gate
   sustituye prompt.
2. **Summarizer selectivo:** activar el resumen **solo** cuando el contexto crudo
   desborda, en vez de siempre —convirtiendo el hallazgo del Experimento 1 en una
   política.
3. **Planner explícito vs. ReAct** en `office-sequence` (goal compuesto/ordenado):
   el escenario premia descomponer y planificar el orden de sub-objetivos.
4. **Más modelos y un modelo fuerte.** Ya corrimos con `--repeats 3` y con dos
   modelos locales (`qwen2.5:3b`, `llama3.2`); el paso que falta es un modelo
   capaz (`nova-lite`/`nova-pro` en Bedrock) que **sí** llame herramientas, para
   separar de forma limpia los límites del framework de los del modelo y ver si
   los efectos medidos (costo del resumen, limpieza del gate) persisten cuando la
   accuracy deja de ser 0.
5. **Calibrar el judge.** Ya lo hicimos **distinto** del agente, con **checklist
   binario**, y **medimos la kappa** contra una referencia determinística (κ ≈ 0:
   el judge chico no es confiable, §3.4). Falta lo más costoso: un judge **más
   capaz** (`nova-pro` en Bedrock) y **trazas con variación real** (éxitos,
   trayectorias largas) para que la kappa deje de ser degenerada y recién ahí
   confiar en sus puntajes.
6. **Memoria más allá de la de trabajo (CoALA).** Hoy el agente usa solo
   **memoria de trabajo** (la ventana). Sumar memoria **episódica** (aprender
   entre escenarios: "en la sala anterior la llave estaba bajo la alfombra") o
   **semántica** (hechos persistentes del mundo) permitiría transferir
   aprendizaje entre corridas, hoy imposible porque el estado vive solo en el
   proceso.

---

## Apéndice A — Cómo reproducir

```bash
# --- Con Ollama (local, sin lease) ---
OLLAMA_HOST=http://localhost:11434 OLLAMA_MODEL=qwen2.5:3b \
  python eval/run.py --repeats 3

# --- Con Bedrock (modelo fuerte; requiere lease + nova-lite habilitado) ---
python eval/run.py --repeats 3          # toma el provider del .env

# Dimensión cualitativa (LLM-as-judge) sobre una corrida (judge DISTINTO del agente)
python eval/judge.py eval/results/<timestamp>/cases.jsonl --judge-model llama3.2

# Meta-eval del judge: kappa de Cohen vs. referencia determinística (sobre el golden)
python eval/judge.py eval/golden/cases.jsonl --judge-model llama3.2
python eval/kappa.py  eval/golden/cases.jsonl

# Gráficos de UNA corrida
python scripts/generar_graficos_m3.py

# Gráficos COMPARANDO todos los modelos/proveedores corridos
python scripts/comparar_modelos_m3.py
```

Salidas en `eval/results/<timestamp>/`: `cases.jsonl`, `summary.json`,
`summary.md`. Cada corrida versiona `provider`/`model` en su meta, así la
comparación cross-modelo se arma sola a partir de las corridas presentes.
Golden set y flujo de etiquetado en [`eval/golden/README.md`](eval/golden/README.md).
