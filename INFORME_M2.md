# Informe M2: memoria, prompting y robustez

Segundo de tres informes sobre el mismo agente. M1 fue el agente y sus
herramientas, este es memoria y robustez, y M3 es la evaluación en la sala de
escape.

## Resumen de la entrega

M2 amplía el agente de M1 para que aguante conversaciones largas, salidas mal
formadas del modelo y fallos transitorios, sin cambiar la interfaz externa.
Elegimos estas tres cosas porque son justo lo que la sala de escape de M3 va
a necesitar: un mundo con estado donde hay que recordar el mapa, modelos
chicos que a veces devuelven texto en vez de llamar a una herramienta, y
partidas largas de muchos pasos.

Toda la lógica nueva vive en el agente y en las herramientas; el cliente LLM
no lo tocamos, como pide la consigna para poder seguir corriendo los tests
con el mock. Agregamos: estado entre llamadas a run, una ventana de memoria
por recencia, salida estructurada con reparación, reintentos con backoff
exponencial ante fallos transitorios, errores accionables en la calculadora y
el lector de archivos, y conteo acumulado de tokens.

Al momento de entregar M2, toda la suite local pasaba: 98 tests en verde
(sin contar M3, que todavía no estaba en el repo). Hoy, con M3 ya integrado,
son 249. De los 98 originales, 21 son de M2 (7 de conformidad y 14 propios);
si sacamos los 33 que solo validan el cliente de Ollama y Bedrock, quedan 65
tests de código propio de M1+M2.

## Estado entre llamadas

El agente guarda el historial una sola vez, en el constructor. Cada llamada a
run agrega el mensaje del usuario, corre el bucle de siempre, y al final
agrega la respuesta del asistente. Como el historial no se reinicia,
llamadas sucesivas continúan la misma conversación. El turno final se guarda
sin llamadas a herramientas pendientes, para no dejar una llamada sin su
respuesta colgada en el historial si el bucle cortó por el tope de
iteraciones.

## Memoria: ventana por recencia

![Sliding window por recencia](docs/memoria_m2.png)

En cada llamada al LLM se arma una copia recortada del historial. Si entra
entero en el presupuesto, se manda entero; si no, se conserva el primer turno
completo (el objetivo original con su respuesta) más los turnos más
recientes, descartando los del medio. La función tiene que devolver una
lista nueva, nunca el historial original: en una versión anterior
recortábamos la lista interna y la pasábamos por referencia, y como el mock
guarda esa referencia, después parecía que el historial seguía creciendo más
allá del límite porque se veía el estado final y no el de cada llamada.

Garantizamos tres cosas siempre. El último mensaje del usuario viaja siempre
al LLM, aunque haya que forzarlo al principio de la ventana cuando el turno
actual ocupa todo el presupuesto. El primer turno completo (objetivo más
respuesta) también se conserva, no solo el mensaje suelto, para no dejar dos
mensajes de usuario seguidos ni una llamada a herramienta sin su respuesta, y
para respetar la alternancia de roles que exige Bedrock; si hiciera falta
elegir, cede el primer turno antes que sacrificar el último mensaje del
usuario. Y la ventana siempre empieza en un mensaje de usuario, descartando
cualquier mensaje de herramienta o asistente que quede colgado al principio.

Elegimos recencia más preservar el objetivo inicial porque en una
conversación lo más útil suele estar en los últimos turnos, pero conviene no
perder de vista para qué arrancó todo; los turnos del medio son los que
menos aportan y los primeros que sacrificamos. No es solo una cuestión de
costo: hay evidencia de que meter más contexto no mejora la respuesta, la
atención del modelo se degrada con textos largos, sobre todo en el medio.
Asumimos algunos costos a propósito: no resumimos lo que se descarta, así que
información muy vieja se pierde del todo; el estado vive en memoria del
proceso, sin persistencia entre corridas; y anclar siempre el primer turno
asume que el objetivo no cambia durante la conversación, razonable para un
agente con una meta fija pero no si la conversación cambiara de tema a mitad
de camino.

