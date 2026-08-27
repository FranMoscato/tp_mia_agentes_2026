# Corridas guardadas

Cada directorio es una corrida de [`eval/run.py`](../run.py), nombrado con su
timestamp. El `summary.json` de cada uno versiona `provider`/`model`/`repeats`/
`git_commit` en su `meta`, así que **el nombre no es la fuente de verdad** — esta
tabla es solo para orientarse.

`scripts/comparar_modelos_m3.py` se queda con la corrida **de más casos por
modelo**, así que los pilotos chicos no ensucian los gráficos.

## La corrida canónica

**`20260825-204157`** — `nova-lite`, 4 configs × 8 escenarios × 3 repeats = **96
casos**. Es la que sostiene el §3 y el §4 del [informe](../../INFORME_M3.md).
Tiene además `judged.jsonl` y `kappa_summary.json` del judge `nova-pro`.

## Todas

| Corrida | Casos | Qué es |
|---|---:|---|
| `20260825-000528` | 1 | piloto de la sesión previa (sin `provider` en el meta) |
| `20260825-000630` | 8 | piloto de la sesión previa (sin `provider` en el meta) |
| `20260825-010249` | 1 | piloto `qwen2.5:3b` |
| `20260825-010410` | 24 | piloto `qwen2.5:3b`, repeats 1 |
| `20260825-011809` | 72 | **baseline local canónico** — `qwen2.5:3b`, repeats 3 |
| `20260825-014434` | 72 | cross-modelo local — `llama3.2`, repeats 3 |
| `20260825-120129` | 8 | piloto `qwen2.5:3b` |
| `20260825-192620` | 8 | primer piloto en Bedrock (`nova-lite`): 4/8, rompió el cero |
| `20260825-193013` | 96 | ⚠️ **CONTAMINADA** — 22 casos murieron con `ExpiredTokenException` a mitad. Se conserva como evidencia del fallo, **no usar sus números** |
| `20260825-204157` | 96 | ⭐ **CANÓNICA** — `nova-lite`, 4 configs, repeats 3 |
| `20260826-190401` | 96 | Escalera A — `nova-micro` |
| `20260826-205117` | 24 | Escalera A — `nova-pro` (solo brazo `react`) |
| `20260826-210243` | 80 | `micro` con repeats 5 (`react`+`gate`), para el poder estadístico del §4.2 |
| `20260826-223130` | 24 | re-run del brazo `summarizer` tras el fix del crash (`lite`) |
| `20260826-231045` | 24 | re-run del brazo `summarizer` tras el fix del crash (`micro`) |
| `20260826-233443` | 96 | Escalera B — `llama3.1` 8B Q4_K_M, corrida por Franco |
| `20260827-004743` | 24 | Experimento 4 — `loop_breaker` |
| `20260827-011841` | 24 | Experimento 5 — ventana de memoria 120 |

## Una advertencia operativa

**No corras `git add -A` ni cambies de rama con un eval en curso.** El
`cases.jsonl` se escribe incrementalmente: si git captura el archivo a medio
escribir y después un `checkout` lo restaura, la corrida queda **truncada** y el
`summary.json` (que se computa en memoria) queda inconsistente con él. Nos pasó
una vez y hubo que relanzar.
