# Evaluación M3 — resumen

- Fecha: 20260826-223130
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-lite-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `8123ac6`
- max_iterations: 30 · repeats: 3
- Casos totales: 24

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| summarizer | 0.417 [0.245, 0.612] | 0.5 / 0.375 (k=3) | 1.76x | 445925 | 91.839 / 201.907 |

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 0/9 | 0.0 |
| hard | 1/6 | 0.167 |
| medium | 6/6 | 1.0 |

**Modos de fallo:**

- `success`: 10
- `loop_detected`: 7
- `exhausted_iterations`: 6
- `prosa_en_vez_de_tool`: 1
    - otro: 1
