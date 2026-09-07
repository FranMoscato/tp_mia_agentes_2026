# Informe M3: evaluación sobre salas de escape

Esta entrega representa el tercer informe de los tres milestones del trabajo practico de agentes. M1 fue el agente y sus
herramientas, M2 memoria y robustez, acá lo evaluamos jugando una sala de
escape.

Las 5 secciones tienen datos reales de Bedrock: la corrida canónica es con
amazon.nova-lite-v1:0, 8 escenarios x 4 configuraciones x 3 repeticiones, 96
casos. Evaluamos la capacidad entre modelos como mortor del agente (nova-micro, nova-lite y nova-pro),
y como el mas fuerte se desarrollaba como juez (nova-pro juzgando a nova-lite, con cobertura completa). Las corridas locales (qwen2.5:3b, llama3.2) se conservan como comparación entre
modelos.

## Resumen

Aplicamos el framework de M1 y M2 a un mundo tipo sala de escape (inspirado
en ALFWorld): el agente tiene que abrir la puerta principal usando cinco
tools (look, examine, take, use, go). Construimos una infraestructura de
evaluación reproducible (eval/run.py) que corre el agente sobre los 8
escenarios, guarda la traza de cada caso y calcula métricas cuantitativas más
una dimensión cualitativa evaluada por otro LLM (eval/judge.py). Comparamos
cinco ejes del framework con experimentos controlados (resumen de estado,
gate determinístico, prompt especializado vs. genérico, corte de loop en
runtime, y tamaño de la ventana de memoria) y categorizamos los modos de
fallo mirando las trazas reales.

Los cuatro resultados principales:

1. El agente resuelve los 8 escenarios, pero no de forma confiable: puede
   resolverlos todos en algún intento (pass@k = 1.0) pero solo 5 de 8 en los
   tres intentos (pass^k = 0.625). Nuestro limitante no es capacidad, es
   consistencia.
2. Testeamos el impacto de aumentar la capacidad del modelo sobre la performance del agente,    comparando nova-micro, nova-lite y nova-pro. La performance mejora fuertemente al principio, pero luego se estanca. Esto indica que el próximo cuello de botella probablemente no sea un modelo más grande, sino un mejor harness. El foco pasa entonces a optimizar el framework del agente: prompting, uso de herramientas, manejo del estado, planificación y estrategias de recuperación.
3. Al introducir un resumen de estado antes de cada mensaje enviado al LLM, observamos un deterioro significativo de la performance, principalmente asociado a la aparición de loops. La accuracy se redujo a la mitad, el costo por caso resuelto aumentó 3,4× y la latencia 7×; además, 9 de 24 casos entraron en loops de hasta 23 llamadas idénticas. Si bien esto sugiere que el mecanismo de resumen puede estar interfiriendo con el proceso de decisión del agente, es posible que el problema se deba a una implementación no óptima del resumen de estado, por lo que sería necesario refinar este componente antes de concluir que el enfoque en sí resulta perjudicial.
4. Al introducir el gate deterministico (sobre el uso de objetos fuera del inventario o IDs inexistentes) y evaluar su impacto con modelos de distinta capacidad, observamos que su efecto depende del modelo utilizado. El mecanismo mejora significativamente la performance de los modelos más débiles, mientras que en los modelos más capaces el beneficio es marginal o inexistente. Esto sugiere que el gate funciona principalmente como un mecanismo de seguridad o robustez para compensar limitaciones del modelo, cuyo valor disminuye a medida que aumenta la capacidad del modelo.

## 1. Cómo lo encaramos

El agente de M3 es el mismo de M1 y M2, sin bifurcar: system prompt más
herramientas y estrategias de administracion de memoria, corriendo dentro del mismo bucle. 

El bucle y las herramientas vienen de M1: el runner registra los verbos del
mundo como herramientas y el agente las ejecuta como siempre. Los errores
vuelven como observaciones en vez de romper el bucle, lo cual deja que el
modelo se corrija solo, algo clave en un dominio donde equivocarse de llave o
de identificador es un caso posible. El estado y la memoria vienen de M2: la sala
de escape depende de lo ya observado, tomado y abierto, y la ventana
deslizante conserva el objetivo inicial mientras descarta los turnos del
medio. Los escenarios de varias salas (apartment-keys, office-sequence)
ponen esto a prueba: hay que navegar, recordar el mapa y volver.

Del sistema completo (entorno, agente, evaluación),cuenta tanto con workflow/procesos determinístico
(el gate, la actualizacion de la ventana de memoria, el harness, la búsqueda del camino óptimo) o
workflow con un LLM en un paso fijo (el resumidor y el juez, que llaman al
LLM pero nunca deciden el control de flujo).

![Arquitectura de la solución: entorno, agente y evaluación](docs/m3_arquitectura.png)

