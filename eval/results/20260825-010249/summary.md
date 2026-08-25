# Evaluación M3 — resumen

- Fecha: 20260825-010249
- Módulo del agente: `student_framework`
- Provider/modelo: `ollama` / `qwen2.5:3b`
- Versión de prompt: `escape-v1` · commit: `b975275`
- max_iterations: 30 · repeats: 1
- Casos totales: 1

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass^k = resolver el escenario en los k intentos._

| Config | Accuracy (IC95%) | pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| react | 1.0 [0.207, 1.0] | 1.0 (1/1, k=1) | 1.67x | 15919 | 15.27 / 15.27 |

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 1/1 | 1.0 |

**Modos de fallo:**

- `success`: 1
