# Evaluación M3 — resumen

- Fecha: 20260825-204157
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-lite-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `14e4f62`
- max_iterations: 30 · repeats: 3
- Casos totales: 96

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.667 [0.467, 0.82] | 0.875 / 0.5 (k=3) | 2.56x | 161362 | 25.379 / 33.246 |
| react | 0.792 [0.595, 0.908] | 1.0 / 0.625 (k=3) | 2.36x | 143340 | 24.866 / 31.125 |
| react_generico | 0.625 [0.427, 0.788] | 0.875 / 0.375 (k=3) | 2.8x | 114328 | 26.176 / 30.527 |
| summarizer | 0.375 [0.212, 0.573] | 0.5 / 0.25 (k=3) | 1.79x | 481678 | 98.696 / 217.458 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 4/9 | 0.444 |
| hard | 3/6 | 0.5 |
| medium | 6/6 | 1.0 |

**Modos de fallo:**

- `success`: 16
- `exhausted_iterations`: 7
- `loop_detected`: 1

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 6/9 | 0.667 |
| hard | 4/6 | 0.667 |
| medium | 6/6 | 1.0 |

**Modos de fallo:**

- `success`: 19
- `exhausted_iterations`: 3
- `loop_detected`: 2

### react_generico

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 4/9 | 0.444 |
| hard | 4/6 | 0.667 |
| medium | 4/6 | 0.667 |

**Modos de fallo:**

- `success`: 15
- `exhausted_iterations`: 7
- `prosa_en_vez_de_tool`: 2
    - otro: 2

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 2/3 | 0.667 |
| extreme | 0/9 | 0.0 |
| hard | 1/6 | 0.167 |
| medium | 6/6 | 1.0 |

**Modos de fallo:**

- `success`: 9
- `loop_detected`: 9
- `exhausted_iterations`: 3
- `crash`: 2
- `prosa_en_vez_de_tool`: 1
    - otro: 1
