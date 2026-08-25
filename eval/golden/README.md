# Golden set (M3)

Trazas **reales** versionadas de una corrida del agente sobre los 8 escenarios.
A diferencia de `eval/results/` (que está en `.gitignore` por ser efímero), esto
**vive en el repo**: es el conjunto de referencia sobre el que se corre la
meta-eval del judge.

## Archivos

- `cases.jsonl` — las 8 trazas (una por escenario), formato de `eval/run.py`.
  Corrida: `nova-lite-v1:0`, config `react`, `max_iterations=30` (piloto
  2026-08-25). Todas dieron `goal_achieved=false`: el modo de fallo dominante
  fue **prosa en vez de tool_call** (ver el informe).
- `labels.jsonl` — la **referencia determinística** (checklist binario) generada
  por `eval/kappa.py` a partir de `reference_verdict` (en `eval/judge.py`). Es un
  proxy objetivo y reproducible del "baseline", no un juicio a ojo.
- `labels.template.jsonl` — plantilla por si se quiere sobre-escribir la
  referencia con etiquetas humanas manuales (mismo esquema binario).
- `judged.jsonl` / `judge_summary.json` — salida del judge-LLM sobre `cases.jsonl`.
- `kappa_summary.json` — kappa por criterio (judge vs. referencia).

## Split dev / holdout (#17)

El dataset se toca libremente en **dev**; el **holdout** solo se mira al final,
antes de decidir, para no sobreajustar prompt/gate a escenarios concretos.

- **dev** (iterar libremente): `study-with-key`, `color-locks`,
  `library-search`, `extreme-archive` (uno por dificultad).
- **holdout** (solo eval final): `apartment-keys`, `office-sequence`,
  `vault-combination`, `backtracking-vault`.

## Meta-eval del judge (kappa, #16)

El judge de `eval/judge.py` es un **checklist binario** de 3 criterios
(`exploracion_ordenada`, `acciones_apoyadas`, `sin_redundancia_evitable`).
Medimos si es confiable comparándolo contra una **referencia determinística**
derivada de propiedades objetivas de la traza (`reference_verdict`): así el
baseline no es otro juicio subjetivo ni el mismo LLM (evita circularidad).

```bash
# 1) el judge-LLM puntúa las trazas (usá un modelo DISTINTO del agente)
python eval/judge.py eval/golden/cases.jsonl --judge-model llama3.2
# 2) kappa de Cohen por criterio (judge vs. referencia determinística)
python eval/kappa.py eval/golden/cases.jsonl
```

Un kappa alto = el judge acuerda con la referencia y es confiable; uno ≈0 o
negativo = no acuerda mejor que el azar, y hay que arreglar el judge (modelo más
capaz, prompt) antes de confiar en sus puntajes. **Nota:** con las 8 trazas del
piloto (todas fallidas, trayectorias cortas) la referencia satura en algunos
criterios y el kappa es frágil; una calibración definitiva necesita trazas con
variación real (éxitos, trayectorias largas) de un modelo más capaz. Ver §3.4
del informe de M3.
