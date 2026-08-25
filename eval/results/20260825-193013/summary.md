# Evaluación M3 — resumen

- Fecha: 20260825-193013
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-lite-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `ea4800c`
- max_iterations: 30 · repeats: 3
- Casos totales: 96

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.625 [0.427, 0.788] | 0.75 / 0.5 (k=3) | 2.7x | 135129 | 13.219 / 31.648 |
| react | 0.667 [0.467, 0.82] | 0.75 / 0.5 (k=3) | 2.64x | 142169 | 16.873 / 32.549 |
| react_generico | 0.583 [0.388, 0.755] | 0.75 / 0.375 (k=3) | 2.27x | 73179 | 10.612 / 29.747 |
| summarizer | 0.542 [0.351, 0.721] | 0.75 / 0.375 (k=3) | 2.22x | 195278 | 54.614 / 271.203 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 3/9 | 0.333 |
| hard | 4/6 | 0.667 |
| medium | 5/6 | 0.833 |

**Modos de fallo:**

- `success`: 15
- `crash`: 6
- `exhausted_iterations`: 3

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 3/9 | 0.333 |
| hard | 5/6 | 0.833 |
| medium | 5/6 | 0.833 |

**Modos de fallo:**

- `success`: 16
- `crash`: 4
- `loop_detected`: 2
- `exhausted_iterations`: 2

### react_generico

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 1/9 | 0.111 |
| hard | 5/6 | 0.833 |
| medium | 5/6 | 0.833 |

**Modos de fallo:**

- `success`: 14
- `crash`: 6
- `prosa_en_vez_de_tool`: 2
    - otro: 2
- `exhausted_iterations`: 2

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 1/9 | 0.111 |
| hard | 3/6 | 0.5 |
| medium | 6/6 | 1.0 |

**Modos de fallo:**

- `success`: 13
- `crash`: 8
- `exhausted_iterations`: 1
- `prosa_en_vez_de_tool`: 1
    - otro: 1
- `loop_detected`: 1
