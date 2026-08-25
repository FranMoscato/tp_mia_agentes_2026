# Evaluación M3 — resumen

- Fecha: 20260825-192620
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-lite-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `acc8310`
- max_iterations: 30 · repeats: 1
- Casos totales: 8

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| react | 0.5 [0.215, 0.785] | 0.5 / 0.5 (k=1) | 2.54x | 229540 | 27.953 / 33.189 |

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 1/1 | 1.0 |
| extreme | 1/3 | 0.333 |
| hard | 0/2 | 0.0 |
| medium | 2/2 | 1.0 |

**Modos de fallo:**

- `success`: 4
- `exhausted_iterations`: 4
