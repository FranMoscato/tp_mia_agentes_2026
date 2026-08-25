# Evaluación M3 — resumen

- Fecha: 20260825-120129
- Módulo del agente: `student_framework`
- Provider/modelo: `ollama` / `qwen2.5:3b`
- Versión de prompt: `escape-v1` · commit: `a19744e`
- max_iterations: 12 · repeats: 1
- Casos totales: 8

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| react | 0.0 [0.0, 0.49] | 0.0 / 0.0 (k=1) | — | — | 6.757 / 10.316 |
| react_generico | 0.0 [0.0, 0.49] | 0.0 / 0.0 (k=1) | — | — | 5.521 / 8.323 |

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/1 | 0.0 |
| hard | 0/1 | 0.0 |
| medium | 0/2 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 4
    - inversion_de_rol: 3
    - otro: 1

### react_generico

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 0/1 | 0.0 |
| hard | 0/1 | 0.0 |
| medium | 0/2 | 0.0 |

**Modos de fallo:**

- `prosa_en_vez_de_tool`: 3
    - otro: 3
- `tool_errors`: 1
