### Cómo leer esta guía
Cada campo cambia **qué operaciones se toman** o **cómo se miden**. Cambiá de a uno y anotá qué pasa. Cuantas más combinaciones probás, más probable es que alguna salga bien por azar (por eso existe el contador de pruebas).

## Fuente de datos, 1. Instrumento a operar y 2. Datos
- **Fuente.** *MT5 directo*: lee el historial del terminal de FTMO (solo corriendo la app en tu PC con Windows y MT5 abierto). *CSV exportado*: archivos generados con `exportar_mt5.py`, uno por símbolo. *Sintéticos*: series inventadas para probar la interfaz; no dicen nada del mercado real.
- **Símbolos.** Podés elegir varios (metales, cripto, forex, índices). Con uno hacés el análisis detallado; con dos o más se habilita *Comparar símbolos*.
- **Temporalidad.** Tamaño de cada vela (M1, M5, H1...). Define cada cuánto se mira el cruce. Velas chicas dan más operaciones, más ruido y un spread que pesa más respecto del SL.
- **Desde / Hasta.** Período descargado. El terminal puede guardar un máximo de velas por gráfico, así que en M1 o M5 el historial disponible es más corto.
- **Remuestrear a.** Arma velas más grandes a partir de las descargadas (por ejemplo H4 desde H1). No puede armar velas más chicas.
- **Recortar período** (solo con CSV o datos de demo). Limita el análisis a un tramo del archivo cargado. Con MT5 no aparece: el período lo define *Desde / Hasta*.
- **Point (solo CSV).** Tamaño del punto del símbolo (0,01 en oro; 0,00001 en EURUSD). Sirve para pasar el spread de puntos a precio, y solo hace falta si el CSV no trae la columna `point`.
- **Tendencia / cantidad de series (sintéticos).** Con 0 la serie es azar puro: ninguna estrategia debería ganar ahí. Es una buena prueba de que el sistema no inventa ventaja.

## 3. Señal y gestión
- **EMA corta y larga.** La señal es el cruce, evaluado al cierre de la vela: la corta por encima de la larga da una compra y por debajo una venta. La entrada es al cierre de esa vela. La corta debe ser menor que la larga.
- **Dirección.** Largos y cortos, solo largos o solo cortos.
- **SL en.** Cómo se calcula la distancia del stop:
  - *Múltiplo de ATR*: SL = ATR × valor. Se adapta a la volatilidad del momento.
  - *% del precio*: SL = precio × porcentaje.
  - *Dólares fijos*: SL = una cantidad fija de dinero (se convierte a precio con el lote, ver sección 3).
- **Valor del SL.** El múltiplo o el porcentaje, según el modo.
- **RR (1:x).** El TP queda a SL × RR de distancia. Con RR 2 hay que ganar al menos 1 de cada 3 operaciones para no perder (ese es el % de equilibrio: 100 / (1 + RR)).
- **SL y TP en dólares.** Con *Dólares fijos* podés indicar el TP como ratio o también en dólares. La relación TP/SL pasa a ser libre (por ejemplo TP de 50 y SL de 100 da 0,5).
- **Período ATR.** Ventana del ATR (14 por defecto). Se usa para el SL por ATR, para la distancia a la SMA y para el filtro de ATR.

**Entrar en pullback a la EMA (opcional).** Por defecto la entrada se hace al cierre de la vela del cruce. Si lo activás, el cruce sigue siendo la señal, pero se deja una orden pendiente y se entra cuando el precio retrocede hacia la EMA, a favor de la tendencia del cruce.
- **Retroceso hacia la EMA (%):** qué parte de la distancia entre el extremo posterior al cruce y la EMA tiene que devolver el precio. 0 = entrar al cierre (igual que apagado); 100 = entrar recién cuando toca la EMA. El nivel se mueve a medida que el precio hace nuevos extremos.
- **EMA de referencia:** corta (retrocesos más chicos, más entradas) o larga (más profundos, menos entradas).
- **Caducidad (velas):** si en ese plazo no hubo retroceso, la orden se cancela. También se cancela si aparece un cruce contrario.
- **Cómo leerlo:** mirá el porcentaje de órdenes ejecutadas y comparalo contra la versión sin pullback **por mes**, no solo por operación: el pullback suele mejorar el R por operación pero deja pasar las tendencias fuertes que no retroceden. El backtest supone que la orden se ejecuta cuando el precio toca el nivel, algo optimista en la práctica.

