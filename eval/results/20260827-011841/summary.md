# Evaluación M3 — resumen

- Fecha: 20260827-011841
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-lite-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `d53abc6`
- max_iterations: 30 · repeats: 3
- Casos totales: 24

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| react | 0.708 [0.508, 0.851] | 1.0 / 0.5 (k=3) | 2.46x | 163338 | 23.101 / 30.16 |

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 5/9 | 0.556 |
| hard | 3/6 | 0.5 |
| medium | 6/6 | 1.0 |

**Modos de fallo:**

- `success`: 17
- `exhausted_iterations`: 7
