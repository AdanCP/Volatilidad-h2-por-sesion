# Pendientes del proyecto

## Para desarrollar (nuevos)
1. ~~**Filtro de tendencia mayor.**~~ Hecho (dos filtros con SMA, temporalidad elegible). Queda probarlo en la app y en MetaEditor. Detalle original: Operar una señal de M5 solo si M15 y H1 (o H4) apuntan en el mismo sentido.
   - Definir: qué cuenta como tendencia (precio vs media o cruce de medias), qué temporalidades se pueden elegir, usar solo la última vela cerrada de cada temporalidad (sin mirar el futuro).
   - Backtest: armar M15/H1/H4 a partir de M5. Bot: leer esas velas con `iMA` o `CopyRates`.
   - Medirlo con la ablación: tiene que mejorar la expectativa, no solo el win rate.
2. **SL por cruce de ADX.** Salir de la operación cuando el ADX cruza un nivel.
   - Definir: qué cruce dispara la salida (ADX bajando de un nivel, cruce de +DI/−DI en contra, o las dos), si reemplaza al SL fijo o convive con él, y que salga al cierre de la vela del cruce (como la salida por señal).
   - Bot: calcular el ADX y chequear la condición en cada vela cerrada.
3. **Breakeven.** Mover el SL al precio de entrada cuando la operación avanzó lo suficiente.
   - Definir: cuándo se activa (en R o % del camino al TP), a dónde se mueve (entrada exacta o con margen por spread y comisión) y cómo se simula si en una misma vela toca la activación y vuelve al SL (asumir lo peor).
   - Bot: modificar el SL de la posición abierta, respetando la distancia mínima del broker.
   - Medirlo con la ablación: corta ganadoras que habrían llegado al TP.
4. **Volume profile: HECHO (primera versión).** Falta toma de liquidez, nodos de bajo volumen y niveles como SL/TP (ideas de abajo). Versión hecha: perfil de N días CE(S)T, volumen de ticks, escalón editable, reglas A/B/C, también en el bot.
   *Idea original:* Perfil de volumen como filtro independiente, y más adelante toma de liquidez.
   - Perfil del día anterior (o desarrollado solo hasta la vela actual, para no mirar el futuro): POC, área de valor (VAH y VAL) y nodos de bajo volumen.
   - Usos posibles: comprar solo sobre el POC o el VAH, vender solo debajo; evitar operar dentro de un nodo de bajo volumen; niveles como SL o TP (más adelante).
   - Límites: el volumen de MT5 en oro es de ticks (varía entre brokers) y dentro de una vela M5 hay que suponer cómo se reparte el volumen.
   - Toma de liquidez (barrida de máximos o mínimos): se puede escribir como regla, pero hay que fijar qué nivel se barre (últimas N velas, pivote, sesión anterior) y que el cierre vuelva adentro en 1 a 3 velas. Solo ideas por ahora.

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
- Streamlit: menús 4 a 7 reordenados, acordeón de filtros (botón «⚙ Parámetros»), líneas divisorias en Gestión de riesgo, sección «Retiros de la cuenta» (monto ideal, retiro sugerido, aviso «sin margen»), gráfico de equity con la zona de out-of-sample, portada.
- MetaEditor: que el bot compile con la pausa tras ganancia/pérdida, el sentido, el retroceso y el vencimiento.