### SL a una distancia del cruce de medias
En "3. Señal y gestión", el campo **SL en** tiene la opción **Distancia al cruce de medias** (con "Precio cruza una SMA" se llama **Distancia a la media**): el SL no se mide desde el precio de entrada sino desde el cruce.
- **Referencia**: el nivel del cruce, que es el punto medio entre la media corta y la larga en la vela de la señal (en esa vela valen casi lo mismo). Con "Precio cruza una SMA", la única media.
- **Distancia en pips, en dólares de precio o en % del precio.** Con «% del precio» la distancia es un porcentaje del propio nivel de referencia: 0,15 % de un nivel en 2.350 son 3,53 (crece o baja con el precio, sin convertir nada). 1 pip = 10 puntos = 10 × tick_size del símbolo: en el oro 0,10 (30 pips = 3,00), en EURUSD 0,0001. «Dólares (precio)» es la distancia en el precio del activo (en el oro, 3 = el precio se mueve 3,00). El «% del precio» de acá es sobre el nivel del cruce; el SL en «% del precio» (otro modo) se mide desde el precio de entrada. Tampoco es lo mismo que el SL en «Dólares fijos», que es una pérdida en dinero de la cuenta.
- **Cómo queda el SL:** fijo en el nivel del cruce **menos** la distancia en las compras y **más** la distancia en las ventas, tomado en la vela de la señal (con pullback, en la vela anterior al llenado). No se mueve después.
- El **riesgo cambia en cada operación**: depende de qué tan lejos estaba el precio de la media. Con el lote fijo, eso cambia los dólares en juego. Para acotarlo, usá «Riesgo máximo por operación» en «4. Lotaje y dinero».
- Si al entrar la media quedó del lado equivocado del precio (el SL quedaría al revés), **esa señal no se opera**. El embudo muestra cuántas fueron.
- El TP por RR (1:x) y la salida por cruce contrario siguen funcionando: el RR se mide sobre la distancia real al SL de esa operación. El bot de MT5 lo respeta.

### Salida (Take Profit): objetivo fijo o cambio de lado de la media
En "3. Señal y gestión", el campo **Salida (Take Profit)** permite elegir:
- **Objetivo fijo (RR o US$)**: como siempre, el TP está a una distancia fija del SL.
- **Cuando las medias se cruzan en sentido contrario** (cruce de dos medias, en las páginas EMA y SMA): no hay TP. Un largo se cierra al cierre de la primera vela en que la media corta queda **por debajo** de la larga; un corto, cuando queda **por encima**. Es decir, la operación dura hasta que el cruce se invierte.
- **Cuando el precio cambia de lado de la media** (señal "precio cruza una SMA"): no hay TP. Un largo se cierra al cierre de la primera vela que queda **por debajo** de la media; un corto, al cierre de la primera vela que queda **por encima**. Ejemplo: una vela M5 cierra sobre la SMA 200 y se compra; se vende cuando una vela cierre por primera vez debajo de la SMA 200. Con el cruce de dos medias, "cambio de lado" significa que el cruce se invierte.
- El **SL sigue activo** y se revisa antes en cada vela. La salida por señal se evalúa recién desde la vela siguiente a la de la entrada.
- En los resultados, «TP» son las operaciones que cerraron con ganancia y «SL» las que cerraron con pérdida (por SL o por la señal). La tabla de operaciones trae la columna «motivo» (tp / sl / senal) y el R de cada una es el real, no uno fijo; el % de equilibrio se calcula con el pago medio observado.
- El **bot de MT5** respeta esta salida: abre sin TP y cierra a mercado cuando una vela cerrada queda del otro lado de la media (también lo detecta si el PC estuvo apagado), y avisa «SALIDA POR SENAL» al celular.

