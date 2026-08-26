# Evaluación M3 — resumen

- Fecha: 20260826-190401
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-micro-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `f922d84`
- max_iterations: 30 · repeats: 3
- Casos totales: 96

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.375 [0.212, 0.573] | 0.5 / 0.25 (k=3) | 2.76x | 325626 | 23.88 / 29.095 |
| react | 0.25 [0.12, 0.449] | 0.5 / 0.0 (k=3) | 2.59x | 497195 | 23.663 / 28.947 |
| react_generico | 0.292 [0.149, 0.492] | 0.375 / 0.125 (k=3) | 2.88x | 293634 | 21.215 / 31.857 |
| summarizer | 0.25 [0.12, 0.449] | 0.5 / 0.0 (k=3) | 1.79x | 656250 | 60.779 / 117.51 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 2/9 | 0.222 |
| hard | 1/6 | 0.167 |
| medium | 3/6 | 0.5 |

**Modos de fallo:**

- `exhausted_iterations`: 11
- `success`: 9
- `prosa_en_vez_de_tool`: 2
    - otro: 2
- `loop_detected`: 2

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 2/3 | 0.667 |
| extreme | 1/9 | 0.111 |
| hard | 2/6 | 0.333 |
| medium | 1/6 | 0.167 |

**Modos de fallo:**

- `exhausted_iterations`: 12
- `success`: 6
- `prosa_en_vez_de_tool`: 5
    - otro: 5
- `loop_detected`: 1

### react_generico

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 2/3 | 0.667 |
| extreme | 2/9 | 0.222 |
| hard | 0/6 | 0.0 |
| medium | 3/6 | 0.5 |

**Modos de fallo:**

- `exhausted_iterations`: 9
- `success`: 7
- `prosa_en_vez_de_tool`: 5
    - otro: 5
- `loop_detected`: 3

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 2/3 | 0.667 |
| extreme | 0/9 | 0.0 |
| hard | 1/6 | 0.167 |
| medium | 3/6 | 0.5 |

**Modos de fallo:**

- `loop_detected`: 8
- `success`: 6
- `exhausted_iterations`: 6
- `crash`: 4