![El loop ReAct por dentro: qué decide el LLM vs. qué es control-flow fijo](docs/m3_loop_react.png)

Agregamos tres cosas específicas para M3, todas detrás de configuración para
no tocar M1 ni M2:
 1.  El system prompt es inyectable: el que trae el agente por
defecto es genérico, y el runner de M3 le inyecta uno propio de sala de
escape, versionado, sin que una corrida de M1/M2 arranque creyendo que está
en el juego.
2. Un resumidor de estado opcional: antes de cada llamada puede
re-derivar un estado estructurado (inventario, ubicación, salidas) con una
llamada estructurada extra al LLM. Al no permitir texto libre al modelo,
obligamos al LLM a curar la información con menos pérdida. Cabe destacar que el costo extra en tokens se cuenta de manera aparte para poder realizar comparaciones mas especificas.
3.  Un gate determinístico opcional: un
chequeo simple que bloquea, antes de ejecutar, usar un objeto fuera del
inventario o un identificador inexistente, algo que ningún prompt garantiza
con certeza. 

Ninguna de las tres es el comportamiento por defecto: el agente
base es el bucle normal con el prompt de escape, sin resumen ni gate.

## 2. Cómo medimos

Medimos sobre el estado del mundo, no sobre lo que dice el agente: un
escenario cuenta como resuelto solo si una verificación de código confirma el
cambio físico (la puerta abierta). Reportamos varias dimensiones
en vez de un puntaje único ya que las restricciones duras (abrió o no) son un filtro binario, no un término de un promedio:

 - **Accuracy**, con intervalo de Wilson al 95%, mide la fracción de casos
resueltos (Wilson se comporta de manera mas precisa que un intervalo normal cerca de 0 o 1).
- **pass@k** mide si el agente resuelve en al menos uno de k intentos (capacidad)
- **pass^k** Mide la consistencia en la capacidad de resolucion (confiabilidad)
- El
**overhead** contra el camino óptimo es la cantidad de llamadas dividida por el camino
más corto posible, medido sobre los casos resueltos.


![Grafo de estados de study-with-key con el óptimo del BFS resaltado](docs/m3_grafo_estados.png)

El camino resaltado (examinar la alfombra, tomar la llave dorada, usarla) son
tres acciones y es el óptimo para study-with-key. El escritorio es un señuelo
con cajones vacíos: revisarlo de nuevo no acerca al objetivo, y es
justamente ese tipo de exploración de más lo que penaliza el overhead y lo
que evaluara el juez.

- Los **tokens consumidos** por caso resuelto son los tokens totales (incluidos los fallidos)
sobre la cantidad de éxitos, porque lo que nos importa es cuánto cuesta un
éxito, no el promedio por corrida (medimos en tokens porque con Ollama el
costo es cero, y el costo en dólares es un derivado que solo tiene sentido
con un proveedor pago).
- La **latencia** se midio en percentiles 50 y 95, nunca en
promedio, ya que el mismo esconde justamente los casos lentos.

 - La **dimensión cualitativa** medira si el agente exploró con metodologia (de manera "logica"), algo que no se puede verificar con código (si miró antes de tomar, si repitió acciones, si usó algo que no
tenía). El **juez** puntúa la trayectoria completa con una rúbrica, mirando la traza real
de llamadas, y devuelve el
puntaje con su justificación para poder auditarlo.

    Un juez es un instrumento que debe ser calibrado: lo calibramos comparando su veredicto contra uno determinístico derivado de propiedades objetivas de la traza, con el coeficiente kappa de Cohen, que corrige el acuerdo esperable por azar (un juez que siempre dice lo mismo puede tener 95% de acierto aparente y kappa 0). Si el kappa da bajo no confiamos en sus números aunque el juez ya esté armado, y es justo lo que pasó con dos de los tres criterios (más abajo).

Todo sale de correr eval/run.py sin pasos manuales. Cada corrida guarda la
traza de cada caso y un resumen, versionando modelo, prompt y commit de git.
El cálculo de métricas, la búsqueda del óptimo, el juez y los contrastes
estadísticos están testeados sin depender de ningún LLM real.

**Cómo comparamos dos configuraciones.** Lo intuitivo sería juntar todos los
casos de cada una y comparar los dos porcentajes, pero eso pierde
información: las dos corren los mismos 8 escenarios, y los escenarios son
muy distintos entre sí (en study-with-key casi todo sale bien, en
backtracking-vault casi nada). Si se mezclan los casos, esa diferencia entre
escenarios se suma al ruido y tapa la diferencia que realmente nos interesa.
La solución es comparar dentro de cada escenario y recién después combinar
los ocho resultados en un solo número: es el test de Cochran-Mantel-Haenszel.
Esto no es un detalle menor: en uno de los experimentos, juntar todos los
casos da un p-valor de 0.0957 (no concluyente) y estratificar por escenario
da 0.0338 (significativo), con exactamente los mismos datos. Por eso
reportamos los dos números en vez de solo el que conviene.