## 4. Lotaje y dinero
- **Lotes.** Tamaño de la posición (1, 0,5, 0,1...). Tiene que respetar el mínimo y el paso del símbolo.
- **tick_size y tick_value.** Datos del contrato. Con MT5 directo se leen solos de cada símbolo. Con CSV o sintéticos los cargás a mano (en MT5: clic derecho en el símbolo → Especificación).
- **Comisión por lote.** Se resta de cada operación.
- **Capital de la cuenta.** Es el capital inicial: sobre él se calculan los límites de pérdida y, en la conclusión final, la probabilidad de tocarlos.
- **Aplicar reglas de cuenta en el backtest.** Tildado (por defecto), el backtest simula la cuenta en orden cronológico y respeta los límites y controles de abajo: las operaciones bloqueadas no cuentan y los resultados, el veredicto y el azar reflejan esas reglas. Destildado, funciona como antes. Los valores quedan cargados y el bot de MT5 los usa igual. Cada tramo (todo, in-sample, out-of-sample) y cada corrida al azar arranca con una cuenta nueva.
- **Pérdida diaria máxima (%) y modo.** 5 % por defecto (0 = sin límite). *Trailing*: el límite es un % del balance con el que empezó el día y se recalcula cada día. *Estático*: un monto fijo en dólares (el % del capital inicial) que se resta del balance de inicio del día. Se vigila el equity, con lo flotante incluido. Al tocarlo se cierra todo y no se opera más ese día.
- **Pérdida total máxima (%) y modo.** 10 % por defecto (0 = sin límite). *Estático*: el piso es fijo (capital inicial menos el %), como en FTMO. *Trailing*: el piso sube con el balance máximo alcanzado y nunca baja. Al tocarlo la cuenta «se quema»: el backtest termina ahí y el bot se detiene hasta que lo reactives a mano.
- **Colchón antes del límite (%).** 1 % por defecto. Se resta a los dos límites: con 5 % y 10 % el bot frena en 4 % y 9 %. Cubre saltos de precio y slippage. Tiene que ser menor que los límites. Abajo se ven los límites efectivos en % y en dólares.
- **No abrir si el SL rompe un límite.** Tildado por defecto. Si el SL de una operación, perdiendo al máximo, llevaría el equity por debajo del límite diario o total, la operación se saltea. Sin esto, una operación abierta se cierra en el momento en que el equity toca el límite.
- **Riesgo máximo por operación (% del capital).** Destildado por defecto. Si el riesgo del SL (más la comisión) supera el %, la operación se saltea; los lotes siguen fijos.
- **Pausa para volver a operar tras una pérdida (minutos).** Destildado por defecto. Después de una operación que cierra en pérdida (por SL, por límite o por la salida por señal), las señales que caen dentro de ese tiempo se descartan, no se posponen.
- **Pausa para volver a operar tras una ganancia (minutos).** Destildado por defecto. Igual que el anterior, pero después de una operación que cierra en ganancia: las señales que caen dentro de ese tiempo se descartan, no se posponen. Se pueden usar los dos a la vez. En el resumen de las reglas de la cuenta, las señales salteadas se cuentan por separado («pausa tras pérdida» y «pausa tras ganancia»). El bot también lo respeta.
- **Retroceso para volver a operar tras una ganancia (%) y vencimiento.** Tiene su propia casilla y es independiente de la pausa por minutos: podés usar solo una, solo la otra, o las dos juntas. Solo para ganancias y solo en el *mismo sentido*. Destildado por defecto. Si está activo, después de una compra ganadora la próxima compra solo se toma cuando el precio retrocede ese % del recorrido de la ganancia (de la entrada al cierre), medido desde el cierre: compra a 4000, TP 4050, 50% → próxima compra solo con precio ≤ 4025. En una venta ganadora es al revés (precio ≥ cierre + %). Si las dos están activas se exigen las dos cosas: que pasen los minutos y que el precio retroceda. *Vencimiento*: **Nunca** (rige hasta que el precio retroceda o haya otra operación), **Al terminar el día** (hora CE(S)T) o **Después de N horas**; pasado ese momento se vuelve a operar sin exigir el retroceso. Las señales descartadas se cuentan como «sin retroceso». El bot lo respeta y guarda el precio de cierre y el recorrido de la última ganadora de cada lado.
- **Sentido de la pausa (tras pérdida y tras ganancia).** Cada pausa tiene su selector: *Ambos* frena a todas las señales (como siempre), *Mismo sentido* solo a las del mismo lado que la operación que cerró (si cerró una compra, espera antes de otra compra) y *Sentido contrario* solo a las del lado opuesto (si cerró una compra, espera antes de una venta). Cada operación cerrada arranca su propio reloj según su sentido y su resultado, y si hay dos pausas activas una señal se descarta si cualquiera la frena. Por defecto no hay ninguna pausa activa. El bot lo respeta y recuerda de qué lado fue la última operación ganadora y perdedora.
- **Retirar al llegar al objetivo.** Destildado por defecto. Hace que «Cuenta quemada» cuente los retiros: cuando la ganancia del ciclo llega al objetivo (% del capital inicial), se retira TODA esa ganancia y el balance vuelve al capital inicial. Sin el colchón de lo ganado, una mala racha puede quemar la cuenta aunque sin retiros se salvara. El piso de pérdida total trailing se mantiene en el máximo anterior, y el retiro no cuenta como pérdida del día. No incluye plazos ni reparto de ganancias de la firma. Solo afecta al backtest: el bot opera con el balance real y los retiros los hacés vos. Con esto activo aparece la sección «Retiros de la cuenta» (cuántos retiros, tiempo hasta quemarse, tiempo entre retiros) y el botón «Calcular el monto ideal», que repite la simulación con varios objetivos y marca con ★ el que más retira en este historial. Es el mejor de esa secuencia de operaciones, no un valor garantizado.
- **Desfase del servidor.** Sirve para cortar el día a medianoche de Europa Central (hora CE(S)T), como FTMO, y no a la del servidor. Medilo con el mercado abierto; es el mismo dato del filtro de sesión (si lo usás, manda ese).
- **Resultados de las reglas.** Con las reglas aplicadas aparecen: días bloqueados por el límite diario, señales salteadas (por día bloqueado, protección, riesgo o pausa), si la cuenta se quemó y el peor día. Dentro de una vela no se conoce el máximo flotante, así que los límites del día se aplican de forma aproximada.
- **Fórmula.** Dinero por cada 1,00 de precio = tick_value / tick_size × lotes. En oro con 0,10 lotes son 10 US$ por cada 1,00.
- **Qué cambia y qué no.** En SL por ATR o por porcentaje, el lote solo escala los resultados en dinero (R y % no cambian). Con SL en dólares, el lote **sí** cambia las operaciones, porque define qué tan lejos queda el stop en precio.

