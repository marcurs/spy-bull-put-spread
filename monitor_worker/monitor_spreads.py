import os
import json
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# 🔐 Cargar variables del entorno
load_dotenv()
TRADIER_API_TOKEN = os.getenv("TRADIER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

BASE_URL = "https://api.tradier.com/v1"
HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_TOKEN}",
    "Accept": "application/json"
}

#POSITIONS_FILE = "open_positions.json"
POSITIONS_FILE = os.path.join(os.path.dirname(__file__), "open_positions.json")

# ✉️ Función para enviar alerta por Telegram
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload)
        if response.status_code != 200:
            print(f"⚠️ Error enviando mensaje a Telegram: {response.text}")
    except Exception as e:
        print(f"⚠️ Excepción al enviar a Telegram: {e}")

# 📈 Consultar precio estimado del contrato usando midpoint (bid + ask)/2 de Tradier
def get_option_price(symbol, expiration, strike, option_type):
    url = f"{BASE_URL}/markets/options/chains"
    params = {
        "symbol": symbol,
        "expiration": expiration,
        "greeks": "false"
    }
    response = requests.get(url, headers=HEADERS, params=params)

    try:
        if response.status_code != 200:
            print(f"❌ Error {response.status_code} consultando {symbol}: {response.text}")
            return None

        data = response.json()
        options = data.get("options")
        if options is None:
            print(f"⚠️ Tradier devolvió 'options: null' para {symbol} {expiration}. Verifica que la fecha y strikes existan.")
            return None

        option_list = options.get("option", [])
    except Exception as e:
        print(f"❌ Error al procesar JSON de respuesta para {symbol} {strike}: {e}")
        print(f"Contenido crudo:\n{response.text}")
        return None

    for opt in option_list:
        if (
            opt["strike"] == strike
            and opt["option_type"] == option_type
            and opt["expiration_date"] == expiration
        ):
            bid = opt.get("bid", 0.0)
            ask = opt.get("ask", 0.0)
            # ⚠️ Esto es solo una estimación basada en precios publicados en Tradier, no en tu broker real
            return round((bid + ask) / 2, 2) if bid and ask else None

    return None

# 🔍 Monitorear y evaluar condiciones desde archivo local
def evaluar_posiciones():
    if not os.path.exists(POSITIONS_FILE):
        print("❌ No se encontró el archivo de posiciones abiertas.")
        return

    with open(POSITIONS_FILE, "r") as f:
        posiciones = json.load(f)

    if not posiciones:
        print("ℹ️ No hay posiciones abiertas para monitorear.")
        return

    for pos in posiciones:
        if pos.get("activo") is False:
            continue

        symbol = pos["symbol"]
        expiration = pos["expiration"]
        short_strike = pos["short_strike"]
        long_strike = pos["long_strike"]
        entry_price = pos["entry_price"]

        # ⚠️ Precios estimados únicamente para referencia
        short_price = get_option_price(symbol, expiration, short_strike, "put")
        long_price = get_option_price(symbol, expiration, long_strike, "put")

        if short_price is None or long_price is None:
            print(f"⚠️ No se pudo obtener precio para spread {symbol} {short_strike}/{long_strike}")
            continue

        current_value = round(short_price - long_price, 2)
        pnl_percent = round((entry_price - current_value) / entry_price * 100, 2)

        print(f"📊 Spread {short_strike}/{long_strike} → Entrada: {entry_price} | Valor estimado: {current_value} | P&L estimado: {pnl_percent}%")

        if pnl_percent <= -25:
            mensaje = (
                f"📢 <b>ALERTA DE CIERRE SPREAD {symbol}</b>\n"
                f"📅 Expira: {expiration}\n"
                f"📉 Short Put: {short_strike} | 📈 Long Put: {long_strike}\n"
                f"💰 Entrada: ${entry_price} | 🔴 Valor estimado: ${current_value}\n"
                f"📉 <b>Pérdida estimada: {pnl_percent}%</b>"
            )
            send_telegram(mensaje)

        elif pnl_percent >= 35:
            mensaje = (
                f"📢 <b>ALERTA DE CIERRE SPREAD {symbol}</b>\n"
                f"📅 Expira: {expiration}\n"
                f"📉 Short Put: {short_strike} | 📈 Long Put: {long_strike}\n"
                f"💰 Entrada: ${entry_price} | 🟢 Valor estimado: ${current_value}\n"
                f"📈 <b>Ganancia estimada: {pnl_percent}%</b>"
            )
            send_telegram(mensaje)

if __name__ == "__main__":
    evaluar_posiciones()