## 3. Resultados

**Corrida canónica:** Bedrock con nova-lite-v1:0, prompt escape-v1, tope de 30
iteraciones, 8 escenarios x 4 configuraciones x 3 repeticiones (96 casos, dos
horas y tres minutos).

| Configuración | Accuracy (IC95%) | pass@k / pass^k | Overhead vs. óptimo | Tokens/resuelto | Latencia p50/p95 (s) |
|---|---:|---:|---:|---:|---:|
| react | 0.792 [0.595, 0.908] | 1.0 / 0.625 | 2.36x | 143.340 | 24.9 / 31.1 |
| gate | 0.667 [0.467, 0.820] | 0.875 / 0.5 | 2.56x | 161.362 | 25.4 / 33.2 |
| react_generico | 0.625 [0.427, 0.788] | 0.875 / 0.375 | 2.80x | 114.328 | 26.2 / 30.5 |
| summarizer | 0.375 [0.212, 0.573] | 0.5 / 0.25 | 1.79x | 481.678 | 98.7 / 217.5 |

El resultado más fuerte de la corrida es pass@k = 1.0 en react "puro" con system prompt especializado: el agente
resuelve los 8 escenarios en al menos uno de los tres intentos pero con pass^k = 0.625 (solo en 5 de 8 lo
logra las tres veces). Esa brecha entre capacidad y confiabilidad es
exactamente lo que las dos métricas existen para separar. Demeustra que el límite de nuestro agente no es
saber resolver: es la consistencia, y eso reorienta el trabajo pendiente
hacia reducir varianza de trayectoria, no hacia ampliar capacidades.

En el otro extremo, el summarizer pierde en todos los ejes a la vez: la
mitad de accuracy que react, 3.4 veces más tokens por caso resuelto y 7
veces peor latencia p95.

### Accuracy por dificultad 

La accuracy cae de forma monótona con la dificultad en las cuatro
configuraciones como podiamos esperar:

| Dificultad | react | gate | react_generico | summarizer |
|---|---:|---:|---:|---:|
| easy | 3/3 | 3/3 | 3/3 | 2/3 |
| medium | 6/6 | 6/6 | 4/6 | 6/6 |
| hard | 4/6 | 3/6 | 4/6 | 1/6 |
| extreme | 6/9 | 4/9 | 4/9 | 0/9 |

Dos cosas que la vista agregada esconde. El summarizer colapsa con la
dificultad: va parejo con el resto en easy/medium y se derrumba a 1/6 y 0/9
cuando el horizonte se alarga, justo donde un resumen de estado debería
ayudar más.  react y react_generico tienen una performance parecida en los escenarios "hard" pero la ventaja del
prompt especializado se demuestra en los escenarios "medium" y "extreme".

### Tokens por caso resuelto:

| Configuración | Tokens/resuelto | vs. react |
|---|---:|---:|
| react_generico | 114.328 | -20% |
| react | 143.340 | — |
| gate | 161.362 | +13% |
| summarizer | 481.678 | +236% |

Comparando todas las configuraciones contra react (aquel que obtuuvo la mayor accuracy), podemos observar que el summarizer cuesta 3.4 veces más por cada caso que resuelve. Si sumamos este resultado a los resultados anteriores, podemos concluir que no es que sea caro y algo mejor, es caro y peor.

### Modos de fallo

Definimos las categorías mirando las trazas reales, no a priori. Un punto a destacar es que la que
dominaba con el modelo local (texto en vez de acción) no se podía anticipar
de antemano, y con nova-lite desaparece prácticamente.

![Modos de fallo por configuración](docs/m3_fallos.png)

Sobre 24 casos por configuración:

| Configuración | success | exhausted_iterations | loop_detected | prosa_en_vez_de_tool | crash |
|---|---:|---:|---:|---:|---:|
| react | 19 | 3 | 2 | 0 | 0 |
| gate | 16 | 7 | 1 | 0 | 0 |
| react_generico | 15 | 7 | 0 | 2 | 0 |
| summarizer | 9 | 3 | 9 | 1 | 2 |

El modo de fallo dominante cambió de naturaleza al cambiar de modelo. Con
qwen2.5:3b era texto en vez de acción: el modelo entendía qué hacer pero lo
describía en vez de emitir la llamada, y eso cerraba el bucle antes de
actuar. Con nova-lite ese modo casi desaparece (0 casos en react). Es un
resultado importante: el motor de tool-use de M1 está bien, solo que el modelo chico no lo acciona de manera correcta. Los
modos que quedan con nova-lite sí hablan del diseño: agotar las iteraciones
sin llegar (un fallo de eficiencia de trayectoria, coherente con el overhead
de 2.4 a 2.8 veces el óptimo) y entrar en loop (repetir la misma llamada con
los mismos argumentos).

