# Pendientes del proyecto

## Para desarrollar (nuevos)
1. ~~**Filtro de tendencia mayor.**~~ Hecho (dos filtros con SMA, temporalidad elegible). Queda probarlo en la app y en MetaEditor. Detalle original: Operar una señal de M5 solo si M15 y H1 (o H4) apuntan en el mismo sentido.
   - Definir: qué cuenta como tendencia (precio vs media o cruce de medias), qué temporalidades se pueden elegir, usar solo la última vela cerrada de cada temporalidad (sin mirar el futuro).
   - Backtest: armar M15/H1/H4 a partir de M5. Bot: leer esas velas con `iMA` o `CopyRates`.
   - Medirlo con la ablación: tiene que mejorar la expectativa, no solo el win rate.
2. **SL por cruce de ADX.** Salir de la operación cuando el ADX cruza un nivel.
   - Definir: qué cruce dispara la salida (ADX bajando de un nivel, cruce de +DI/−DI en contra, o las dos), si reemplaza al SL fijo o convive con él, y que salga al cierre de la vela del cruce (como la salida por señal).
   - Bot: calcular el ADX y chequear la condición en cada vela cerrada.
3. ~~**Breakeven.**~~ **HECHO (primera versión).** Activación en múltiplos de R, US$ fijos o % del camino al TP; el SL pasa a la entrada más un nivel en R o US$ (mínimo 0). Por tick en el bot; en el backtest, peor caso dentro de la vela. Cierre «BE» neutro para win rate, RR, rachas y pausas, pero su dinero entra a balance, equity y expectativa. Sección «Breakeven» en los resultados, paso «+ Breakeven» en la ablación y casilla opcional «el breakeven también activa la pausa tras pérdida» (apagada). Queda probarlo en la app y compilar el bot en MetaEditor.
   - Límite conocido: el anillo «% TP vs. equilibrio» y la probabilidad de ventaja de la conclusión cuentan solo TP y SL (suponen un pago fijo); con breakeven son una aproximación. Se podría recalcularlos.
4. ~~**Volume profile.**~~ **HECHO** (cerrado por el usuario). Perfil de N días CE(S)T, volumen de ticks, escalón editable, reglas A/B/C, también en el bot. Queda probar la compilación del bot en MetaEditor.
   *Ideas sueltas, sin fecha (no son pendientes):* toma de liquidez (barrida de máximos o mínimos con cierre de vuelta en 1 a 3 velas), nodos de bajo volumen como filtro y niveles del perfil como SL o TP.

5. ~~**Cierre parcial.**~~ **HECHO (primera versión).** Menú 3 (entre TP y Breakeven), motor, resultados («Cierre parcial», win rate por resultado) y bot MQL5 (por tick, variables globales, push). Queda probarlo en la app y compilar el bot en MetaEditor. No se hizo MFE / MAE (se descartó a pedido).

## Decisiones abiertas
- **Piso trailing después de un retiro.** Hoy se mantiene en el máximo anterior y, con retiros, la cuenta puede quedar sin margen para operar (ahora hay un aviso). Decidir si se recalcula el piso o se deja como está.

## Postergados por pedido
- Filtro de noticias (FX Street u otra fuente).
- Renombrar la carpeta del proyecto.
- Neutralizar los textos "FTMO".
- Problema del scroll de la barra lateral.
- Análisis de volatilidad por hora.
- Selector de perfiles de broker (Instant Funding, Goat, etc.). No se quiere por ahora.

## Para probar de tu lado (no se pudo en el entorno de desarrollo)
- Streamlit (parcial): casilla «Cierre parcial (opcional)» y su «⚙ Parámetros» en el menú 3, el texto con los lotes reales y la sección «Cierre parcial» de los resultados. MetaEditor: que compile el bot con `ManageParcial` y los inputs `InpPar…`; probar en el Probador que cobra el parcial una sola vez.
- Streamlit: menús 4 a 7 reordenados, acordeón de filtros (botón «⚙ Parámetros»), líneas divisorias en Gestión de riesgo, sección «Retiros de la cuenta» (monto ideal, retiro sugerido, aviso «sin margen»), gráfico de equity con la zona de out-of-sample, portada.
- MetaEditor: que el bot compile con la pausa tras ganancia/pérdida, el sentido, el retroceso y el vencimiento, el Volume Profile y el breakeven (modificar el SL de la posición abierta, distancia mínima del broker, cierre inmediato si el precio ya volvió al nivel).
- Streamlit (breakeven): el control en el menú 3, la casilla en el menú 9 y la sección «Breakeven» de los resultados.
- Streamlit (menú 3 en acordeón): los bloques Pullback, SL, TP y Breakeven con «⚙ Parámetros». Streamlit (menú 6): el recorte de horario por sesión (casilla, Desde/Hasta, equivalencia local, aviso si cae fuera de la sesión).
- Streamlit (portada): el cartel rojo de cambio de horario (marzo completo: Londres / NY; 20 al 31 de octubre: Londres; 1 al 7 de noviembre: NY). Hoy (8/11) no se ve; para verlo antes hay que probar con una fecha dentro de esas ventanas.
- Streamlit (fin de semana): casilla «Mantener posición el fin de semana» al final del menú 8, la hora opcional del viernes (14:00 ART por defecto) y la sección «Fin de semana» de los resultados.
- MetaEditor: que compile el bot con `ManageFinde`, `FindeBloqueaEntrada` y los inputs `InpFinde…` (el viernes 16:59 de Nueva York cierra posiciones y cancela pendientes).
- MetaEditor: que compile el bot con los inputs de recorte por sesión (`Inp...Corte`, `...CIni`, `...CFin`).
