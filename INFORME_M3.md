# Informe — Milestone 3: Evaluación sobre salas de escape

> **Estado del documento.** Las secciones 1, 2 y 5 están completas. Las
> secciones 3 (Resultados) y 4 (Experimentos) tienen la metodología y las
> tablas armadas; los números finales salen de la corrida `python eval/run.py
> --repeats 3` contra el modelo real. Donde falta pegar un número aparece
> `«…»`. Se incluye, marcado como **piloto**, el resultado de una corrida
> preliminar (1 repeat, config `react`) que ya tenemos.

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

El agente de M3 es **el mismo `MyAgent`** de M1+M2, sin bifurcar. El problema se
resuelve registrando las herramientas del mundo y dejando que el bucle ReAct de
M1 (sense → decide → act) opere, apoyado en el estado conversacional y la
ventana de memoria de M2:

- **Bucle y herramientas (M1).** El runner registra los verbos del mundo con
  `agent.register_tool(...)` ([`mia_world/cli.py`](mia_world/cli.py),
  [`eval/run.py`](eval/run.py)). El agente los expone al LLM en cada llamada y
  ejecuta el `tool_call` elegido. Los **errores de las herramientas vuelven
  como observaciones** (no rompen el bucle), lo que permite que el modelo
  corrija sobre la marcha —clave en un dominio donde equivocarse de llave o de
  ID es esperable.
- **Estado y memoria (M2).** La sala de escape es un problema **estado-full**:
  lo que se puede hacer depende de lo ya observado, tomado y abierto. La ventana
  deslizante de M2 (recencia + preservación del turno inicial) mantiene el
  objetivo presente en conversaciones largas, y los escenarios multi-sala
  (`apartment-keys`, `office-sequence`) ejercitan justamente esa memoria: hay
  que **navegar, recordar el mapa y volver**.

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
  acciones, salidas) con una llamada LLM extra y lo inyecta como contexto. Es
  **memoria comprimida**, activable con `use_summarizer`; su costo se contabiliza
  **aparte** para que el experimento compare de forma justa.
- **Gate determinístico (opcional).** Un `if` que garantiza lo que ningún prompt
  puede: no usar un objeto que no está en el inventario, no inventar IDs
  ([`_ejecutar_tool`](student_framework/agent.py); gate específico en
  [`eval/run.py`](eval/run.py)). Detrás de flag: el contrato de M1 (`run` puede
  terminar con texto sin tools) se mantiene.

Ninguna de estas piezas es el comportamiento por defecto: el agente "base" de
M3 es ReAct puro con el prompt de escape.

---

## 2. Métricas

Medimos sobre el **estado del mundo**, no sobre el texto del agente: un
escenario cuenta como resuelto solo si `check_goal` verifica el cambio físico
(p. ej. `puerta_principal.open_state == "open"`). Esto da una señal objetiva e
inmune a que el agente "diga" que resolvió.

### 2.1 Cuantitativas

| Métrica | Qué mide | Por qué la elegimos |
|---|---|---|
| **Accuracy** (con **IC de Wilson 95%**) | Fracción de casos resueltos | Es la medida directa de éxito. Reportamos el intervalo de Wilson porque *"una corrida no es una medición"*: con 8 escenarios y pocos repeats, el intervalo es más honesto que un puntaje pelado (y Wilson se porta mejor que la normal cerca de 0/1). |
| **pass^k** | Resolver el escenario en **todos** los k intentos | El agente actúa **sin supervisión**, así que lo relevante no es "alguna vez lo logró" sino "lo logra de forma consistente". pass^k castiga la varianza que la accuracy promedio esconde. |
| **Overhead vs. óptimo** | `tool_calls / óptimo`, sobre los resueltos | Mide **eficiencia**: cuánto se aleja del camino ideal. El óptimo **no se hardcodea**: se **deriva por BFS** sobre el grafo de estados ([`eval/optimal.py`](eval/optimal.py)), y coincide con el enunciado en los 8/8 escenarios (cross-validación). |
| **Costo por caso resuelto** | Tokens totales (incl. fallidos) / resueltos | El costo relevante es *"cuánto cuesta un éxito"*, no el promedio por corrida: un agente que falla barato no es más barato si nunca resuelve. Separamos tokens de **agente** vs. **summarizer**. |
| **Latencia p50 / p95** | Percentiles de wall-clock por caso | La clase es explícita: *"nunca promedio"*. Los percentiles muestran la cola (p95), que es donde vive la mala experiencia. |

### 2.2 Dimensión cualitativa (LLM-as-judge)

La dimensión es **calidad de la trayectoria**: *¿el agente exploró con método?*
La elegimos así deliberadamente: si el agente **abrió la puerta**, eso ya lo
verifica `check_goal` **por código**, y la regla de la clase 8 es **no usar un
judge donde hay verificación programática**. El judge aporta donde no la hay: en
*cómo* se comportó en el camino (look al entrar, examinar antes de tomar, no
repetir acciones, no usar objetos que no tiene), más allá del éxito binario.

- **Cómo.** El judge puntúa la trayectoria **1–5** con una rúbrica explícita
  ([`eval/judge.py`](eval/judge.py)), sobre la **traza real de tool-calls** (no
  sobre el output final, que muchas veces no llega). Devuelve el puntaje **y su
  justificación**, para poder auditarlo.