Al analizar los modos de fallo, sale a luz un resultado poco intuitivo: El summarizer crea loops, y eso lleva su mal desempeño: 9 de sus 24
casos (37%) terminan en loop, contra 2 de react. La racha máxima de llamadas
idénticas consecutivas lo muestra de manera clara:


| Configuración | racha máxima | casos con racha >= 3 |
|---|---:|---:|
| react_generico | 3 | 1 |
| gate | 12 | 3 |
| react | 15 | 5 |
| summarizer | 23 | 9 |

Veintitrés llamadas idénticas seguidas. Reinyectar un estado resumido en
cada turno puede no anclar al agente sino encerrarlo: si el resumen omite o deforma el
efecto de la última acción, el agente vuelve a intentarla, y el resumen
siguiente (derivado de esa misma interacción) vuelve a omitirla.

![Redundancia: racha máxima de tool-calls repetidas](docs/m3_redundancia.png)

Otro punto a destacar es que priorizar los modos de fallo solo por frecuencia esconde los modos raros pero
caros:

| Modo de fallo | Frecuencia | Latencia media | Costo total |
|---|---:|---:|---:|
| loop_detected | 12 | 125.0 s | 1499.8 s |
| exhausted_iterations | 20 | 40.3 s | 805.4 s |
| crash | 2 | 132.8 s | 265.6 s |
| prosa_en_vez_de_tool | 3 | 40.4 s | 121.1 s |

Si medimos por frecuencia de aparición, agotar iteraciones apreciera el fallo mas importante (20 contra 12) pero, si medimos por costo total, la creacion de loops resutla el modo de fallo mas preocupante, porque cada una de esas ejecuciones resulta mucho mas cara que quedarse sin iteraciones.

### Resultados del juez

Checklist binario de 3 criterios, con nova-pro como juez (distinto del
agente nova-lite y de mayor capacidad):

- Que las trazas muestren un uso razonable de tools, **sin redundancia evitable**
- Que el agente haya realizado una **exploración ordenada** (ej: Que al entrar a un cuarto observe y luego intente agarrar objetos)
- Que el agente haya realizado **acciones apoyadas/sustentadas logicamente** (ej: Que no intente usar un objeto que no agarro todavía)

| Configuración | Casos puntuados | Score (0-3) | ordenada | apoyadas | sin redundancia |
|---|---:|---:|---:|---:|---:|
| gate | 24/24 | 2.38 | 0.88 | 0.88 | 0.62 |
| react | 24/24 | 2.33 | 0.88 | 0.88 | 0.58 |
| react_generico | 24/24 | 2.00 | 0.83 | 0.71 | 0.46 |
| summarizer | 24/24 | 1.46 | 0.71 | 0.54 | 0.21 |

![Calidad de exploración por configuración](docs/m3_judge.png)

El orden del juez coincide con la accuracy salvo en la cabeza: pone gate
(2.38) apenas por encima de react (2.33) aunque react resuelve más casos (0.792
contra 0.667). Esto no resulta una contradicción: el juez puntúa la calidad de la
trayectoria, no si abrió la puerta, y es consistente con lo que hace el
gate: cortar acciones inválidas produce trazas más limpias aunque no
resuelva más. 

A su vez, el veredicto del juez sobre el summarizer fue tajante y resulta congruente con lo analizado anteriormente: 0.21 en trazas "sin
redundancia" contra 0.58-0.62 del resto.

#### Confiabilidad del Juez
Para evaluar la confiabilidad del juez del agente, construimos una referencia determinística basada en código que aproxima tres aspectos observables de las trazas: si el agente mira antes de actuar, la cantidad de errores de herramientas y la presencia de repeticiones. Esta referencia no pretende capturar todos los casos ni toda la complejidad del comportamiento del agente, sino proporcionar una señal objetiva e independiente con la cual contrastar al juez. Esto permite evitar la circularidad de validar un LLM utilizando otro LLM como referencia. Comparamos ambos veredictos mediante Cohen’s kappa por criterio, sobre las 96 trazas de la corrida canónica. La necesidad del juez surge precisamente de las limitaciones de esta referencia determinística: hay aspectos de la calidad y del comportamiento del agente que no pueden reducirse fácilmente a reglas sobre la traza y requieren una evaluación más flexible.

Los primero resultados fueron los siguientes:

| Criterio | acuerdo bruto | kappa | ref dice "sí" | juez dice "sí" |
|---|---:|---:|---:|---:|
| sin_redundancia_evitable | 0.77 | 0.55 | 0.66 | 0.47 |
| exploracion_ordenada | 0.85 | 0.26 | 0.97 | 0.82 |
| acciones_apoyadas | 0.73 | 0.00 | 0.96 | 0.75 |

