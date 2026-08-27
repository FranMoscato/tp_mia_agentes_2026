# Informes — Serie de tres milestones

**Materia:** Agentes con LLMs — MIA (UdeSA)

Este trabajo se construye en tres milestones hacia una misma meta: un agente que
**juega y se evalúa en una sala de escape**. La *gamification* —usar un juego
(escape room) como banco de pruebas— es el **hilo conductor**: cada milestone
agrega la pieza que el juego va a exigir, y el último lo pone a jugar y lo mide.

| Informe | Milestone | Qué aporta al juego |
|---|---|---|
| [**INFORME_M1**](INFORME_M1.md) | Bucle del agente y herramientas | El **agente** y el mecanismo de **herramientas** (`register_tool` + loop ReAct). Las tools genéricas (calculadora, lector) son el mismo mecanismo que en M3 se vuelve `look/examine/take/use/go`. |
| [**INFORME_M2**](INFORME_M2.md) | Memoria, prompting y robustez | La **memoria** (sliding window + goal), la **salida estructurada** y la **resiliencia**. Es justo lo que el escape room necesita: un mundo *estado-full*, salidas malformadas de modelos chicos y trayectorias largas. |
| [**INFORME_M3**](INFORME_M3.md) | Evaluación sobre salas de escape | Pone el agente **dentro del juego** y lo **evalúa** (accuracy + IC, pass^k, overhead vs. óptimo por BFS, latencia, costo, LLM-as-judge). |

## Estado y próximo paso

La serie está completa y los tres informes son estables. **El eval de M3 ya corrió
en Bedrock**: `nova-lite` como agente (96 casos) y `nova-pro` como judge
(cobertura 96/96), más una escalera de capacidad `nova-micro` → `nova-lite` →
`nova-pro` y una de tamaño en local (`llama3.2` 3.2B → `llama3.1` 8B).

**El hallazgo que ordena el trabajo:** el techo dejó de ser el modelo. La
accuracy sube de 0/24 a 0.792 entre el modelo local y `nova-lite`, y **deja de
subir** en `nova-pro`. El agente resuelve los 8 escenarios en algún intento
(`pass@k` = 1.0) pero solo 5 de 8 en los tres (`pass^k` = 0.625): el límite es la
**consistencia**, no la capacidad.

El próximo paso apunta ahí, y ya sabemos por dónde **no** va: cortar loops en
runtime y ampliar la ventana de memoria son dos experimentos que no movieron la
accuracy (§4.4 y §4.5). Detalle en [INFORME_M3](INFORME_M3.md) §5.

## Cómo se regeneran los diagramas

```bash
# Diagramas de M1
python scripts/generar_diagrama_arquitectura.py
python scripts/generar_diagrama_bucle.py
# Diagramas de M2
python scripts/generar_diagramas_m2.py
# Diagramas y gráficos de M3
python scripts/generar_diagramas_arquitectura_m3.py
python scripts/grafico_grafo_estados_m3.py
python scripts/generar_graficos_m3.py         # gráficos de datos de una corrida
python scripts/comparar_modelos_m3.py         # comparativa cross-modelo
```