- **Confiabilidad (meta-eval).** Etiquetamos a mano las trazas del golden set y
  medimos el **kappa de Cohen** entre el judge y el humano (`cohen_kappa`). Un
  kappa alto valida el judge; uno bajo dice que hay que ajustar la rúbrica antes
  de confiar en sus números.

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

> Corrida final: `python eval/run.py --repeats 3` con
> `BEDROCK_MODEL_ID = «…»`, prompt `escape-v1`, commit `«…»`.

### 3.1 Tabla principal por configuración

| Config | Accuracy (IC95%) | pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| `react` | «…» | «…» | «…» | «…» | «…» |
| `summarizer` | «…» | «…» | «…» | «…» | «…» |
| `gate` | «…» | «…» | «…» | «…» | «…» |

### 3.2 Accuracy por dificultad

| Dificultad | `react` | `summarizer` | `gate` |
|---|---:|---:|---:|
| easy | «…» | «…» | «…» |
| medium | «…» | «…» | «…» |
| hard | «…» | «…» | «…» |
| extreme | «…» | «…» | «…» |

**Óptimo por escenario (BFS, = enunciado):** study-with-key 3 · color-locks 11 ·
apartment-keys 7 · library-search 7 · office-sequence 13 · extreme-archive 4 ·
vault-combination 21 · backtracking-vault 18.

### 3.3 Análisis de errores (sobre trazas reales)

Categorías (definidas y verificadas mirando trazas, no a priori):
`success` · `crash` · `loop_detected` · `exhausted_iterations` · `tool_errors` ·
`prosa_en_vez_de_tool`. Distribución por config: «…».

**Hallazgo del piloto (config `react`, 1 repeat, `nova-lite-v1:0`):**

- **Accuracy 0/8** (IC95% [0.0, 0.324]); pass^k 0/8.
- **Modo de fallo dominante: `prosa_en_vez_de_tool` — 8/8.** El agente **deja de
  llamar herramientas y "habla"** en lugar de actuar. Dos variantes observadas:
  - **inversión de rol (4/8):** imparte instrucciones a un tercero
    (*"Haz uso de la llave plateada en el cofre…"*).
  - **intención anunciada (1/8):** anuncia en primera persona lo que hará
    (*"Volveré a examinar el escritorio…"*).
  - otras (3/8): prosa que no encaja limpio en las dos anteriores.
- Latencia p50/p95 ≈ 4.7 / 6.8 s.

Este hallazgo es el que motiva el **Experimento 2 (gate)**: el gate ataca
directamente el uso inválido de objetos/IDs que acompaña a este modo de fallo.

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
- **Qué miramos.** Accuracy por dificultad (¿el resumen recupera los `extreme`?),
  costo por resuelto (¿cuánto suma el resumen?, medido aparte) y overhead.
- **Resultado.** «…». **Conclusión.** «…».

### 4.2 Experimento 2 — Gate determinístico (gate on/off)

- **Qué cambiamos.** `react` (gate off) vs. `gate` (un `if` bloquea, antes de
  ejecutar, usar objetos fuera del inventario o IDs inexistentes).
  `--configs react,gate`.
- **Hipótesis.** *"Ningún prompt garantiza X; un gate sí."* El piloto mostró que
  ~200 líneas de "REGLAS ABSOLUTAS" en el prompt **no** evitan el uso inválido; un
  gate de ~15 líneas y **0 tokens** debería reducir `tool_errors`/uso inválido y,
  con ello, mejorar accuracy o al menos el overhead.
- **Qué miramos.** Accuracy y desglose de modos de fallo (¿baja el uso inválido?),
  overhead y costo (el gate no gasta tokens: ¿mejora la eficiencia?).
- **Resultado.** «…». **Conclusión.** «…».

---

## 5. Limitaciones y próximos pasos

**Limitaciones asumidas.**

- **Modelo chico.** Con `nova-lite`, el modo de fallo dominante es de
  **disciplina de tool-calling** (prosa en vez de acción), no de razonamiento
  espacial. Muchos de nuestros resultados podrían estar acotados por el modelo,
  no por el framework; un modelo más capaz podría mover el techo.
- **Óptimo como referencia de eficiencia.** El overhead es relativo al óptimo
  **derivado por búsqueda**; es una medida de eficiencia, no una afirmación de
  minimalidad absoluta (aunque coincide con el enunciado en los 8/8).
- **Judge = LLM.** La dimensión cualitativa depende de un LLM; su confiabilidad
  se apoya en el kappa contra etiquetas humanas del golden set. Un kappa bajo
  invalidaría sus números.
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
4. **Más repeats y más modelos** para angostar los intervalos y separar límites
   del framework de límites del modelo.

---

## Apéndice A — Cómo reproducir

```bash
# Corrida completa (8 escenarios × 3 experimentos × 3 repeats)
python eval/run.py --repeats 3

# Un experimento puntual
python eval/run.py --configs react,gate --repeats 3

# Dimensión cualitativa (LLM-as-judge) sobre una corrida
python eval/judge.py eval/results/<timestamp>/cases.jsonl
```

Salidas en `eval/results/<timestamp>/`: `cases.jsonl`, `summary.json`,
`summary.md`. Golden set y flujo de etiquetado en
[`eval/golden/README.md`](eval/golden/README.md).