Dos de los tres criterios no llegan a una zona de acuerdo realmente confiable. La
hipótesis inmediata fue que el problema era una referencia saturada
(diciendo "sí" casi siempre), así que endurecimos la logica de acciones_apoyadas: además
de exigir cero errores de herramienta, ahora exige que todo uso de un objeto
venga después de haberlo tomado con éxito (la misma garantía que el gate
impone por código). Su tasa de "sí" bajó de 0.96 a 0.75: la
referencia pasó a discriminar en mayor medida.

Un punto de lectura que vale para los tres criterios: un kappa bajo no
equivale a que el juez nunca acierte. Cuando una de las dos partes dice "sí"
el 96% de las veces, el acuerdo esperado por azar ya es altísimo y el kappa
lo descuenta hasta anularlo, aunque el acuerdo bruto sea alto. 

Segunda medición, tras realizar cambio en las referencias:

| Criterio | ref dice "sí" | juez dice "sí" | kappa |
|---|---:|---:|---:|
| sin_redundancia_evitable | 0.66 | 0.47 | 0.55 |
| acciones_apoyadas (endurecida) | 0.96 -> 0.75 | 0.75 | 0.00 -> -0.056 |
| exploracion_ordenada | 0.97 | 0.82 | 0.26 |

Con la referencia ya discriminando, el kappa de
acciones_apoyadas siguió en cero. Ambas partes reparten en la misma
proporción (0.75 y 0.75) pero no coinciden en cuáles casos, que es acuerdo
al nivel del azar. 

En base a estOS resultados, entendemos que al confiabilidad de nuestro Juez debe analizarse por criterio, y no de manera
global:

- sin_redundancia_evitable tiene un acuerdo moderado y es utilizable
- acciones_apoyadas tiene una referencia que discrimina y aun así el juez no
coincide (un fallo real del juez en ese criterio)
- exploracion_ordenada todavía tiene una referencia saturada (0.97) y debería continuar ajustandose.

##### Sesgo hacia uno mismo, medido:
Utilizar un modelo mas grande como juez tiene un costo asociado mayor que utilizar el mismo modelo que el agente. Bajo esta premisa, decidimos probar si se obtenían resultados similares con los dos jueces. Corrimos el juez propio
(nova-lite juzgando sus propias trazas) sobre los mismos 96 casos que ya había juzgado nova-pro:

| Configuración | juez ajeno | juez propio | sesgo |
|---|---:|---:|---:|
| gate | 2.38 | 2.62 | +0.25 |
| react | 2.33 | 2.71 | +0.38 |
| react_generico | 2.00 | 2.42 | +0.42 |
| summarizer | 1.46 | 2.04 | +0.58 |
| global | 2.04 | 2.45 | +0.41 |

El modelo se infla 0.41 puntos sobre 3 (+20%) al juzgarse a sí mismo, pero lo
importante es que cuanto peor es la trayectoria, más se auto-premia: el esquema
que peor rinde (summarizer) recibe más del doble de sesgo que el que mejor
rinde (gate). Esto tiene dos consecuencias que un sesgo parejo no tendría:
comprime el poder de discriminar (la brecha entre el mejor y el peor brazo
cae de 0.92 a 0.67), y da vuelta el ranking (con el juez ajeno gana gate,
con el propio gana react). Esto confirma con datos empiricos que
usar un juez distinto del agente no era una precaución solo teórica.

### Comparación entre modelos y proveedores

Como los resultados de accuracy están limitados por el modelo, corrimos el
mismo framework sobre varios modelos para separar los límites del modelo de
los del framework. Corrimos cinco: qwen2.5:3b y llama3.2 en Ollama, y la
familia Nova completa (micro, lite, pro) en Bedrock.

#### La escalera de capacidad.
Entre qwen2.5:3b y nova-lite cambian cuatro variables a la vez (tamaño, cuantización, familia de entrenamiento). La comparacion de estos dos modelos
 demuestra que un limitante de la performance es el modelo en si modelo pero no qué parte del
modelo. La familia Nova permite un contraste limpio: misma familia, misma
API, mismo tratamiento, solo cambia la capacidad. Sobre la configuración
react:

| Modelo | Accuracy | IC95% | Delta |
|---|---:|---|---:|
| qwen2.5:3b (local) | 0.000 | [0.000, 0.138] | — |
| nova-micro | 0.250 | [0.120, 0.449] | +0.250 |
| nova-lite | 0.792 | [0.595, 0.908] | +0.542 |
| nova-pro | 0.625 | [0.427, 0.788] | -0.167 |

![Accuracy por modelo × configuración](docs/m3_cmp_accuracy.png)

