# Evaluación M3 — resumen

- Fecha: 20260826-233443
- Módulo del agente: `student_framework`
- Provider/modelo: `ollama` / `llama3.1`
- Versión de prompt: `escape-v1` · commit: `14e4f62`
- max_iterations: 30 · repeats: 3
- Casos totales: 96

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.167 [0.067, 0.359] | 0.25 / 0.125 (k=3) | 1.57x | 392390 | 16.785 / 20.136 |
| react | 0.125 [0.043, 0.31] | 0.125 / 0.125 (k=3) | 1.67x | 563556 | 16.579 / 19.403 |
| react_generico | 0.0 [0.0, 0.138] | 0.0 / 0.0 (k=3) | — | — | 9.588 / 27.661 |
| summarizer | 0.125 [0.043, 0.31] | 0.125 / 0.125 (k=3) | 1.33x | 515708 | 72.941 / 148.183 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 1/6 | 0.167 |

**Modos de fallo:**

- `exhausted_iterations`: 13
- `tool_errors`: 7
- `success`: 4

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `exhausted_iterations`: 13
- `prosa_en_vez_de_tool`: 8
    - otro: 8
- `success`: 3

### react_generico

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/3 | 0.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `tool_errors`: 13
- `prosa_en_vez_de_tool`: 9
    - otro: 9
- `exhausted_iterations`: 2

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `crash`: 9
- `prosa_en_vez_de_tool`: 4
    - otro: 4
- `loop_detected`: 4
- `success`: 3
- `exhausted_iterations`: 3
- `tool_errors`: 1
