"""Alertas por WhatsApp: cruce EMA13/EMA34 en M15 de GC=F con filtro SMA50.

Uso:
  python bot_alertas.py --test        Envía un mensaje de prueba.
  python bot_alertas.py --historial   Muestra los últimos cruces (no envía nada).
  python bot_alertas.py --una-vez     Revisa una vez y avisa si hay cruce nuevo.
  python bot_alertas.py --loop        Revisa cada 15 minutos sin parar.

Variables de entorno necesarias para enviar mensajes (TextMeBot):
  WHATSAPP_PHONE    número destino con código de país, sin + ni espacios
                    (Argentina celular: 549 + código de área + número)
  TEXTMEBOT_APIKEY  la apikey de tu cuenta en https://textmebot.com
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

# ---------------------------------------------------------------- Configuración
TICKER = "GC=F"
INTERVALO_MIN = 15
EMA_RAPIDA = 13
EMA_LENTA = 34
SMA_FILTRO = 50

# Cuántas velas hacia atrás se revisan en cada corrida. Sirve para no perder
# un cruce si una corrida se atrasa (GitHub Actions puede demorar bastante).
LOOKBACK_BARRAS = 8

# Posición "ideal" de la SMA50 respecto del punto de cruce de las EMAs:
#   True  -> COMPRA: cruce alcista con la SMA50 POR DEBAJO del cruce
#            VENTA:  cruce bajista con la SMA50 POR ENCIMA del cruce
#   False -> al revés (COMPRA con la SMA50 por encima, VENTA por debajo)
IDEAL_COMPRA_SMA_DEBAJO = True

TEXTMEBOT_URL = "https://api.textmebot.com/send.php"
TZ_MENSAJE = "America/Argentina/Buenos_Aires"
ARCHIVO_ESTADO = Path(__file__).with_name("estado_alertas.json")
# -----------------------------------------------------------------------------


@dataclass
class Cruce:
    inicio_vela: pd.Timestamp
    direccion: str  # "alcista" | "bajista"
    cierre: float
    nivel: float  # punto aproximado del cruce: promedio de ambas EMAs
    sma: float
    sma_arriba: bool
    tipo: str  # "COMPRA" | "VENTA" | "ANALIZAR"


def descargar_m15() -> pd.DataFrame:
    """Velas de 15m de GC=F, sin la vela que todavía se está formando."""
    df = yf.download(
        TICKER, period="10d", interval="15m", progress=False, auto_adjust=False
    )
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    df = df.dropna(subset=["Close"])
    ahora = pd.Timestamp.now(tz="UTC")
    return df[df.index + pd.Timedelta(minutes=INTERVALO_MIN) <= ahora]


def detectar_cruces(
    df: pd.DataFrame, ultimas_barras: Optional[int] = None
) -> "list[Cruce]":
    """Cruces EMA rápida / EMA lenta, clasificados según la SMA50."""
    df = df.copy()
    df["ema_rapida"] = df["Close"].ewm(span=EMA_RAPIDA, adjust=False).mean()
    df["ema_lenta"] = df["Close"].ewm(span=EMA_LENTA, adjust=False).mean()
    df["sma"] = df["Close"].rolling(SMA_FILTRO).mean()

    dif = df["ema_rapida"] - df["ema_lenta"]
    previo = dif.shift(1)
    alcista = (previo <= 0) & (dif > 0)
    bajista = (previo >= 0) & (dif < 0)

    marcadas = df[(alcista | bajista) & df["sma"].notna()]
    if ultimas_barras:
        corte = df.index[max(len(df) - ultimas_barras, 0)]
        marcadas = marcadas[marcadas.index >= corte]

    cruces = []
    for ts, fila in marcadas.iterrows():
        direccion = "alcista" if bool(alcista.loc[ts]) else "bajista"
        nivel = float((fila["ema_rapida"] + fila["ema_lenta"]) / 2)
        sma_arriba = bool(fila["sma"] > nivel)
        if direccion == "alcista":
            ideal = (not sma_arriba) if IDEAL_COMPRA_SMA_DEBAJO else sma_arriba
            tipo = "COMPRA" if ideal else "ANALIZAR"
        else:
            ideal = sma_arriba if IDEAL_COMPRA_SMA_DEBAJO else (not sma_arriba)
            tipo = "VENTA" if ideal else "ANALIZAR"
        cruces.append(
            Cruce(
                inicio_vela=ts,
                direccion=direccion,
                cierre=float(fila["Close"]),
                nivel=nivel,
                sma=float(fila["sma"]),
                sma_arriba=sma_arriba,
                tipo=tipo,
            )
        )
    return cruces


def _hora_cierre(c: Cruce) -> pd.Timestamp:
    return (c.inicio_vela + pd.Timedelta(minutes=INTERVALO_MIN)).tz_convert(
        TZ_MENSAJE
    )


def _hora_apertura(c: Cruce) -> pd.Timestamp:
    return c.inicio_vela.tz_convert(TZ_MENSAJE)


def armar_mensaje(c: Cruce) -> str:
    apertura = _hora_apertura(c)
    cierre = _hora_cierre(c)
    posicion = "por encima" if c.sma_arriba else "por debajo"

    if c.tipo == "COMPRA":
        titulo = "🟢 COMPRA"
    elif c.tipo == "VENTA":
        titulo = "🔴 VENTA"
    else:
        titulo = "🟡 CRUCE A ANALIZAR"

    lineas = [
        f"{titulo} - {TICKER} M15",
        f"Cruce {c.direccion} EMA{EMA_RAPIDA}/EMA{EMA_LENTA}",
        f"Cierre de la vela: {c.cierre:.1f}",
        f"SMA{SMA_FILTRO}: {c.sma:.1f} ({posicion} del cruce)",
        f"Vela de las {apertura:%H:%M} (cerró {cierre:%H:%M}) del"
        f" {apertura:%d/%m}, hora Argentina",
    ]
    if c.tipo == "ANALIZAR":
        if c.direccion == "alcista":
            ideal = "por debajo" if IDEAL_COMPRA_SMA_DEBAJO else "por encima"
            para = "compra"
        else:
            ideal = "por encima" if IDEAL_COMPRA_SMA_DEBAJO else "por debajo"
            para = "venta"
        lineas.insert(
            1,
            f"La SMA{SMA_FILTRO} no está en la posición ideal para"
            f" {para} (tendría que estar {ideal} del cruce).",
        )
    return "\n".join(lineas)


def enviar_whatsapp(texto: str) -> bool:
    """Envía el mensaje con la API de TextMeBot."""
    telefono = "".join(
        ch for ch in os.environ.get("WHATSAPP_PHONE", "") if ch.isdigit()
    )
    apikey = os.environ.get("TEXTMEBOT_APIKEY", "").strip()
    if not telefono or not apikey:
        print("Faltan WHATSAPP_PHONE y/o TEXTMEBOT_APIKEY.")
        return False
    try:
        r = requests.get(
            TEXTMEBOT_URL,
            params={"recipient": telefono, "apikey": apikey, "text": texto},
            timeout=30,
        )
    except requests.RequestException as e:
        print(f"Error de red al enviar: {e}")
        return False
    respuesta = r.text.strip().replace("\n", " ")[:150]
    print(f"TextMeBot respondió {r.status_code}: {respuesta}")
    malo = any(
        p in respuesta.lower()
        for p in ("error", "invalid", "fail", "incorrect", "expired")
    )
    return r.status_code == 200 and not malo


def cargar_estado() -> dict:
    try:
        return json.loads(ARCHIVO_ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def guardar_estado(estado: dict) -> None:
    ARCHIVO_ESTADO.write_text(
        json.dumps(estado, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def revisar_y_avisar() -> None:
    df = descargar_m15()
    if df.empty or len(df) < SMA_FILTRO + 5:
        print("Sin datos suficientes (mercado cerrado o Yahoo no respondió).")
        return

    estado = cargar_estado()
    ultima = estado.get("ultima_barra")
    # Primera corrida (sin estado): solo se miran las últimas 2 velas,
    # para no mandar un aluvión de cruces viejos.
    ultima_ts = pd.Timestamp(ultima) if ultima else df.index[-3]

    nuevos = [
        c
        for c in detectar_cruces(df, LOOKBACK_BARRAS)
        if c.inicio_vela > ultima_ts
    ]
    for c in nuevos:
        if not enviar_whatsapp(armar_mensaje(c)):
            print("No se pudo enviar; se reintenta en la próxima corrida.")
            guardar_estado(estado)
            return
        estado["ultima_barra"] = c.inicio_vela.tz_convert("UTC").isoformat()
        print(f"Aviso enviado: {c.tipo} / cruce {c.direccion}")

    if not nuevos:
        print("Sin cruces nuevos.")
    estado["ultima_barra"] = df.index[-1].tz_convert("UTC").isoformat()
    guardar_estado(estado)


def mostrar_historial(n: int = 15) -> None:
    df = descargar_m15()
    if df.empty:
        print("Sin datos.")
        return
    cruces = detectar_cruces(df)[-n:]
    print(f"Últimos {len(cruces)} cruces (hora de APERTURA de la vela, hora Argentina):")
    for c in cruces:
        h = _hora_apertura(c)
        sma = "arriba" if c.sma_arriba else "abajo"
        print(
            f"{h:%d/%m %H:%M} | cruce {c.direccion:7} | SMA50 {sma:6}"
            f" | {c.tipo}"
        )


def esperar_proximo_cuarto() -> None:
    ahora = datetime.now(timezone.utc)
    proximo = (
        ahora + timedelta(minutes=INTERVALO_MIN - ahora.minute % INTERVALO_MIN)
    ).replace(second=0, microsecond=0) + timedelta(seconds=45)
    time.sleep(max((proximo - ahora).total_seconds(), 1))


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--test", action="store_true")
    g.add_argument("--historial", action="store_true")
    g.add_argument("--una-vez", action="store_true")
    g.add_argument("--loop", action="store_true")
    args = p.parse_args()

    if args.test:
        ok = enviar_whatsapp(f"Prueba: el bot de alertas {TICKER} funciona.")
        print("Enviado." if ok else "No se pudo enviar.")
    elif args.historial:
        mostrar_historial()
    elif args.una_vez:
        revisar_y_avisar()
    elif args.loop:
        print("Bot en marcha. Ctrl+C para detener.")
        while True:
            try:
                revisar_y_avisar()
            except Exception as e:  # el bot no se cae por un error puntual
                print(f"Error en la revisión: {e}")
            esperar_proximo_cuarto()


if __name__ == "__main__":
    main()