La curva de performance sube fuertemente y después deja de subir, un descubrimiento importante ya que nos dice que el cuello de botella no es el modelo. Es importante destacar la salvedad de
que, con estos datos, no afirmamos que nova-pro sea peor que nova-lite: los intervalos se
solapan de lleno y con 24 casos por escalón esa caída de accuracy es compatible con
ruido. Lo afirmarle es que no mejora la performance al comparar nova-lite y nova-pro, y eso contrasta con el escalón
anterior, donde la mejora sí es clara. Un dato que refuerza la lectura:
nova-pro tiene pass@k = 1.0 igual que nova-lite pero pass^k de 0.375 contra
0.625, un modelo más capaz que resuelve lo mismo con más varianza apunta a
que el límite está en la trayectoria, no en el razonamiento.


#### Cómo falla cada modelo.
No es que un modelo falle "más": fallan por razones distintas, y la progresión se lee de menor a mayor capacidad:

| Modelo | Modo dominante (react) | Uso de use/go |
|---|---|---|
| qwen2.5:3b (3.1B) | prosa (no actúa) | ~0 |
| llama3.2 (3.2B) | errores de herramienta (actúa, pero inválido) | usa ambos, con errores |
| llama3.1 (8.0B) | agota iteraciones + algo de prosa | 100 use, 110 go |
| nova-lite | agota iteraciones / loops | 92 use, 109 go |

Los dos modelos de ~3B fallan antes del razonamiento: uno describe la acción
en vez de emitirla, el otro se equivoca de objeto. Esos fallos no dicen nada
sobre el diseño del agente, solo sobre el modelo. llama3.1 (8B) es el punto
de quiebre: ya usa los cinco verbos con la misma intensidad que nova-lite
pero todavía arrastra algo de prosa y se queda sin iteraciones seguido.
Recién con nova-lite la prosa desaparece del todo y quedan solo fallos de
trayectoria, que es exactamente la condición que este informe necesitaba
para poder concluir algo sobre el framework y no sobre el modelo.

#### El orden de las configuraciones según accuracy depende del modelo

La performance de nuestro framework segun sus distintas configuraciones cambia con el tamaño del modelo:

```
nova-micro: gate (0.42) > generico (0.29) > react (0.28) ≈ summarizer (0.25)
nova-lite:  react (0.79) > gate (0.67) > generico (0.62) > summarizer (0.38)
```

Con el modelo débil el gate gana; con el fuerte, react puro gana y el gate
estorba. Este es un resultado esperable dada la naturaleza del gate configurado: su función es
suplir con reglas determinísticas lo que el modelo no sabe hacer solo. Cuando
el modelo es incapaz, esas "barandas" lo salvan; cuando es competente, las
mismas "barandas" no son utilizadas. 

Por último, "barato" no es una virtud si no resolvés. Los modelos locales
gastan un orden de magnitud menos en tokens, pero su accuracy es cero: no
son eficientes, abandonan. El agente que responde en prosa a los tres turnos
cierra el loop temprano y por eso "cuesta poco". De aquí surge el argumento de fondo
para medir tokens por caso resuelto y no tokens por caso: con el
denominador en cero, el numerador chico no significa nada.



## 4. Experimentos y Analisis

Con el fin de analizar como afectan el desempeño general cada parte del framework, realizamos cinco experimentos aislando cada una  una pieza del framework: resumen de
estado, gate, prompt, corte de loop en runtime y tamaño de la ventana de
memoria. Son comparaciones apareadas: mismos escenarios, misma cantidad de repeticiones,
mismo entorno y modelo, cambiando solo el eje bajo estudio. El contraste de
significancia siempre estratifica por escenario (Cochran-Mantel-Haenszel),
por la razón explicada en la sección 2: agrupar todo mete la varianza entre
escenarios en el error estándar y puede tapar un efecto real.

### Resumen de estado (react vs. summarizer)

**Hipótesis:** el resumen ayuda solo cuando el contexto crudo no entra en la
ventana (por ejemplo en extreme-archive, diseñado para no caber en 16K
tokens) y perjudica cuando entra, porque agrega costo y puede corromper cuando el estado
exacto importa.

![Latencia p50/p95 por configuración](docs/m3_latencia.png)

Resultado: el resumen perjudica, con significancia estadística.

| | react | summarizer |
|---|---:|---:|
| Accuracy | 19/24 = 0.792 | 9/24 = 0.375 |
| loop_detected | 2 | 9 |
| Racha máx. de llamadas repetidas | 15 | 23 |
| Tokens por resuelto | 143.340 | 481.678 |
| Latencia p95 | 31.1 s | 217.5 s |
| Juez ("sin redundancia") | 0.58 | 0.21 |

