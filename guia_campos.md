### Cómo leer esta guía
Cada campo cambia **qué operaciones se toman** o **cómo se miden**. Cambiá de a uno y anotá qué pasa. Cuantas más combinaciones probás, más probable es que alguna salga bien por azar (por eso existe el contador de pruebas).

## 1. Datos
- **Fuente.** *MT5 directo*: lee el historial del terminal de FTMO (solo corriendo la app en tu PC con Windows y MT5 abierto). *CSV exportado*: archivos generados con `exportar_mt5.py`, uno por símbolo. *Sintéticos*: series inventadas para probar la interfaz; no dicen nada del mercado real.
- **Símbolos.** Podés elegir varios (metales, cripto, forex, índices). Con uno hacés el análisis detallado; con dos o más se habilita *Comparar símbolos*.
- **Temporalidad.** Tamaño de cada vela (M1, M5, H1...). Define cada cuánto se mira el cruce. Velas chicas dan más operaciones, más ruido y un spread que pesa más respecto del SL.
- **Desde / Hasta.** Período descargado. El terminal puede guardar un máximo de velas por gráfico, así que en M1 o M5 el historial disponible es más corto.
- **Remuestrear a.** Arma velas más grandes a partir de las descargadas (por ejemplo H4 desde H1). No puede armar velas más chicas.
- **Recortar período.** Limita el análisis a un tramo, sin volver a descargar.
- **Point (solo CSV).** Tamaño del punto del símbolo (0,01 en oro; 0,00001 en EURUSD). Sirve para pasar el spread de puntos a precio, y solo hace falta si el CSV no trae la columna `point`.
- **Tendencia / cantidad de series (sintéticos).** Con 0 la serie es azar puro: ninguna estrategia debería ganar ahí. Es una buena prueba de que el sistema no inventa ventaja.

## 2. Señal y gestión
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

## 3. Lotaje y dinero
- **Lotes.** Tamaño de la posición (1, 0,5, 0,1...). Tiene que respetar el mínimo y el paso del símbolo.
- **tick_size y tick_value.** Datos del contrato. Con MT5 directo se leen solos de cada símbolo. Con CSV o sintéticos los cargás a mano (en MT5: clic derecho en el símbolo → Especificación).
- **Comisión por lote.** Se resta de cada operación.
- **Capital de la cuenta y pérdida máxima (%).** Se usan solo en la conclusión final, para estimar la probabilidad de tocar el límite de pérdida de la cuenta (en FTMO, 10% del capital inicial).
- **Fórmula.** Dinero por cada 1,00 de precio = tick_value / tick_size × lotes. En oro con 0,10 lotes son 10 US$ por cada 1,00.
- **Qué cambia y qué no.** En SL por ATR o por porcentaje, el lote solo escala los resultados en dinero (R y % no cambian). Con SL en dólares, el lote **sí** cambia las operaciones, porque define qué tan lejos queda el stop en precio.

## 4. Costos
- **Spread.** *De la vela*: el spread de cierre de cada vela (en historial viejo suele venir en 0, lo que subestima el costo). *Ceros → mediana*: reemplaza los ceros por la mediana. *Valor fijo*: el que indiques. *Sin spread*: solo para comparar.
- **Cómo se aplica.** Los largos entran al precio de venta (ask). En los cortos, el SL y el TP se activan con el ask.
- **Costo extra por operación.** Unidades de precio que se restan a cada operación resuelta (slippage, comisión). En R equivale a costo / distancia del SL.

## 5. Filtros
Son independientes y se pueden combinar. Un cruce se toma solo si pasa todos los filtros activos.
- **SMA.** Compra solo si el cierre está por encima de la SMA y venta solo si está por debajo.
  - *Distancia mínima*: pide que el cierre esté a por lo menos N × ATR de la SMA, para evitar cruces pegados a ella (0 = sin condición).
  - *Pendiente a favor*: la SMA tiene que estar subiendo (en compras) o bajando (en ventas) respecto de hace N velas.
- **ADX.** Mide la **fuerza** de la tendencia, no su dirección.
  - *Mínimo*: descarta los cruces con ADX bajo (por ejemplo menor a 20, mercado sin tendencia).
  - *Máximo*: descarta tendencias ya muy extendidas (0 = sin límite).
  - *Creciente N velas*: pide que el ADX actual sea mayor que hace N velas.
- **ATR.** Mide la volatilidad.
  - *Mínimo / máximo (% del precio)*: ATR dividido el cierre, por cien.
  - *Modo relativo*: compara el ATR actual con su promedio de las últimas N velas. Con mínimo 0,8 descarta el mercado dormido y con máximo 2,0 descarta la volatilidad extrema.
- **Sesión.** Solo toma cruces dentro de Tokio (09-18), Londres (08-17) o Nueva York (08-17), en horario local, con el horario de verano de cada plaza. Se pueden elegir varias.
  - *Desfase del servidor*: diferencia entre la hora de las velas del broker y UTC en invierno (GMT+2 → 2). **Hay que medirlo con el mercado abierto**, porque si está mal las sesiones quedan corridas.
  - *El servidor cambia con EE.UU.*: casi todos los brokers pasan de GMT+2 a GMT+3 con el verano de EE.UU.
  - En BTC el filtro se desactiva solo (opera 24/7).

## 6. Control de sobreajuste
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