## 5. Costos
- **Spread.** *De la vela*: el spread de cierre de cada vela (en historial viejo suele venir en 0, lo que subestima el costo). *Ceros → mediana*: reemplaza los ceros por la mediana. *Valor fijo*: el que indiques. *Sin spread*: solo para comparar.
- **Cómo se aplica.** Los largos entran al precio de venta (ask). En los cortos, el SL y el TP se activan con el ask.
- **Costo extra por operación.** Unidades de precio que se restan a cada operación resuelta (slippage, comisión). En R equivale a costo / distancia del SL.

## 6. Filtros
Son independientes y se pueden combinar. Un cruce se toma solo si pasa todos los filtros activos.
- **SMA.** Compra solo si el cierre está por encima de la SMA y venta solo si está por debajo.
  - *Distancia mínima*: pide que el cierre esté a por lo menos N × ATR de la SMA, para evitar cruces pegados a ella (0 = sin condición).
  - *Pendiente a favor*: la SMA tiene que estar subiendo (en compras) o bajando (en ventas) respecto de hace N velas.
- **VWAP (diario).** Precio medio del día ponderado por volumen (precio típico = (máx + mín + cierre) / 3), reiniciado en cada día del servidor. Largos solo si el cierre está sobre el VWAP y cortos solo si está debajo: es un filtro de contexto, no una señal por sí solo. En forex, oro e índices el volumen es el de ticks (cuántas veces cambió el precio), no el volumen real. *Distancia mínima* (por defecto 0,5×ATR): exige que el precio esté al menos esa distancia del VWAP, para no operar en la zona de ruido pegada a él. *Minutos mínimos desde el inicio del día* (por defecto 30): al abrir, el VWAP es casi igual al precio y filtrar ahí es ruido. Ninguno de los dos valores es un estándar formal: son reglas prácticas habituales, y la ablación te dice si aportan. Necesita velas menores a D1; con datos de demo (volumen constante) es solo un promedio simple.
- **ADX.** Mide la **fuerza** de la tendencia, no su dirección.
  - *Mínimo*: descarta los cruces con ADX bajo (por ejemplo menor a 20, mercado sin tendencia).
  - *Máximo*: descarta tendencias ya muy extendidas (0 = sin límite).
  - *Creciente N velas*: pide que el ADX actual sea mayor que hace N velas.
