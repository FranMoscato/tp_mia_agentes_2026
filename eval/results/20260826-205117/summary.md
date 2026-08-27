# Evaluación M3 — resumen

- Fecha: 20260826-205117
- Módulo del agente: `student_framework`
- Provider/modelo: `bedrock` / `amazon.nova-pro-v1:0` · perfil AWS: `948169713308_udesasbx_IsbUsersPS`
- Versión de prompt: `escape-v1` · commit: `884653a`
- max_iterations: 30 · repeats: 3
- Casos totales: 24

## Métricas por configuración

_Latencia en percentiles (nunca promedio); costo por caso resuelto; pass@k = resolver en AL MENOS UNO de los k intentos (capacidad); pass^k = resolver en TODOS (confiabilidad)._

| Config | Accuracy (IC95%) | pass@k / pass^k | Overhead vs óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| react | 0.625 [0.427, 0.788] | 1.0 / 0.375 (k=3) | 2.47x | 192136 | 29.511 / 45.158 |

### react

**Accuracy por dificultad:**

| Dificultad | Resueltos | Accuracy |
|---|---:|---:|
| easy | 3/3 | 1.0 |
| extreme | 4/9 | 0.444 |
| hard | 4/6 | 0.667 |
| medium | 4/6 | 0.667 |

**Modos de fallo:**

- `success`: 15
- `exhausted_iterations`: 4
- `prosa_en_vez_de_tool`: 3
    - otro: 3
- `loop_detected`: 2