Contraste estratificado: p = 0.0015 (el agrupado da p = 0.0034, ambos
coinciden, así que acá la conclusión no depende del método). La hipótesis
original se refuta. Esperábamos que el resumen ayudara
donde el contexto crudo no entra, y es exactamente donde peor le va (0/9 en
extreme contra 6/9 de react). El resumen no es caro-pero-útil en los casos de gran contexto, es caro y ofrece peores resultados.

Reinyectar un estado resumido en cada turno puede generar loops si el resumen omite el efecto de la última
acción, causando que el agente la repita, y el resumen siguiente (derivado de esa misma
interacción) vuelva a omitirlo.

### Gate determinístico (react vs. gate)

**Hipótesis:** El uso de un gate deterministico sobre el uso de herramientas deberia mejorar la performance ya que ningún prompt garantiza con certeza evitar el uso inválido de herramientas, pero un chequeo de código sí. 

Resultado: el efecto del gate depende según la capacidad del modelo.

| Modelo | react | gate | Delta | p (estratificado) |
|---|---:|---:|---:|---:|
| nova-micro (débil) | 0.281 | 0.422 | +0.141 | 0.0338 |
| nova-lite (fuerte) | 0.792 | 0.667 | -0.125 | 0.4219 |

Con el modelo débil el gate ayuda de forma significativa; con el fuerte no
ayuda (la baja de accuracy no es significativa). Es justo lo que la teoría del gate predice: suple con reglas determinísticas
lo que un modelo no sabe/puede hacer solo.

Con el fin de entender como mejora la performance en modelos mas chicos, analizamos el efecto por escenario. Descubrimos que el mismo no es parejo y está concentrado en un escenario:

| Escenario | react | gate | Delta |
|---|---:|---:|---:|
| extreme-archive | 1/8 | 7/8 | +0.750 |
| apartment-keys | 6/8 | 8/8 | +0.250 |
| study-with-key | 6/8 | 8/8 | +0.250 |
| color-locks | 1/8 | 0/8 | -0.125 |
| library-search | 1/8 | 0/8 | -0.125 |

Extreme-archive tiene 20 expedientes con prosa burocrática: el modelo débil se pierde entre
identificadores parecidos y el gate le bloquea los inválidos antes de gastarlos. Entendemos entonces que el gate entrega valor donde el prompt no puede, dependiendo de con qué
modelo corras: es una base de garantías "gratis" que paga cuando el modelo es
propenso a acciones inválidas, y se vuelve neutro cuando no lo es. No es una
mejora incondicional del framework, es un seguro cuyo valor cae a
medida que sube la capacidad del modelo.

```Nota metodológica: el contraste agrupado en nova-micro daba p = 0.0957, no concluyente; estratificado por escenario da p = 0.0338, con exactamente los mismos 128 casos. Dos escenarios daban 0/8 en ambos brazos y no aportaban señal, pero inflaban el denominador del test agrupado.```

### Prompt especializado vs. genérico

Hipótesis: el prompt de sala de escape está lleno de reglas o estrategias de como usar herramientas de la sala de escape, por lo que debería mejorar la accuracy. Además, tiene notas para evitar enunciar el usos de tools en vez de hacer el llamado, así que debería reducir ese modo de fallo (dominante con modelos débiles).

Resultado: el prompt especializado sí se traduce en accuracy.

| | react (escape-v1) | react_generico |
|---|---:|---:|
| Accuracy | 19/24 = 0.792 | 15/24 = 0.625 |
| prosa_en_vez_de_tool | 0 | 2 |
| exhausted_iterations | 3 | 7 |
| Llamadas de media | 21.38 | 21.42 |

El delta en accuracy es +0.167 pero no alcanza significancia (p = 0.277 estratificado):
con 24 casos por framework, un efecto de ese tamaño queda dentro del ruido.

Lo que sí es limpio es el cambio en el perfil de fallo: la hipótesis de que el prompt
especializado reduce la prosa se cumple (0 casos contra 2). Ademas, aparece algo
que no habíamos previsto: el prompt genérico se queda sin iteraciones más del doble
de veces gastando la misma cantidad de llamadas a herramientas. No actúa menos, sino que lo hace peor dirigido, y se le acaba el presupuesto sin lograr escapar. Analizandolo desde la otra cara de la misma moneda, podriamos decir que el prompt especializado compra eficiencia de trayectoria: ambas cponfiguraciones llaman herramientas con la misma intensidad pero el especializado logra escapar más seguido porque las ordena de mejor manera.

### Corte de loop en runtime

La señal de loop es la repetición de la misma llamada con los mismos argumentos de manera consecutiva. Nuestro sistema de evaluación ya la medía después de correr pero no se enviaban señales al agente en runtime. Agregamos que, a la tercera llamada idéntica consecutiva, en vez de reejecutar la herramienta se le devuelve al modelo una observación
("ya la llamaste N veces con estos argumentos y el resultado no cambió, probá otra cosa"). De esta manera, no se cortaría la ejecución del agente al entrar en un loop pero se le informaria de su comportamiento con la esperanza de que cambie.

