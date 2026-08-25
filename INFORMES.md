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

## Diseño compartido

Los tres informes se leen como una serie: los diagramas comparten una **paleta
única** (la paleta categórica validada del skill de dataviz, ver
[`scripts/estilo_diagramas.py`](scripts/estilo_diagramas.py)) y el mismo estilo
de cajas y flechas. Los gráficos de datos (solo en M3) usan esa misma paleta.

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
