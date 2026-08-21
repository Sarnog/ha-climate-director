# Climate Director — Guía de instalación (Español)

[![Invítame a un café en Ko-fi](https://img.shields.io/badge/Ko--fi-Invítame%20a%20un%20café-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Patrocinar en GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

Esta guía explica paso a paso cómo instalar y configurar Climate Director.
Sigue los pasos de arriba abajo; cada paso se apoya en el anterior.

## Contenido

- [Qué es Climate Director](#qué-es-climate-director)
- [Qué necesitas](#qué-necesitas)
- [Paso 1 — Instalar](#paso-1--instalar)
- [Paso 2 — Añadir la integración](#paso-2--añadir-la-integración)
- [El menú principal](#el-menú-principal)
- [Paso 3 — Ajustes generales](#paso-3--ajustes-generales)
- [Paso 4 — Zonas](#paso-4--zonas)
- [Paso 5 — Fuentes](#paso-5--fuentes)
- [Paso 6 — Circuitos de aire acondicionado](#paso-6--circuitos-de-aire-acondicionado)
- [Paso 7 — Fuentes de calor compartidas](#paso-7--fuentes-de-calor-compartidas)
- [Paso 8 — Grupos exclusivos](#paso-8--grupos-exclusivos)
- [Paso 9 — Ventanas silenciosas](#paso-9--ventanas-silenciosas)
- [Paso 10 — Residentes](#paso-10--residentes)
- [Paso 11 — Puertas y ventanas](#paso-11--puertas-y-ventanas)
- [Paso 12 — Guardar y cerrar](#paso-12--guardar-y-cerrar)
- [Qué obtienes en Home Assistant](#qué-obtienes-en-home-assistant)
- [Los interruptores y botones](#los-interruptores-y-botones)
- [Acciones](#acciones)
- [Preacondicionamiento](#preacondicionamiento)
- [Tomar el mando](#tomar-el-mando)
- [Evaluar una prueba en modo sombra](#evaluar-una-prueba-en-modo-sombra)
- [Blueprints y notificaciones](#blueprints-y-notificaciones)
- [Resolver problemas](#resolver-problemas)
- [Idiomas](#idiomas)

## Qué es Climate Director

Climate Director es una integración de Home Assistant que gobierna aparatos de
climatización existentes. No posee hardware propio: dirige las entidades
`climate` que ya tienes — una caldera de gas, una bomba de calor, aires
acondicionados. En cada momento calcula un estado final coherente para toda la
casa y lo convierte en llamadas de servicio.

**El modo sombra está activado por defecto.** La integración calcula entonces
cada decisión y muestra lo que habría hecho, pero no gobierna nada. Así puedes
dejarla funcionar durante semanas junto a tus automatizaciones existentes y
cambiar solo cuando confíes en ella.

Tres conceptos forman la base:

| Concepto | Significado |
|---|---|
| **Zona** | Una habitación. Describe *lo que quieres*: temperatura objetivo, cuándo puede empezar a calentar o enfriar y en qué estación. |
| **Fuente** | Un aparato capaz de servir a una zona, con una función (calentar, enfriar o ambas), un orden de preferencia y una ventana de temperatura exterior. |
| **Circuito de aire acondicionado** | Una unidad exterior y las unidades interiores que cuelgan de ella. Describe *qué es técnicamente posible a la vez*. |

La regla de oro para una unidad exterior compartida: todas las unidades
interiores de un circuito llevan la misma función — calentar, enfriar, apagado
o solo ventilar. Dos unidades interiores en una misma unidad exterior no pueden
tener una calentando mientras la otra enfría. Climate Director sabe qué
unidades van juntas y resuelve ese conflicto por ti.

## Qué necesitas

| Entidad | Obligatoria | Para qué |
|---|---|---|
| Una `climate.*` por zona | **sí** | sin aparato no hay nada que gobernar |
| Un sensor de temperatura por zona | **sí** | sin medición, la integración no distingue demasiado frío de demasiado calor; una `climate.*` con `current_temperature` sirve |
| `sensor.*` o `weather.*` temperatura exterior | no | solo para poner límites por temperatura exterior — gas por debajo de 3 °C, bomba de calor por encima, por ejemplo |
| `weather.*` o `sensor.*` precipitación | no | solo si las precipitaciones pueden levantar el límite de «abrir una ventana» |
| `person.*` o `device_tracker.*` por residente | sí, en cuanto configures residentes | si no, ese residente nunca puede estar en casa |
| Un sensor de sueño por residente | no | sin él, nadie cuenta nunca como dormido |
| `binary_sensor.*` presencia por zona | solo si una zona funciona por *la habitación en sí* | entonces es la única puerta de la zona |
| `binary_sensor.*` puerta o ventana | no | suspende las zonas vinculadas mientras está abierto |
| `calendar.*` | no | activa el horario de vacaciones por sí solo; solo funciona con una palabra clave |
| Una entidad de estación | no | solo si no quieres deducir la estación del mes |

No necesitas crear ningún helper. La integración fabrica ella misma todos sus
interruptores y controles.

## Paso 1 — Instalar

**Versión mínima:** Home Assistant **2025.3** o más reciente. La integración
añade sus entidades mediante una API disponible desde 2025.3.

**Mediante HACS** (recomendado):

1. Abre HACS.
2. Ve a los tres puntos de arriba a la derecha y elige **Repositorios
   personalizados**.
3. Añade esta URL, con la categoría **Integración**:

   ```
   https://github.com/Sarnog/ha-climate-director
   ```

4. Busca **Climate Director** en HACS, instálalo y reinicia Home Assistant.

**Manualmente:**

1. Descarga o clona este repositorio.
2. Copia la carpeta `custom_components/climate_director` a la carpeta
   `custom_components` de tu configuración de Home Assistant.
3. Reinicia Home Assistant.

## Paso 2 — Añadir la integración

1. Ve a **Ajustes → Dispositivos y servicios → Añadir integración**.
2. Busca **Climate Director** y elígelo.
3. Dale un **nombre** a la instalación. Ese nombre se convierte en el título y
   precede al nombre de cada entidad que crea la integración.
4. Deja el **Modo sombra** activado. Así primero observas antes de que se
   gobierne nada de verdad.
5. Guarda. La instalación aparece en la pestaña **Integraciones**.

Todo lo demás se construye en **Configurar** de esa integración.

## El menú principal

En **Configurar** encuentras el menú principal, en este orden:

| Menú | Para qué |
|---|---|
| **Ajustes generales** | temperatura exterior, estación, puertas, ventanas, calendarios, modo sombra |
| **Zonas y fuentes** | por habitación: temperatura, puntos de arranque y parada, y los aparatos correspondientes |
| **Circuitos de aire acondicionado** | qué unidades interiores comparten una unidad exterior |
| **Fuentes de calor compartidas** | una caldera o bomba de calor de la que tiran varias habitaciones |
| **Grupos exclusivos** | aparatos que nunca deben funcionar a la vez |
| **Ventanas silenciosas** | horas en las que el director no inicia nada por su cuenta |
| **Residentes** | quién está en casa, quién duerme y el horario de cada uno |
| **Puertas y ventanas** | qué aperturas silencian qué zonas |
| **✅ Guardar y cerrar** | solo aquí se guarda todo de verdad |

Dos cosas hacen el menú agradable:

- Cada pantalla termina con **Cuando hayas terminado aquí**, con la opción
  *Conservar estos cambios y volver* o *Descartar y volver*.
- Cada lista lleva una fila **← Volver al menú principal**.

Así que nada te atrapa. Volver atrás siempre funciona, incluso con una pantalla
a medio rellenar — lo que escribiste se pierde entonces. Y **nada** se guarda
hasta que eliges **Guardar y cerrar** en el menú principal.

## Paso 3 — Ajustes generales

| Ajuste | Qué hace |
|---|---|
| **Sensor de temperatura exterior** | alimenta cada límite exterior. Sin sensor, todo límite cuenta como no alcanzado y la instalación se queda quieta |
| **Sistema de calefacción** | *Central* o *Por zona*, ver abajo |
| **Fuente de la estación** | de dónde sale la estación: el mes, una entidad, o fijada verano/invierno |
| **Entidad de estación** | solo si la fuente está en *entidad*; la entidad integrada `season.*` también se puede elegir |
| **Hemisferio** | qué meses cuentan como verano cuando la estación sale del mes: norte abril–septiembre, sur octubre–marzo |
| **Elección de estación** | la entidad `select.*` *Estación* fija la estación a mano en Automático, Verano o Invierno; la elección sobrevive a un reinicio |
| **Alguien en casa debe estar despierto** | activado = la casa espera a alguien en casa *y* despierto; desactivado = dormir no cuenta |
| **El horario de un residente debe estar abierto** | activado = la casa espera la primera ventana de horario; desactivado = solo la presencia decide |
| **Calendarios de vacaciones** | qué calendarios pueden anunciar vacaciones; se permiten varios |
| **Palabra que marca vacaciones** | la palabra clave que debe llevar un evento; vacío = se ignoran los calendarios |
| **Preacondicionamiento de / hasta** | la ventana en la que cuenta una petición; por defecto 06:00–23:00 |
| **Duración del preacondicionamiento** | el tope de una sola petición; por defecto 120 minutos |
| **Modo invitados de / hasta** | la ventana en la que se aplica el modo invitados; ambos vacíos = todo el día |
| **Avisar de zona atascada tras** | tras cuántos minutos de espera una zona cuenta como atascada; 0 apaga el sensor |
| **Fuente de precipitaciones** | una entidad `weather.*` o `sensor.*` que dice si hay precipitaciones; vacío = la regla de precipitaciones no participa |
| **Estados que cuentan como precipitación** | qué estados de esa entidad significan precipitaciones; lluvia, nieve y granizo por defecto |
| **Cuánto tiempo siguen contando las precipitaciones (minutos)** | margen tras cesar las precipitaciones; 15 minutos por defecto |
| **Modo sombra** | activado = calcularlo todo, no gobernar nada |

### Las precipitaciones dejan de lado el límite exterior

El límite exterior por zona es una regla de ahorro con una suposición debajo:
si fuera hace mejor tiempo que dentro, te conviene abrir una ventana antes que
encender el aire acondicionado. Cuando hay precipitaciones, esa ventana se
queda cerrada, así que no pasa nada, mientras la habitación sigue demasiado
caliente o fría.

Configura por eso una **fuente de precipitaciones**. Mientras informe de
precipitaciones, Climate Director omite el **límite exterior por zona** —
exactamente
como hace una petición de preacondicionamiento. La banda muerta, la estación y
el límite exterior **por fuente** siguen aplicándose; son ellos los que eligen
el aparato. El margen hace que un chaparrón de cinco minutos no haga oscilar la
regulación. Sin fuente, la regla de precipitaciones no participa.

Una habitación sin ventanas no gana nada con ello. Ahí, activa en la zona **Las
precipitaciones no levantan la regla de «abrir una ventana»**, y el límite
exterior sigue aplicándose incluso con precipitaciones.

### Sistema de calefacción: central o por zona

| Opción | Qué significa | Cómo se rellena |
|---|---|---|
| **Central** | Una fuente de calor para toda la casa. Encender para una habitación calienta el resto con ella. Piensa en un único termostato inteligente, con o sin válvulas de radiador. | Pon el **mismo** termostato como fuente en cada zona |
| **Por zona** | Cada parte de la casa puede recibir su calor por separado, mediante una válvula de zona o una fuente propia. | Da a cada zona su **propia** válvula o aparato como fuente; si hay una caldera compartida, añádela como fuente de calor compartida |

Las válvulas de radiador inteligentes por sí solas no son zonificación: la casa
sigue teniendo un circuito y una fuente de calor que se enciende o apaga para
todos a la vez. Elige entonces **Central**. Una caldera con tres válvulas de
zona es, en cambio, **Por zona**.

Este ajuste no cambia nada sobre quién puede funcionar. Registra lo que es tu
instalación, para que la comprobación de configuración pueda avisarte si tu
montaje no encaja.

## Paso 4 — Zonas

Una zona es una habitación. Por zona configuras:

| Ajuste | Qué hace |
|---|---|
| **Nombre** | la etiqueta que aparece en todas partes |
| **Sensor de temperatura interior** | sobre qué calcula la banda muerta; una `climate.*` que mida por sí misma sirve |
| **Precedencia en una unidad exterior compartida** | con qué fuerza reclama esta zona una unidad exterior compartida; **el más bajo gana**. En un circuito no puede repetirse ningún número |
| **Qué decide si esta zona funciona** | *el hogar* (horario, sueño, alguien en casa) o *la habitación en sí* (solo el sensor de presencia) |
| **Sensor de presencia + estado + margen** | cuándo la habitación cuenta como ocupada; el margen absorbe detectores parpadeantes |
| **Las precipitaciones no levantan la regla de «abrir una ventana»** | actívalo en una habitación sin ventanas; ahí el límite exterior sigue aplicándose incluso con precipitaciones |
| **Esta zona puede calentar** | desactivado = esta habitación nunca se calienta |
| **Temperatura objetivo calefacción** | la consigna que recibe el aparato cuando calienta — no el punto de arranque |
| **Empezar a calentar a** | la calefacción arranca a esta temperatura interior o por debajo |
| **Banda muerta calefacción** | cuánto por encima del punto de arranque se detiene la calefacción |
| **Calentar solo por debajo de esta temperatura exterior** | por encima, la calefacción sigue apagada; vacío = sin límite |
| **Esta zona puede enfriar** | desactivado = esta habitación nunca se enfría |
| **Temperatura objetivo refrigeración** | la consigna que recibe el aparato cuando enfría |
| **Empezar a enfriar a** | la refrigeración arranca a esta temperatura interior o por encima |
| **Banda muerta refrigeración** | cuánto por debajo del punto de arranque se detiene la refrigeración |
| **Enfriar solo por encima de esta temperatura exterior** | por debajo, la refrigeración sigue apagada; vacío = sin límite |
| **Enfriar solo en verano** | liga la refrigeración a la estación de los ajustes generales |

### Cómo funciona la banda muerta

Encender y apagar ocurren a dos temperaturas distintas, para que un aparato no
titile con una décima de grado:

- calentar arranca con `interior ≤ punto de arranque` y para con `interior ≥ punto de arranque + banda`;
- enfriar arranca con `interior ≥ punto de arranque` y para con `interior ≤ punto de arranque − banda`.

El punto de arranque cuenta como alcanzado, el de parada como superado. Un
grado de banda es un comienzo sensato.

### Lo que la pantalla rechaza

Tres combinaciones se rechazan al guardar, porque producen una zona que está
ahí pero nunca hace nada:

- un **objetivo en el lado equivocado del punto de arranque** — el aparato
  recibe entonces una temperatura para la que no tiene nada que hacer;
- **enfriar que arranca en o por debajo del punto donde arranca calentar** —
  ambos piden entonces la misma habitación a la vez;
- la zona en **la habitación en sí sin sensor de presencia**, o una zona que
  **no puede calentar ni enfriar**.

### El hogar o la habitación en sí

- **El hogar** (por defecto): horario, sueño y alguien-en-casa cuentan. Si
  pones además un sensor de presencia, actúa como condición extra: el hogar
  debe permitirlo **y** la habitación debe estar ocupada.
- **La habitación en sí**: horario, sueño y alguien-en-casa se omiten. Solo el
  sensor de presencia decide. Esto exige un sensor de presencia, o la zona
  nunca puede funcionar.

Así, una habitación puede ir por horario y otra por presencia.

## Paso 5 — Fuentes

Una fuente es un aparato capaz de servir a la zona. Tras guardar una zona,
eliges enseguida sus fuentes.

| Ajuste | Qué hace |
|---|---|
| **Entidad climática** | el aparato en sí |
| **Qué puede hacer este aparato** | solo calentar, solo enfriar, o ambas cosas. Una caldera es *solo calentar* |
| **Arrancar este aparato automáticamente** | desactivado lo deja en paz, ver abajo |
| **Orden dentro de esta zona** | qué fuente se prefiere; **el más bajo gana** |
| **Usar desde esta temperatura exterior** | el límite inferior; incluido en el rango |
| **Usar hasta esta temperatura exterior** | el límite superior; excluido del rango |

### Límites exteriores: medio abiertos

El límite inferior pertenece a la ventana, el superior no. Dos fuentes
adyacentes cubren así toda la escala, sin hueco ni solape.

¿Quieres gas por debajo de 3 °C y el aire acondicionado por encima? Entonces
**no** pongas la frontera en 3,0:

| Frontera | 2,9 °C | 3,0 °C | 3,1 °C |
|---|---|---|---|
| ambas en `3.0` | gas | **aire acondicionado** | aire acondicionado |
| ambas en `3.1` | gas | **gas** | aire acondicionado |

Pon la frontera igual en **cada** fuente, y nunca distinta — si no, aparece un
solape en el que ambas están permitidas.

### Un aparato que enciendes tú mismo

Desactiva **Arrancar este aparato automáticamente** para un aparato que manejas
a mano (un aire acondicionado en un dormitorio sin sensor de presencia, por
ejemplo). El director:

- **no lo enciende nunca**, por fría o caliente que esté la habitación;
- **lo deja** tal como tú lo pongas;
- **solo lo apaga** cuando ejecuta una función que la unidad exterior
  compartida no admite.

Si una función solo puede hacerla un aparato así, la integración lo avisa una
vez bajo *Reparaciones*. Confirma el aviso y no volverá — tampoco tras un
reinicio. Si la zona gana luego una nueva función manual, llegará un aviso
nuevo.

## Paso 6 — Circuitos de aire acondicionado

Solo necesario cuando unidades interiores comparten una unidad exterior. Si
cada unidad tiene la suya, déjalo vacío.

| Ajuste | Qué hace |
|---|---|
| **Nombre** | una etiqueta para distinguir circuitos |
| **Unidades interiores** | qué entidades `climate.*` cuelgan de esta unidad exterior. Incluye también unidades que el director no gestiona: también reclaman el compresor |
| **Puede calentar y enfriar a la vez** | desactivado para un multisplit normal; activado para un split simple o un VRF de tres tubos con recuperación de calor |
| **Política de conflicto** | quién gana cuando dos habitaciones quieren funciones opuestas |
| **Una zona perdedora puede ventilar** | activado = la perdedora pasa a `fan_only` en vez de apagarse, pero solo si la unidad conoce ese modo; si no, se apaga |
| **Pausa al cambiar de función** | cuánto tiempo está todo apagado antes del cambio |
| **Mínimo antes de un cambio de función** | cuánto tiempo debe haber funcionado una función antes de que la otra pueda tomar el relevo |
| **Descanso antes de que una unidad pueda rearrancar** | solo retrasa arranques, nunca paradas; por defecto 180 segundos |
| **Máximo de unidades a la vez** | el límite de capacidad de la unidad exterior; vacío = sin tope |

### Políticas de conflicto

| Política | Comportamiento |
|---|---|
| **Prioridad** (por defecto) | gana la zona con el número de prioridad más bajo |
| **Quien llegó primero** | la función ya en marcha conserva el circuito; una petición nueva espera |
| **Demanda** | gana la mayor desviación respecto a la consigna |
| **Estación** | la estación dicta la función; todo lo que vaya en contra se aparta |

## Paso 7 — Fuentes de calor compartidas

Una caldera o bomba de calor de la que tiran varias habitaciones mediante sus
propias válvulas. Déjalo vacío si el sistema enciende su propio quemador en
cuanto una válvula lo pide.

| Ajuste | Qué hace |
|---|---|
| **Nombre** | una etiqueta para distinguir fuentes de calor |
| **Entidad climática** | la caldera o bomba de calor en sí; no debe ser también fuente de una zona, o recibiría dos órdenes |
| **Zonas que sirve** | vacío = todas las habitaciones |
| **Temperatura objetivo fija** | vacío = sigue el objetivo más cálido entre las habitaciones que piden |

La fuente de calor funciona mientras una habitación a la que sirve se está
calentando, y se detiene cuando no queda ninguna.

## Paso 8 — Grupos exclusivos

¿Quieres que dos aparatos no funcionen **nunca** a la vez — una caldera de gas
y una bomba de calor, por ejemplo? No lo confíes solo a los límites exteriores.
Un valor olvidado basta para que arranquen juntos. Ponlos en cambio en un grupo
exclusivo: de los aparatos de un grupo, solo uno funciona a la vez.

Atento a lo que significa un grupo: **un** aparato del grupo a la vez. Si
quieres que la caldera de gas no estorbe a ningún aire acondicionado, mientras
que dos aires del mismo circuito sí pueden enfriar juntos, haz un grupo por
pareja — el gas con uno, el gas con el otro.

Un grupo también ata a los aparatos que enciendes tú mismo: cuando le toca a
otro miembro del grupo, el aparato manual se apaga. Y al revés: cuando un
aparato así ya está en marcha, ocupa el grupo y otro miembro espera.

## Paso 9 — Ventanas silenciosas

Horas en las que el director **no inicia nada por su cuenta**. Llegar a casa a
las once de la noche cuando estás a punto de acostarte no debe encender la
caldera.

Es un freno al **arranque**, no a la continuación:

- lo que ya funciona sigue regulado;
- enciende algo tú mismo y se retoma;
- lo que está apagado sigue apagado hasta que pase la ventana.

Las ventanas pueden cruzar la medianoche y llevan días de la semana. Un hogar
que se acuesta a las nueve entre semana y a las once el fin de semana pone dos:

| De | Hasta | Días |
|---|---|---|
| 21:00 | 09:00 | lun mar mié jue dom |
| 23:00 | 09:00 | vie sáb |

Sin ventanas configuradas, el freno no actúa.

## Paso 10 — Residentes

Déjalo vacío para un edificio donde no se sigue a nadie; las puertas de
presencia se omiten entonces en vez de bloquearlo todo para siempre.

| Ajuste | Qué hace |
|---|---|
| **Nombre** | una etiqueta para distinguir residentes |
| **Sensor de presencia** | normalmente una `person.*`; dice si este residente está en casa |
| **Sensor de sueño** | cuándo duerme este residente; vacío = no se sigue el sueño |
| **Estado que significa dormido** | el estado que el sensor de sueño informa al dormir |
| **El sensor de sueño cuenta de / hasta** | las horas en las que ese sensor significa algo; ambos vacíos = todo el día |

### Horarios

Tras guardar un residente, configuras sus horarios:

| Ajuste | Qué hace |
|---|---|
| **Es una ventana de vacaciones** | solo se aplica durante el horario de vacaciones, sustituyendo entonces las ventanas normales |
| **De / Hasta** | la ventana; puede cruzar la medianoche |
| **Días** | vacío = todos los días |

Un residente sin horario no participa en la puerta de horario. Quien no tiene
ventana un día no retiene la casa ese día.

### Sensor de sueño: ¿sin sensor, pero con un botón?

Un botón (`button` o `input_button`) no puede decir si duermes — su estado es
el instante de la última pulsación. Lo que sí funciona es un `input_boolean`
que conmutas con un botón: crea el interruptor, elígelo como sensor de sueño
con `on` como estado de dormir y deja que un botón lo conmute. Quien sí tiene
un sensor de sueño (un sensor de cama, un cargador inalámbrico) usa ese: es más
preciso.

Deja el sensor de sueño vacío y ese residente nunca cuenta como dormido.

## Paso 11 — Puertas y ventanas

Una apertura abierta el tiempo suficiente suspende las zonas afectadas.

| Ajuste | Qué hace |
|---|---|
| **Sensor** | el contacto de puerta o ventana; abierto cuenta como `on` |
| **Zonas afectadas** | vacío = toda la instalación |
| **Retardo antes de suspender** | vacío o 0 = en el momento de abrirse |

## Paso 12 — Guardar y cerrar

Elige **✅ Guardar y cerrar** en el menú principal. Solo entonces se escribe la
instalación.

Si algo está estructuralmente mal — una zona sin fuente útil, dos fuentes sobre
la misma entidad, una ventana exterior que no admite nada — primero ves una
lista, con la opción *Guardar de todos modos* o *Volver para cambiar algo*. Es
una **advertencia, no una negativa**: una instalación puede ser deliberadamente
peculiar, y solo tú sabes si es así. La misma lista aparece también bajo
**Reparaciones** mientras se aplique.

## Qué obtienes en Home Assistant

Un dispositivo por instalación, con debajo:

| Entidad | Para qué |
|---|---|
| `sensor.*_last_decision` | cuántas zonas están siendo servidas, con el plan completo como atributos |
| `sensor.*_would_command_<entity>` | el modo en que el director pondría este aparato — un sensor por aparato |
| `sensor.*_mismatch` | cuántos aparatos están ahora en un sitio distinto del que el plan quiere; 0 = director y casa de acuerdo |
| `sensor.*_<zone>_source` | qué fuente sirve esta zona, con lo que la zona quería, obtuvo y por qué |
| `binary_sensor.*_<zone>_blocked` | activado cuando una zona recibió menos de lo pedido, o quería funcionar pero una circunstancia la retuvo; las puertas cerradas están en los atributos |
| `binary_sensor.*_<zone>_on_stand_in` | activado cuando una zona funciona con un aparato suplente porque la primera opción es inalcanzable |
| `binary_sensor.*_stuck` | activado cuando una zona lleva demasiado tiempo con el mismo motivo de espera |
| `switch.*_director` | el interruptor principal; apagado = no se regula nada |
| `switch.*_holiday_schedule` | hace que cada día cuente como sábado, o como su propio horario de vacaciones |
| `switch.*_guest_mode` | sigue regulando mientras los residentes están fuera |
| `switch.*_<zone>_override` | devuelve una zona por completo a ti |
| `number.*_<zone>_priority` | la precedencia de esta zona; también configurable desde una automatización |
| `number.*_pre_conditioning_duration` | cuánto dura una pulsación de un botón de preacondicionamiento |
| `button.*_<zone>_pre_condition` | preacondiciona esta zona |

También hay una exportación de diagnóstico descargable con la configuración, la
última instantánea leída y el último plan.

## Los interruptores y botones

- **Interruptor principal** (`switch.*_director`): apagado = el director no hace
  nada en absoluto.
- **Modo invitados** (`switch.*_guest_mode`): hay alguien no seguido alojado,
  así que «casa vacía» no dice nada. El sueño de los presentes sigue contando, y
  fuera de la ventana de invitados toman el relevo las puertas normales.
- **Horario de vacaciones** (`switch.*_holiday_schedule`): cada día cuenta como
  sábado, o como su propia ventana de vacaciones. También se activa solo en
  cuanto un calendario configurado tiene un evento en curso con la palabra
  clave. Sin palabra clave, los calendarios se ignoran.
- **Override** (`switch.*_<zone>_override`): devuelve una zona por completo a
  ti. El director no envía nada a esa zona — ni siquiera un apagado. Las reglas
  del circuito siguen aplicándose a las demás habitaciones. El override expira
  solo en cuanto todos los presentes se acuestan o la casa queda vacía.
- **Botón de preacondicionamiento** (`button.*_<zone>_pre_condition`) y
  **duración** (`number.*_pre_conditioning_duration`): ver abajo.

## Acciones

| Acción | Para qué |
|---|---|
| `climate_director.evaluate` | decidir de nuevo ahora mismo, sin esperar un cambio de estado |
| `climate_director.precondition` | iniciar el preacondicionamiento |
| `climate_director.cancel_precondition` | cancelar una petición de preacondicionamiento en curso |

`climate_director.evaluate` es práctico durante la puesta en marcha. En modo
sombra sigue sin ejecutar nada — solo recalcula.

## Preacondicionamiento

La única forma de hacer funcionar una casa vacía, y deliberadamente la única
que debes activar a mano.

- **Con un botón**: cada zona tiene `button.*_<zone>_pre_condition`. Cuánto
  dura una pulsación así está en `number.*_pre_conditioning_duration` (60
  minutos por defecto, de un cuarto de hora a dos horas).
- **Con la acción**:

  ```yaml
  action: climate_director.precondition
  data:
    zone_ids: [<zone>]
    minutes: 45
  ```

**Importante:** no dices qué debe pasar. La petición solo abre la puerta;
después la integración decide exactamente igual que siempre — la banda muerta
comprueba si hace demasiado frío o calor, la estación y la ventana exterior por
fuente eligen el aparato. Si la habitación ya está bien, el aparato sigue
apagado.

Durante una petición de preacondicionamiento siguen aplicándose el interruptor
principal, un override, la banda muerta, la estación, la ventana exterior por
fuente, puertas y ventanas, el circuito y los grupos exclusivos. Se omiten:
*alguien en casa*, *despierto*, *horario*, *presencia en la habitación*, la
ventana exterior por zona y la ventana silenciosa.

Una ventana o puerta abierta **rechaza** una petición. Quien abrió la ventana
puede decir: hazlo de todos modos.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 90
  ignore_openings: true
```

Dos límites imposibles de olvidar:

- **Expira solo.** Pide más del máximo configurado y tu petición se acorta. No
  indicar tiempo te da el máximo.
- **Solo cuenta dentro de la ventana** (06:00–23:00 por defecto). Fuera, una
  petición no cuenta.

Cancélalo con `climate_director.cancel_precondition`.

## Tomar el mando

- **Apagar un aparato tú mismo** (en el aparato o con el mando) silencia esa
  zona. El director no lo vuelve a encender dos segundos después. La zona
  vuelve a participar en cuanto la enciendes tú, en cuanto todos los presentes
  se acuestan, o en cuanto es el día siguiente.
- **Encender un aparato a mano unas horas** funciona con un script al lado,
  siempre que te devuelvas esa zona con el override durante ese tiempo. Sin
  override, el director recalcula su propio plan en la siguiente evaluación y
  apaga tu aparato. Un aparato con *Arrancar este aparato automáticamente*
  desactivado no necesita override.
- **Una habitación que manejas siempre tú mismo**: haz de ella una zona igual
  (si no, la integración no sabe de ese aparato), elige la entidad `climate.*`
  del propio aparato como sensor interior y desactiva *Arrancar este aparato
  automáticamente* en la fuente.

## Evaluar una prueba en modo sombra

Tres sensores hacen que una prueba en modo sombra sea evaluable después:

- **`sensor.*_mismatch`** es la cifra clave. Cero significa que el director está
  de acuerdo con lo que funciona en ese momento. Un pico breve es normal; un
  valor que se mantiene es un desacuerdo real. Pon este sensor en un gráfico de
  historial.
- **`sensor.*_would_command_<entity>`** se coloca junto al historial de la
  entidad `climate` del mismo nombre. Dos líneas que se siguen = el director
  decidió lo mismo que tus automatizaciones.
- **`sensor.*_<zone>_source`** y **`binary_sensor.*_<zone>_blocked`** dicen
  después *por qué*: qué fuente se eligió y qué puerta retuvo una zona.

## Blueprints y notificaciones

Climate Director no envía mensajes por su cuenta. A dónde va una notificación,
cómo suena y si puede llegar de noche difiere por hogar. En su lugar, la
integración prepara eventos y sensores para colgar tu propia automatización.
Tres de ellos no deberías saltártelos:

| Blueprint | Por qué no puedes prescindir de él | Enlace de importación |
|---|---|---|
| **Supervisión** | avisa de fallos silenciosos: una zona atascada, o una zona funcionando con un aparato suplente más caro | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| **Preacondicionamiento rechazado** | pulsaste un botón y no pasó nada; este lo avisa, con un botón *Hazlo de todos modos* | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| **Qué se decidió** | la herramienta más práctica durante la configuración y en modo sombra | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

La importación va por **Ajustes → Automatizaciones y escenas → Blueprints →
Importar blueprint**, con el enlace de arriba.

> **Importar solo no basta.** Un blueprint es una plantilla; nada escucha hasta
> que construyes una automatización a partir de él. Hazlo justo después de
> importar.

Mientras nadie escuche una petición de preacondicionamiento rechazada, Home
Assistant muestra un aviso de reparación al respecto. Desaparece solo en cuanto
una automatización se apoya en ese evento.

## Resolver problemas

- **`binary_sensor.*_stuck`** se enciende cuando una zona lleva demasiado tiempo
  con el mismo motivo de espera (15 minutos por defecto), o cuando una entidad
  configurada no se puede leer — mal escrita, borrada o temporalmente
  `unavailable`. Qué entidades son está en el atributo `unusable_entities`.
  Un sensor legible pero que no da ningún número también figura ahí
  (`no number`).
- **`binary_sensor.*_<zone>_on_stand_in`** se enciende cuando una zona funciona
  con una fuente que no era la primera opción, porque la primera opción es
  inalcanzable. La habitación simplemente se calienta — y por eso mismo, sin
  sensor, no notas nada hasta la factura de la luz.
- **Los avisos de reparación** bajo *Reparaciones* muestran errores
  estructurales de la configuración. Las zonas sanas se siguen regulando; una
  zona rota no detiene la instalación.
- **El diagnóstico** (descargable en la integración) contiene la configuración,
  la última instantánea leída y el último plan. Con esos tres, cualquier
  decisión es exactamente reproducible.

## Idiomas

La explicación bajo cada campo sigue el idioma de tu Home Assistant.
Incluidos: neerlandés, inglés, alemán, francés, español y árabe.

[![Invítame a un café en Ko-fi](https://img.shields.io/badge/Ko--fi-Invítame%20a%20un%20café-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Patrocinar en GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)