- **Filtro de rango (ratio de eficiencia).** Detecta si el precio está en rango (va y viene sin avanzar) y, si es así, no opera la señal.
  - Mide, sobre las últimas *N* velas, cuánto avanzó el precio en línea recta (|cierre actual − cierre hace N velas|) dividido por todo lo que recorrió (la suma de los movimientos de vela a vela). Da un número de 0 a 1: **1 = tendencia limpia**, **0 = ida y vuelta sin avanzar**.
  - *Ventana*: cuántas velas mira (20 por defecto). Más chica reacciona más rápido y es más ruidosa; más grande es más estable pero más lenta.
  - *Ratio mínimo*: por debajo de este valor la señal se descarta (0,30 por defecto). Más alto = más exigente, opera menos.
  - Usa solo datos hasta la vela de la señal, igual que en el bot. Como todo filtro, reconoce el rango un poco tarde y puede perder alguna ruptura.
  - Se parece al ADX (los dos miden fuerza de tendencia): conviene probar uno u otro con el modo ablación y mirar el out-of-sample, y usar los dos juntos solo si la mejora es clara.
- **ATR.** Mide la volatilidad.
  - *Mínimo / máximo (% del precio)*: ATR dividido el cierre, por cien.
  - *Modo relativo*: compara el ATR actual con su promedio de las últimas N velas. Con mínimo 0,8 descarta el mercado dormido y con máximo 2,0 descarta la volatilidad extrema.