Cuatro problemas concretos surgieron al implementar esto: el de copia contra
referencia ya descripto; que con un turno muy largo la cola recortada podía
quedar sin ningún mensaje de usuario (lo forzamos); que recortar sin cuidado
podía dejar una ventana que empezaba con un mensaje de herramienta sin su
llamada, algo que Bedrock rechaza (ahora descartamos del frente hasta llegar
a un usuario); y que si el bucle cortaba con una llamada pendiente, quedaba
huérfana en el historial (ahora el turno final se guarda sin llamadas
pendientes).

**Extensión hecha después, para M3.** Esta parte se agregó tras entregar M2.
La estrategia de arriba desliza sobre turnos, marcados por los mensajes de
usuario, lo cual funciona mientras el agente sea conversacional. Pero en M3
el agente resuelve todo el escenario en un solo run: hay un único mensaje de
usuario y después solo bloques de acción, así que "conservar el primer turno
completo" se comía todo el historial y la ventana colapsaba al objetivo
pelado con presupuestos chicos, perdiendo toda la exploración hecha (con los
defaults de eval, 50 mensajes y 30 iteraciones, el colapso ocurría en la
llamada 26, justo en los escenarios que más tool-calls necesitan). Agregamos
una rama para este caso: cuando hay un único mensaje de usuario, la ventana
desliza sobre bloques de acción (un mensaje del asistente junto con las
respuestas a sus llamadas) en vez de turnos, conservando el objetivo como
ancla. Las garantías de antes se mantienen, y el camino multiturno de M1 y M2
no cambió; la rama nueva está cubierta por test_m3_ventana.py.

## Salida estructurada

Agregamos un método aparte para obligar al LLM a responder con un objeto que
valide contra un schema. Es un método aparte y no un paso más del bucle
normal porque tiene otra condición de corte (una llamada a una herramienta
sintética cuyos argumentos validan contra el schema), su propio ciclo de
reparación acotado por una cantidad máxima de intentos, y porque solo ofrece
esa herramienta sintética (no las reales) trabajando sobre un historial
propio, sin tocar la conversación del agente. Lo que sí comparte con el
bucle normal es la capa de reintentos.

![Flujo de reparación de la salida estructurada](docs/structured_call_m2.png)

Contemplamos tres formas en que esto puede fallar, cada una con su reintento:
texto libre sin llamar a ninguna herramienta (se le recuerda cuál usar),
llamar a otra herramienta (se le pide la correcta), o argumentos que no
validan contra el schema (se le devuelve el error concreto para corregir). Si
se agotan los intentos sin éxito, se levanta una excepción; nunca se
devuelve un resultado vacío ni una instancia a medio construir.

## Resiliencia ante fallos transitorios

![Reintentos ante fallos transitorios](docs/resiliencia_m2.png)

Una función decide qué errores conviene reintentar: los de timeout y
conexión por tipo, y cualquier otro que en su nombre o mensaje mencione
palabras como timeout, throttling, rate limit, o códigos 429/5xx. Cualquier
otro error (un bug de programación, argumentos inválidos) sube limpio, sin
reintentarse. El mecanismo reintenta hasta un máximo configurable con backoff
exponencial, y lo usamos tanto en las llamadas al LLM como en la ejecución de
herramientas, por si alguna hace una llamada de red.

Elegimos clasificar por tipo y por texto del error, en vez de por los códigos
específicos de cada proveedor, porque así la misma lógica sirve para el mock,
Ollama y Bedrock sin acoplar el agente a ningún SDK; el costo es que un
proveedor con mensajes poco comunes podría no reintentarse cuando debería.
Probamos esto con tests que simulan cada tipo de fallo: timeout, rate limit,
error no transitorio, reintentos agotados, y una herramienta con fallo
transitorio.

## Errores recuperables en las herramientas

La idea acá no es solo evitar que la herramienta rompa, sino distinguir los
errores que el LLM puede corregir y devolverle un mensaje que le sirva para
eso: un error vuelve como un mensaje más de la conversación, y un mensaje
que explica qué falló y cómo debería verse una entrada válida habilita esa
corrección, mientras que un simple "Error" no.

En la calculadora, un operando no numérico indica qué parámetro falló y qué
se esperaba (si llega un string numérico como "42" directamente lo
convierte), un operador no soportado lista los que sí están, y una división o
módulo por cero explica la restricción y sugiere reintentar con otro valor.
En un test concreto, el LLM llama con el segundo operando en cero, recibe el
error, y en el siguiente turno lo corrige.

