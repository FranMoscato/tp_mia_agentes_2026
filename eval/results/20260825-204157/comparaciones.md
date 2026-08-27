# Contrastes entre brazos (estratificados por escenario)

- Casos analizados: **96**
- Fuentes: `eval/results/20260825-204157/cases.jsonl`

> El test **agrupado** junta todos los casos de un brazo contra los del otro. El **CMH** estratifica por escenario, que es el diseño real: los dos brazos corren los mismos escenarios, y el escenario es la fuente dominante de varianza. `*` marca p < 0.05.

| Experimento | base | comparado | Δ | p agrupado | p CMH | estratos |
|---|---:|---:|---:|---:|---:|---:|
| Experimento 1 — resumen de estado on/off | `react` 0.792 | `summarizer` 0.375 | -0.417 | 0.0034 * | 0.0015 * | 6/8 |
| Experimento 2 — gate determinístico on/off | `react` 0.792 | `gate` 0.667 | -0.125 | 0.3299 | 0.4219 | 4/8 |
| Experimento 3 — prompt escape-v1 vs. genérico | `react` 0.792 | `react_generico` 0.625 | -0.167 | 0.2040 | 0.2765 | 5/8 |

## Experimento 1 — resumen de estado on/off

`react` 19/24 = 0.792 IC95% [0.595, 0.908] · `summarizer` 9/24 = 0.375 IC95% [0.212, 0.573]

Estratos descartados por no tener varianza (mismo resultado en ambos brazos): `color-locks`, `apartment-keys`. No aportan al contraste pero sí inflarían el denominador del test agrupado.

| Escenario | base | comparado | Δ |
|---|---:|---:|---:|
| `color-locks` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `apartment-keys` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `study-with-key` | 3/3 (1.000) | 2/3 (0.667) | -0.333 |
| `library-search` | 1/3 (0.333) | 0/3 (0.000) | -0.333 |
| `vault-combination` | 1/3 (0.333) | 0/3 (0.000) | -0.333 |
| `office-sequence` | 3/3 (1.000) | 1/3 (0.333) | -0.667 |
| `backtracking-vault` | 2/3 (0.667) | 0/3 (0.000) | -0.667 |
| `extreme-archive` | 3/3 (1.000) | 0/3 (0.000) | -1.000 |

## Experimento 2 — gate determinístico on/off

`react` 19/24 = 0.792 IC95% [0.595, 0.908] · `gate` 16/24 = 0.667 IC95% [0.467, 0.820]

Estratos descartados por no tener varianza (mismo resultado en ambos brazos): `study-with-key`, `color-locks`, `extreme-archive`, `apartment-keys`. No aportan al contraste pero sí inflarían el denominador del test agrupado.

| Escenario | base | comparado | Δ |
|---|---:|---:|---:|
| `library-search` | 1/3 (0.333) | 2/3 (0.667) | +0.333 |
| `study-with-key` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `color-locks` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `extreme-archive` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `apartment-keys` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `vault-combination` | 1/3 (0.333) | 0/3 (0.000) | -0.333 |
| `backtracking-vault` | 2/3 (0.667) | 1/3 (0.333) | -0.333 |
| `office-sequence` | 3/3 (1.000) | 1/3 (0.333) | -0.667 |

## Experimento 3 — prompt escape-v1 vs. genérico

`react` 19/24 = 0.792 IC95% [0.595, 0.908] · `react_generico` 15/24 = 0.625 IC95% [0.427, 0.788]

Estratos descartados por no tener varianza (mismo resultado en ambos brazos): `study-with-key`, `extreme-archive`, `apartment-keys`. No aportan al contraste pero sí inflarían el denominador del test agrupado.

| Escenario | base | comparado | Δ |
|---|---:|---:|---:|
| `library-search` | 1/3 (0.333) | 2/3 (0.667) | +0.333 |
| `study-with-key` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `extreme-archive` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `apartment-keys` | 3/3 (1.000) | 3/3 (1.000) | +0.000 |
| `vault-combination` | 1/3 (0.333) | 1/3 (0.333) | +0.000 |
| `office-sequence` | 3/3 (1.000) | 2/3 (0.667) | -0.333 |
| `color-locks` | 3/3 (1.000) | 1/3 (0.333) | -0.667 |
| `backtracking-vault` | 2/3 (0.667) | 0/3 (0.000) | -0.667 |
