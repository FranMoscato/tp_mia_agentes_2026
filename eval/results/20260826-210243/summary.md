# Evaluación M3 — resumen

- Fecha: 20260826-210243
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-micro-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `cda9111`
- max_iterations: 30 · repeats: 5
- Casos totales: 80

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| gate | 0.45 [0.307, 0.602] | 0.5 / 0.375 (k=5) | 3.14x | 270333 | 22.478 / 29.008 |
| react | 0.3 [0.181, 0.454] | 0.625 / 0.125 (k=5) | 1.96x | 379136 | 24.09 / 30.159 |

### gate

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 5/5 | 1.0 |
| extreme | 5/15 | 0.333 |
| hard | 3/10 | 0.3 |
| medium | 5/10 | 0.5 |

**Modos de fallo:**

- `success`: 18
- `exhausted_iterations`: 12
- `tool_errors`: 5
- `loop_detected`: 4
- `prosa_en_vez_de_tool`: 1
    - otro: 1

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 4/5 | 0.8 |
| extreme | 0/15 | 0.0 |
| hard | 2/10 | 0.2 |
| medium | 6/10 | 0.6 |

**Modos de fallo:**

- `exhausted_iterations`: 15
- `success`: 12
- `prosa_en_vez_de_tool`: 7
    - otro: 7
- `loop_detected`: 6
