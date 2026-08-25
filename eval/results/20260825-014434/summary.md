# Evaluación M3 — resumen

- Fecha: 20260825-014434
- Módulo del agente: `student_framework`
- Provider/modelo: `ollama` / `llama3.2`
- Versión de prompt: `escape-v1` · commit: `c9edd61`
- max_iterations: 30 · repeats: 3
- Casos totales: 72

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass^k = resolver el escenario en los k intentos._

| Config | Accuracy (IC95%) | pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.0 [0.0, 0.138] | 0.0 (0/8, k=3) | — | — | 2.474 / 29.686 |
| react | 0.0 [0.0, 0.138] | 0.0 (0/8, k=3) | — | — | 2.25 / 9.165 |
| summarizer | 0.083 [0.023, 0.258] | 0.0 (0/8, k=3) | 2.0x | 162824 | 10.096 / 62.198 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/3 | 0.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `tool_errors`: 20
- `exhausted_iterations`: 2
- `prosa_en_vez_de_tool`: 2
    - intencion_anunciada: 2

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/3 | 0.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `tool_errors`: 23
- `prosa_en_vez_de_tool`: 1
    - intencion_anunciada: 1

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 2/3 | 0.667 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `tool_errors`: 18
- `prosa_en_vez_de_tool`: 3
    - intencion_anunciada: 3
- `success`: 2
- `exhausted_iterations`: 1
