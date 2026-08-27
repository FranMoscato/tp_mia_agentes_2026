# Contrastes entre brazos (estratificados por escenario)

- Casos analizados: **176**
- Fuentes: `eval/results/20260826-190401/cases.jsonl`, `eval/results/20260826-210243/cases.jsonl`

> El test **agrupado** junta todos los casos de un brazo contra los del otro. El **CMH** estratifica por escenario, que es el diseño real: los dos brazos corren los mismos escenarios, y el escenario es la fuente dominante de varianza. `*` marca p < 0.05.

| Experimento | base | comparado | Δ | p agrupado | p CMH | estratos |
|---|---:|---:|---:|---:|---:|---:|
| Experimento 1 — resumen de estado on/off | `react` 0.281 | `summarizer` 0.250 | -0.031 | 0.7694 | 0.9759 | 6/8 |
| Experimento 2 — gate determinístico on/off | `react` 0.281 | `gate` 0.422 | +0.141 | 0.0957 | 0.0338 * | 6/8 |
| Experimento 3 — prompt escape-v1 vs. genérico | `react` 0.281 | `react_generico` 0.292 | +0.010 | 0.9231 | 0.8295 | 6/8 |

## Experimento 1 — resumen de estado on/off

`react` 18/64 = 0.281 IC95% [0.186, 0.401] · `summarizer` 6/24 = 0.250 IC95% [0.120, 0.449]

Estratos descartados por no tener varianza (mismo resultado en ambos brazos): `vault-combination`, `backtracking-vault`. No aportan al contraste pero sí inflarían el denominador del test agrupado.

| Escenario | base | comparado | Δ |
|---|---:|---:|---:|
| `color-locks` | 1/8 (0.125) | 1/3 (0.333) | +0.208 |
| `vault-combination` | 0/8 (0.000) | 0/3 (0.000) | +0.000 |
| `backtracking-vault` | 0/8 (0.000) | 0/3 (0.000) | +0.000 |
| `office-sequence` | 3/8 (0.375) | 1/3 (0.333) | -0.042 |
| `study-with-key` | 6/8 (0.750) | 2/3 (0.667) | -0.083 |
| `apartment-keys` | 6/8 (0.750) | 2/3 (0.667) | -0.083 |
| `library-search` | 1/8 (0.125) | 0/3 (0.000) | -0.125 |
| `extreme-archive` | 1/8 (0.125) | 0/3 (0.000) | -0.125 |

## Experimento 2 — gate determinístico on/off

`react` 18/64 = 0.281 IC95% [0.186, 0.401] · `gate` 27/64 = 0.422 IC95% [0.309, 0.544]

Estratos descartados por no tener varianza (mismo resultado en ambos brazos): `vault-combination`, `backtracking-vault`. No aportan al contraste pero sí inflarían el denominador del test agrupado.

| Escenario | base | comparado | Δ |
|---|---:|---:|---:|
| `extreme-archive` | 1/8 (0.125) | 7/8 (0.875) | +0.750 |
| `study-with-key` | 6/8 (0.750) | 8/8 (1.000) | +0.250 |
| `apartment-keys` | 6/8 (0.750) | 8/8 (1.000) | +0.250 |
| `office-sequence` | 3/8 (0.375) | 4/8 (0.500) | +0.125 |
| `vault-combination` | 0/8 (0.000) | 0/8 (0.000) | +0.000 |
| `backtracking-vault` | 0/8 (0.000) | 0/8 (0.000) | +0.000 |
| `color-locks` | 1/8 (0.125) | 0/8 (0.000) | -0.125 |
| `library-search` | 1/8 (0.125) | 0/8 (0.000) | -0.125 |

## Experimento 3 — prompt escape-v1 vs. genérico

`react` 18/64 = 0.281 IC95% [0.186, 0.401] · `react_generico` 7/24 = 0.292 IC95% [0.149, 0.492]

Estratos descartados por no tener varianza (mismo resultado en ambos brazos): `vault-combination`, `backtracking-vault`. No aportan al contraste pero sí inflarían el denominador del test agrupado.

| Escenario | base | comparado | Δ |
|---|---:|---:|---:|
| `extreme-archive` | 1/8 (0.125) | 2/3 (0.667) | +0.542 |
| `apartment-keys` | 6/8 (0.750) | 3/3 (1.000) | +0.250 |
| `vault-combination` | 0/8 (0.000) | 0/3 (0.000) | +0.000 |
| `backtracking-vault` | 0/8 (0.000) | 0/3 (0.000) | +0.000 |
| `study-with-key` | 6/8 (0.750) | 2/3 (0.667) | -0.083 |
| `color-locks` | 1/8 (0.125) | 0/3 (0.000) | -0.125 |
| `library-search` | 1/8 (0.125) | 0/3 (0.000) | -0.125 |
| `office-sequence` | 3/8 (0.375) | 0/3 (0.000) | -0.375 |