- **Sesión y horario.** Con el casillero **sin marcar** (por defecto) opera **24/5, todo el mercado**: toma cruces a cualquier hora en que el mercado esté abierto, sin filtro y sin necesitar el desfase del servidor. Con el casillero **marcado** solo toma cruces dentro de la rueda de Tokio (9:00 a 15:30), Londres (8:00 a 16:30) o Nueva York (9:30 a 16:00), en horario local de cada bolsa y con el horario de verano de cada plaza. Se pueden elegir varias. Ojo: las tres juntas no equivalen a 24/5, porque dejan afuera unas 4 a 5 horas por día (entre el cierre de Nueva York y la apertura de Tokio, y entre el cierre de Tokio y la apertura de Londres).
  - *Limitar horario de cada sesión*: por defecto cada sesión se mide **completa**. Al marcar «Limitar horario de…» elegís un rango **en hora Argentina**; arranca cuando abre la bolsa de esa plaza (hoy: Tokio 21:00, Londres 05:00, Nueva York 11:30) y termina donde cierra esa bolsa (hoy: Tokio 03:30, Londres 13:30, Nueva York 18:00). Ejemplo: para operar solo las dos primeras horas de Nueva York, ponés 11:30 a 13:30.
  - *Se corre solo con el horario de verano*: el rango se guarda como hora de esa plaza (por ejemplo, 9:30 a 11:30 de Nueva York), no como número fijo en hora Argentina. Cuando cambia el horario de verano de Londres o de Nueva York, el rango se corre una hora en hora Argentina y sigue siendo la misma franja de la plaza. Tokio no cambia. En el backtest esto vale para todo el historial, y el bot lo hace igual. Los números que ves en hora Argentina son los de hoy.
  - *Cada sesión limitada opera solo en su rango*; las no limitadas, completas. Si dos sesiones se pisan, alcanza con estar dentro de una.
  - *Excluir pausa de mediodía*: casillero por sesión que deja operar la sesión (completa o con tu rango) **salvo en su pausa**. Las pausas son fijas y están en hora local de la plaza: Tokio 11:30 a 12:30 (en Argentina 23:30 a 00:30, todo el año), Londres 12:00 a 13:00 (hoy 09:00 a 10:00 en Argentina; en verano 08:00 a 09:00) y Nueva York 12:00 a 14:00 (hoy 14:00 a 16:00 en Argentina; en verano 13:00 a 15:00). Se corren solas con el horario de verano.
  - *Qué velas se excluyen*: las que **abren** desde el inicio de la pausa hasta antes del fin. En M5 con la pausa de Tokio: la 11:25 se opera, la 11:30 es la primera excluida, la 12:25 la última excluida y la 12:30 se vuelve a operar. En velas más grandes, solo la que abre dentro de la pausa (en H1, la de 12:00 en Tokio).
  - *Solo bloquea entradas nuevas*: una operación ya abierta sigue con su SL y TP durante la pausa. La pausa se saca solo de su propia sesión; si otra sesión elegida cubre esa hora, se opera igual. Si limitás el horario y la pausa cae afuera de tu rango, no cambia nada.
  - La hora que se mide es la de apertura de la vela de la señal, igual que antes.
  - *Desfase del servidor*: diferencia entre la hora de las velas del broker y UTC en invierno (GMT+2 → 2). **Hay que medirlo con el mercado abierto**, porque si está mal las sesiones quedan corridas.
  - *El servidor cambia con EE.UU.*: casi todos los brokers pasan de GMT+2 a GMT+3 con el verano de EE.UU.
  - En BTC el filtro se desactiva solo (opera 24/7).

## 7. Control de sobreajuste
- **Out-of-sample reservado (%).** El último tramo del historial, que se mide aparte. Si el modelo funciona en el tramo de ajuste (in-sample) pero no en este, probablemente era azar o sobreajuste.
- **Repeticiones del azar.** Cuántas veces se simulan entradas aleatorias con la misma cantidad de operaciones y las mismas reglas de SL, TP y spread. Sirve de vara de comparación.
- **Pruebas en la sesión.** Cuenta cuántas configuraciones evaluaste. Con muchas pruebas, un buen resultado puede ser casualidad.

