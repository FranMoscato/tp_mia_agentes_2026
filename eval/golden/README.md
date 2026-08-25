# Golden set (M3)

Trazas **reales** versionadas de una corrida del agente sobre los 8 escenarios.
A diferencia de `eval/results/` (que está en `.gitignore` por ser efímero), esto
**vive en el repo**: es el conjunto de referencia sobre el que se etiqueta a mano
y se corre la meta-eval del judge.

## Archivos

- `cases.jsonl` — las 8 trazas (una por escenario), formato de `eval/run.py`.
  Corrida: `nova-lite-v1:0`, config `react`, `max_iterations=30` (piloto
  2026-08-25). Todas dieron `goal_achieved=false`: el modo de fallo dominante
  fue **prosa en vez de tool_call** (ver el informe).
- `labels.template.jsonl` — plantilla de etiquetas humanas para la meta-eval.

## Split dev / holdout (#17)

El dataset se toca libremente en **dev**; el **holdout** solo se mira al final,
antes de decidir, para no sobreajustar prompt/gate a escenarios concretos.

- **dev** (iterar libremente): `study-with-key`, `color-locks`,
  `library-search`, `extreme-archive` (uno por dificultad).
- **holdout** (solo eval final): `apartment-keys`, `office-sequence`,
  `vault-combination`, `backtracking-vault`.

## Meta-eval del judge (kappa, #16)

1. Etiquetá a mano cada traza con `exploracion_metodica` (1-5) según la rúbrica
   de `eval/judge.py`. Hay un **borrador** en `labels.draft.jsonl` (basado en las
   trazas del piloto) para acelerar: **revisalo a mano** y, cuando estés de
   acuerdo, guardalo como `labels.jsonl` (el baseline humano debe ser genuino).
   La plantilla vacía está en `labels.template.jsonl`.
2. Corré el judge sobre `cases.jsonl` para obtener sus puntajes.
3. Compará con `cohen_kappa(judge, humano)` (en `eval/judge.py`): un kappa alto
   indica que el judge es confiable; uno bajo, que la rúbrica o el prompt del
   judge necesitan ajuste antes de confiar en sus números.
