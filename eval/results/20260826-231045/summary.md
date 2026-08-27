# Evaluación M3 — resumen

- Fecha: 20260826-231045
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-micro-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `8123ac6`
- max_iterations: 30 · repeats: 3
- Casos totales: 24

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| summarizer | 0.125 [0.043, 0.31] | 0.375 / 0.0 (k=3) | 1.82x | 1737075 | 79.792 / 125.587 |

### summarizer

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 1/3 | 0.333 |
| extreme | 0/9 | 0.0 |
| hard | 0/6 | 0.0 |
| medium | 2/6 | 0.333 |

**Modos de fallo:**

- `loop_detected`: 14
- `exhausted_iterations`: 5
- `success`: 3
- `prosa_en_vez_de_tool`: 2
    - otro: 2