## Cómo leer los resultados
- **Expectativa (R).** Promedio de resultado por operación, donde 1 R es lo que arriesgás. +0,3 R significa que, en promedio, ganás 0,3 veces tu riesgo por operación.
- **% TP vs. equilibrio.** El anillo es el porcentaje de operaciones que llegaron al TP. La rayita es el mínimo necesario para no perder; si el anillo la pasa, la expectativa es positiva.
- **Mejor que el azar.** Porcentaje de las simulaciones al azar que quedaron por debajo de tu resultado. Cerca de 50% no se distingue de entrar al azar. Un valor alto sugiere algo, pero no lo prueba.
- **Racha de SL y drawdown.** La peor racha de pérdidas seguidas y la mayor caída desde un máximo de la curva. Son lo que hay que poder aguantar en una cuenta de fondeo.
- **Ambiguas.** Velas que tocaron el SL y el TP a la vez. Como con velas no se sabe cuál fue primero, se cuenta SL.
- **Abiertas, ignoradas, tomadas, descartadas.** *Abiertas*: sin resolver al final de los datos. *Ignoradas*: cruces que llegaron con otra operación en curso. *Descartadas*: cruces que no pasaron algún filtro.
- **Ablación.** Corre el cruce solo y después cada filtro por separado, para ver qué aporta cada uno. Mide los filtros con valores fijos, no con los que pusiste.
- **Comparar símbolos.** Mismos parámetros en varios mercados. Sirve para ver si la idea se sostiene en general, no para elegir al ganador.
- **Resultados en dinero.** Son teóricos: el slippage y los gaps pueden empeorarlos.

## Conclusión final
Al final del resultado, la app arma tres cosas:
- **Qué habría pasado.** Un párrafo con el período, el símbolo, la temporalidad, el cruce y todos los parámetros que marcaste, y cuánto habrías ganado o perdido en dinero.
- **Veredicto.** Se calcula con criterios fijos y visibles (✓ cumple, ! con reservas, ✕ no cumple):
  1. *Muestra suficiente*: al menos 100 operaciones y 30 en out-of-sample. Si no se cumple, el veredicto es **no concluyente**.
  2. *Expectativa positiva*: en todo el período y en out-of-sample.
  3. *Ventaja estadística*: probabilidad de que la ventaja sea real (se calcula con las operaciones ganadas y perdidas y el % de equilibrio). Se exige 95%, y 99% si llevás más de 10 pruebas.
  4. *Mejor que el azar* en out-of-sample (90% o más).
  5. *Consistencia por año*: expectativa positiva en al menos el 60% de los años con 10 o más operaciones.
  6. *Peso de los costos*: spread de hasta el 20% del SL.
  7. *Riesgo para la cuenta*: hasta 10% de probabilidad de tocar la pérdida máxima en 12 meses.

  Resultado: **Válida para intentar** (todo cumple, con a lo sumo una reserva), **Dudosa** (indicios, pero no alcanza), **No válida** (sin ventaja estadística o sin expectativa positiva) o **No concluyente** (pocas operaciones).
- **Probabilidad de terminar en ganancia a 1, 3, 6 meses y 1 año.** Es la probabilidad de que el resultado acumulado a ese plazo sea positivo. Se simula miles de veces: en cada simulación se sortea la probabilidad real de acierto (que es incierta, más cuando hay pocas operaciones) y luego las operaciones que entrarían en ese plazo, según la frecuencia observada. Se muestra con todo el historial y solo con el out-of-sample (más conservador). El resultado típico y el riesgo de tocar la pérdida máxima usan el escenario conservador.

**Límites que conviene tener presentes:** supone que el futuro se parece al pasado, que las operaciones son independientes y que los costos reales son los modelados. Una probabilidad alta indica que la historia fue consistente, no que el futuro esté garantizado. Por eso el veredicto más favorable siempre dice "empezando en demo".

---

### Generar bot (barra lateral, debajo de los menús)

El botón **Generar bot (.mq5)** descarga un Expert Advisor de MetaTrader 5 con los valores que tenés cargados: EMAs, dirección, SL y TP, lotes, filtros (SMA, VWAP, ADX, rango, ATR, sesión) y pullback. Solo arma texto, así que funciona también en la versión online y no necesita MT5.

**Cómo usarlo:** copiá el archivo a `MQL5/Experts` (en MT5: Archivo → Abrir carpeta de datos), abrilo en MetaEditor y compilá con F7. Antes de operar, corrélo en el Strategy Tester y compará con la app; después probalo en demo.

