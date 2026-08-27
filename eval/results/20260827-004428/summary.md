# Evaluación M3 — resumen

- Fecha: 20260827-004428
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-lite-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `b57afb2`
- max_iterations: 4 · repeats: 1
- Casos totales: 1

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| react | 0.0 [0.0, 0.793] | 0.0 / 0.0 (k=1) | — | — | 5.689 / 5.689 |

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/1 | 0.0 |

**Modos de fallo:**

- `exhausted_iterations`: 1