En el lector de archivos, todas las rutas son relativas a un directorio raíz
(un sandbox): una ruta vacía o absoluta, o con "..", se explica y se rechaza,
igual que un intento de escape vía symlink; si el archivo no existe pero el
directorio sí, se listan los archivos disponibles; si la ruta es un
directorio, se lista su contenido. Se sigue validando el tamaño máximo y que
sea texto UTF-8, como en M1. En un caso concreto, el LLM pide un archivo que
no existe, recibe la lista de disponibles, y reintenta con el nombre
correcto.

## Conteo de tokens

Sumamos los tokens de entrada y salida de cada respuesta a lo largo de un
run. Quedan en None hasta que algún proveedor los reporta, y a partir de ahí
se acumulan. Separar entrada de salida sirve para estimar el costo real: los
proveedores cobran distinto por cada uno, y la salida suele ser bastante más
cara.

## Cómo probamos

Los 7 tests de conformidad verifican el contrato mínimo pedido por la
cátedra. Los 14 propios cubren resiliencia, recencia, conversaciones largas,
reparación de salida estructurada, y los errores accionables de ambas
herramientas, incluida una recuperación de punta a punta a través del
agente. Todos corren con el mock, sin credenciales.

Contando la suite al momento de entregar M2 (sin M3, que integró después):
5 de conformidad de M1, 7 de M2, 26 de herramientas, 5 escenarios propios de
M1, 14 propios de M2 y 8 de schema de herramientas, 65 en total de código
propio. Sumando los 33 tests de proveedores (que validan el cliente fijo, no
código nuestro), el total era 98. Hoy, con los tests que sumó M3, la suite
completa corre en 249.

## Qué está dentro y qué está fuera de alcance

Ordenamos las defensas según dónde nace cada falla: una salida mal formada
nace en el LLM (salida estructurada más reparación); una herramienta que
falla nace en el mundo externo (reintentos más errores accionables); un
contexto que crece nace en el historial con el tiempo (ventana de memoria más
conteo de tokens).

Fuera de alcance, por decisión: no resumimos el contexto descartado, solo lo
tiramos; no hay persistencia del estado entre procesos; la salida
estructurada no usa el historial de la conversación; los reintentos duermen
de forma bloqueante; no hay prompt caching (la ventana cambia el principio
del historial en cada llamada, lo cual va en contra del cache de prefijo de
los proveedores; M3 terminó midiendo el costo real de esto, sin caching un
tercio del input de una corrida se gasta repitiendo el mismo system prompt);
el presupuesto se mide en mensajes, no en tokens, así que un solo
mensaje enorme podría igual exceder el contexto real; y asumimos que las
herramientas son seguras de reintentar, lo cual vale para las tres que
tenemos (de solo lectura o cómputo puro) pero no para una con efectos
secundarios.

## Del enunciado a la implementación

| Pide el enunciado | Dónde está | Test |
|---|---|---|
| Estado entre llamadas a run | historial persiste en el agente | test_agent_is_stateful_across_runs |
| El historial nunca supera el tope | ventana de memoria | test_bounded_history_growth |
| El último mensaje de usuario siempre presente | inclusión forzada en la ventana | test_ultimo_mensaje_de_usuario_siempre_presente |
| Se preserva el primer turno completo | turnos completos en la ventana | test_primer_turno_goal_se_conserva |
| Conversaciones largas sin romperse | ventana con sus invariantes | test_conversacion_larga_sigue_respondiendo |
| Salida estructurada ofrece la herramienta correcta | se pasa una sola tool en cada llamada | test_structured_call_offers_final_result_tool |
| Validación y reparación de salida estructurada | los tres casos de fallo | test_structured_output_repairs_schema_validation_error, test_prompt_roto_dispara_reparacion_y_se_recupera |
| Fallo limpio al agotar reintentos | excepción explícita | test_structured_output_max_retries |
| Errores recuperables en la calculadora | calculator.py | test_calculadora_* |
| Errores recuperables en el lector | file_reader.py | test_lector_escape_del_sandbox_via_subdirectorio |
| Fallo transitorio reintentado con éxito | mecanismo de reintentos | test_timeout_del_llm_se_reintenta_y_termina_bien |
| Tokens acumulados según el contrato | conteo de tokens | test_token_accounting* |
| Informe con las secciones pedidas | este documento | — |