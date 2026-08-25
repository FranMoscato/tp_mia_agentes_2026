# Evaluación M3 — resumen

- Fecha: 20260825-010410
- Módulo del agente: `student_framework`
- Provider/modelo: `ollama` / `qwen2.5:3b`
- Versión de prompt: `escape-v1` · commit: `b3bffcd`
- max_iterations: 30 · repeats: 1
- Casos totales: 24

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass^k = resolver el escenario en los k intentos._

| Config | Accuracy (IC95%) | pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.0 [0.0, 0.324] | 0.0 (0/8, k=1) | — | — | 3.368 / 6.236 |
| react | 0.0 [0.0, 0.324] | 0.0 (0/8, k=1) | — | — | 4.156 / 7.602 |
| summarizer | 0.0 [0.0, 0.324] | 0.0 (0/8, k=1) | — | — | 27.858 / 53.915 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/1 | 0.0 |
| extreme | 0/3 | 0.0 |
| hard | 0/2 | 0.0 |
| medium | 0/2 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 8
    - inversion_de_rol: 4
    - otro: 3
    - intencion_anunciada: 1

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/1 | 0.0 |
| extreme | 0/3 | 0.0 |
| hard | 0/2 | 0.0 |
| medium | 0/2 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 7
    - inversion_de_rol: 4
    - otro: 2
    - intencion_anunciada: 1
- `loop_detected`: 1

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/1 | 0.0 |
| extreme | 0/3 | 0.0 |
| hard | 0/2 | 0.0 |
| medium | 0/2 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 6
    - inversion_de_rol: 4
    - otro: 2
- `tool_errors`: 1
- `loop_detected`: 1
