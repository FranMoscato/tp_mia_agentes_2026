# Dataset complementario (no oficial)

Los 8 escenarios de `scenarios/` son **el dataset del enunciado**
([ENUNCIADO_M3.md](../ENUNCIADO_M3.md)), con sus óptimos tabulados. Este
directorio **no los toca**: agregar casos ahí cambiaría el objeto de evaluación
y rompería la comparabilidad con todas las corridas anteriores.

## Por qué existe

El contraste entre brazos se estratifica por escenario ([`eval/stats.py`](../eval/stats.py)).
Un estrato **saturado** —mismo resultado en ambos brazos— no aporta información
al test. En el dataset oficial, con `nova-micro`, dos de los ocho se saturan en
0/8 (`backtracking-vault`, `vault-combination`) y varios se saturan en 1.00 con
`nova-lite`. Quedan 4-6 estratos útiles de 8.

Ahí está el cuello: **para el mismo presupuesto, un escenario nuevo de
dificultad intermedia rinde más que un repeat extra.** El repeat achica el error
dentro de estratos que ya tenés; el escenario agrega un estrato informativo.

Estos cuatro apuntan al hueco entre `medium` y `extreme`: difíciles para que no
saturen en 1.00, resolubles para que no saturen en 0.00.

## Cómo correrlos

```bash
python eval/run.py --scenarios-dir scenarios_extra --repeats 3
```

Los resultados salen a `eval/results/<timestamp>/` como cualquier corrida y se
comparan con `eval/comparar_brazos.py`. **No los mezcles con el dataset oficial
en una misma tabla del informe**: son datasets distintos.