- **Mismo gráfico:** ponelo en el símbolo y la temporalidad con que hiciste el backtest (el bot avisa si no coinciden).
- **Lotes fijos**, como en la app. Con SL en dólares, el bot convierte el monto a distancia de precio con el valor del tick de tu broker.
- **Protección de cuenta (incluida):** corta todo si la pérdida del día llega al 4 % o la total al 8 % del balance inicial (editables). Quedan por debajo de los límites de FTMO (5 % y 10 %).
- **Sesiones:** el bot necesita el desfase horario de tu servidor (el mismo campo de la app).
- **Veredicto:** si el backtest no respalda la estrategia, la app lo advierte y el archivo lo indica en su cabecera. No se bloquea la descarga.
- **Límites:** una operación a la vez por magic number; no incluye slippage ni gaps, y los resultados reales pueden diferir del backtest.

**Avisos al celular (notificaciones push de MT5).** El bot avisa: operación abierta (a mercado o por pullback), cierre por TP, por SL o por otro motivo (con el resultado en dinero), freno diario, freno total, rechazo al arrancar, bot iniciado (primera puesta en marcha) o recargado (cada vez que se vuelve a cargar), bot detenido (con el motivo), trading algorítmico desactivado o reactivado, pérdida y recuperación de la conexión con el servidor, reinicio tras un hueco (PC apagada, suspendida o MT5 cerrado) y un chequeo diario a las 20:00 de Argentina («CHEQUEO DIARIO OK» si todo anda, o «CON PROBLEMAS» y el motivo). Si un día no llega el chequeo de las 20:00, el bot o la PC no están funcionando. Requiere configurar el MetaQuotes ID en Herramientas → Opciones → Notificaciones.

## Objetivo y retiros
(Con «Retirar al llegar al objetivo» activo en la sección 4, esta sección se reemplaza por «Retiros de la cuenta» y «Monto ideal a retirar», que usan la simulación de la cuenta con sus límites.)
Muestra cuánto tarda la estrategia en ganar un porcentaje del balance inicial (por defecto 5 %) y, si retiraras cada vez, cuánto tarda en volver a ganarlo, hasta el final del período.
- **Primer objetivo:** tiempo desde el inicio del período hasta que la ganancia acumulada de las operaciones cerradas llega al objetivo.
- **Retiros logrados:** cuántas veces lo alcanzó. En cada retiro se supone que retirás todo lo ganado, así que el balance vuelve al inicial y arranca un ciclo nuevo.
- **Tiempo medio entre retiros:** promedio, mediana, mínimo y máximo de los ciclos.
- **Ciclo en curso:** cuánto lleva ganado el tramo final, que todavía no llegó al objetivo.
- *Objetivo por retiro:* lo podés cambiar (por ejemplo 8 o 10 %). Se calcula sobre el **capital** cargado en la sección 4.
- Las caídas cuentan: si el ciclo baja de cero, hay que recuperarlas antes de llegar al objetivo. El tiempo es calendario (incluye fines de semana) y es teórico: no cuenta la ganancia flotante.

## Backtester SMA (página aparte en el menú)
Es el mismo backtester que el de EMA, con todos los campos y resultados iguales. Lo único que cambia está en "3. Señal y gestión":
- **Señal = Cruce de dos SMA**: entra cuando la SMA corta cruza a la larga (valores por defecto 20/50).
- **Señal = Precio cruza una SMA**: una sola media; compra cuando el cierre cruza hacia arriba de la SMA y vende cuando cruza hacia abajo. Se carga solo el período.
- Con pullback, el nivel de referencia es la misma media (la SMA única, o la corta/larga elegida).
- El botón "Generar bot (.mq5)" arma un bot con el mismo tipo de media y la misma señal; se aplican las mismas reglas de veredicto y la protección de cuenta.
- Es independiente de la página EMA: los valores que cargues en una no se mezclan con la otra.