Hipótesis: como el loop es el modo de fallo más caro, cortarlo debería convertir parte de esos casos en éxitos o al menos liberar iteraciones.

| | react | loop_breaker |
|---|---:|---:|
| Accuracy | 0.792 | 0.708 |
| Racha máxima de llamadas repetidas | 15 | 3 |
| pass@k / pass^k | 1.0 / 0.625 | 0.875 / 0.625 |
| Intervenciones del corte | — | 1 en 24 casos |

El mecanismo funciona y el efecto esperado no aparece: la racha máxima cae
de 15 a 3, pero la accuracy no mejora (diferencias no significativas). El dato
revelador es que el corte intervino una sola vez en 24 casos: al cortar
temprano, el modelo cambia de estrategia y ya no llega a rachas largas.

Eliminar los loops no se tradujo en un aumento de éxitos, lo que significa que en esos casos el agente no estaba "trabado y a
punto de resolver": estaba perdido, y repetir era una forma de estarlo entre otras.

### Ventana de memoria (50 vs. 120 mensajes)

Hipótesis: si la ventana está descartando turnos que el agente necesita,
ampliarla debería mejorar los escenarios de gran contexto.

| | ventana 50 | ventana 120 |
|---|---:|---:|
| Accuracy | 0.792 | 0.708 |
| pass^k | 0.625 | 0.500 |
| Llamadas de media | 21.4 | 21.4 |
| Tokens de input | 2.693.635 | 2.744.204 (+2%) |

Rsultados no significativos. Seis de los ocho escenarios dan
exactamente el mismo resultado. Habíamos estimado que cerca de la mitad de
los casos desbordaba la ventana de 50; si eso fuera cierto, pasar a 120
habría aumentado el accuracy. No lo hizo, y las llamadas
quedaron idénticas: la ventana casi no estaba recortando nada. La memoria
de trabajo queda descartada como cuello de botella en este dataset. Junto
con el corte de loop, dos de las tres explicaciones candidatas para la
brecha de consistencia (redundancia y pérdida de contexto) quedan desestimadas.

## 5. Limitaciones y próximos pasos

La limitación que más pesa es la varianza entre corridas: dos corridas
idénticas del mismo brazo y modelo dieron 0.250 y 0.125 (diferencia no
significativa), del mismo orden que los efectos que medimos. Por eso cuatro
de los cinco experimentos no alcanzan significancia sobre nova-lite. El
remedio sería fijar la semilla de muestreo, pero Bedrock no lo permite (lo
verificamos); solo está disponible para Ollama.

El confound de cuantización quedó acotado, no eliminado: con familia y
cuantización fijas, pasar de 3.2B a 8B rompe el cero, así que el cero de los
modelos chicos no era solo degradación por correr en 4 bits. Sigue sin poder
atribuirse la brecha entre el 8B local (0.125) y nova-lite (0.792), donde
cambian familia, entrenamiento y API a la vez.

Sobre el juez: con nova-pro (distinto del agente, sobre 96 trazas con
variación real) dos de los tres criterios no llegan a una zona de acuerdo
confiable; solo sin_redundancia_evitable, donde la referencia reparte bien,
da un acuerdo moderado.

Sin prompt caching, más de un tercio del input de una corrida se gasta
repitiendo el mismo system prompt en cada llamada. No lo implementamos
porque el cliente de Bedrock es un archivo fijo del andamiaje que no expone
esa opción, y afecta por igual a todas las configuraciones.

Y dos menores: el split entre desarrollo y holdout quedó desbalanceado
porque la etiqueta "extreme" agrupa escenarios muy distintos entre sí, y el
tope de 30 iteraciones es una decisión nuestra del harness, no del
enunciado, para que no le ponga un techo artificial a la accuracy.

El próximo paso es atacar la consistencia, no la capacidad: el agente ya
resuelve los 8 escenarios en algún intento pero solo 5 de 8 en los tres, y
subir de modelo ya no mueve la aguja. Ya sabemos por dónde no pasa la
solución: ni cortar loops en runtime ni ampliar la ventana de memoria
mueven la accuracy, así que lo que queda es la calidad de la decisión en
cada paso: rediseñar el summarizer para que el estado incluya qué se
intentó y con qué resultado (no solo el estado alcanzado), resolver el
criterio del juez que no acuerda aunque su referencia ya discrimine, probar
un gate adaptativo que se prenda solo donde el espacio de identificadores es
grande y ambiguo, sumar un planificador explícito para el escenario de
objetivo compuesto, y eventualmente memoria episódica o semántica más allá
de la ventana de trabajo actual.
