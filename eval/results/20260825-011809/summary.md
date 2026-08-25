# Evaluación M3 — resumen

- Fecha: 20260825-011809
- Módulo del agente: `student_framework`
- Provider/modelo: `ollama` / `qwen2.5:3b`
- Versión de prompt: `escape-v1` · commit: `cc1a7ae`
- max_iterations: 30 · repeats: 3
- Casos totales: 72

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass^k = resolver el escenario en los k intentos._

| Config | Accuracy (IC95%) | pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.0 [0.0, 0.138] | 0.0 (0/8, k=3) | — | — | 3.639 / 5.312 |
| react | 0.0 [0.0, 0.138] | 0.0 (0/8, k=3) | — | — | 2.726 / 6.1 |
| summarizer | 0.0 [0.0, 0.138] | 0.0 (0/8, k=3) | — | — | 25.927 / 50.103 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/3 | 0.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 24
    - inversion_de_rol: 15
    - otro: 8
    - intencion_anunciada: 1

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/3 | 0.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 24
    - inversion_de_rol: 14
    - otro: 9
    - intencion_anunciada: 1

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/3 | 0.0 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 0/6 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 19
    - inversion_de_rol: 10
    - otro: 8
    - intencion_anunciada: 1
- `loop_detected`: 3
- `tool_errors`: 2
