import os
import json
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

TRADIER_API_KEY = os.getenv("TRADIER_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

HEADERS = {
    "Authorization": f"Bearer {TRADIER_API_KEY}",
    "Accept": "application/json"
}

# Enviar mensaje a Telegram
def send_telegram(mensaje):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensaje,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Error enviando mensaje a Telegram: {e}")

# Obtener RSI y SMA desde datos históricos de SPY
def cumple_condiciones_tecnicas():
    print("🔎 Evaluando condiciones técnicas (RSI y SMA)...")
    try:
        r = requests.get("https://api.tradier.com/v1/markets/history",
                         headers=HEADERS,
                         params={"symbol": "SPY", "interval": "daily", "start": "2023-01-01"})
        r.raise_for_status()
        datos = r.json().get("history", {}).get("day", [])
        df = pd.DataFrame(datos)

        if df.empty:
            print("❌ No se encontraron datos de historial diario.")
            return False

        df["close"] = pd.to_numeric(df["close"])
        df["sma_30"] = df["close"].rolling(window=30).mean()
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(window=14).mean()
        avg_loss = loss.rolling(window=14).mean()
        rs = avg_gain / avg_loss
        df["rsi"] = 100 - (100 / (1 + rs))

        rsi_actual = df.iloc[-1]["rsi"]
        sma_actual = df.iloc[-1]["sma_30"]
        precio_actual = df.iloc[-1]["close"]

        print(f"📊 RSI: {rsi_actual:.2f} | SMA 30: {sma_actual:.2f} | Precio: {precio_actual:.2f}")

        return 45 < rsi_actual < 65 and precio_actual > sma_actual
    except Exception as e:
        print(f"❌ Error al evaluar condiciones técnicas: {e}")
        return False

# Obtener cadena de opciones de SPY
def get_option_chain():
    try:
        print("🔍 Obteniendo cadena de opciones...")
        r = requests.get("https://api.tradier.com/v1/markets/options/chains",
                         headers=HEADERS,
                         params={"symbol": "SPY", "expiration": "2025-04-25"})
        r.raise_for_status()
        data = r.json().get("options", {}).get("option", [])
        return pd.DataFrame(data)
    except Exception as e:
        print(f"❌ Error al obtener cadena de opciones: {e}")
        return pd.DataFrame()

# Filtrar y construir spreads válidos
def build_spreads(df):
    try:
        puts = df[(df["option_type"] == "put") & (df["expiration_date"] == "2025-04-25")]
        spreads = []
        for i, row in puts.iterrows():
            delta = row.get("greeks", {}).get("delta", -1)
            if not -0.28 <= delta <= -0.22:
                continue
            short_strike = row["strike"]
            long_strike = short_strike - 5
            long_leg = puts[puts["strike"] == long_strike]
            if long_leg.empty:
                continue
            credit = round((row["bid"] - long_leg.iloc[0]["ask"]), 2)
            if credit >= 0.75:
                spreads.append({
                    "short_strike": short_strike,
                    "long_strike": long_strike,
                    "credit": credit,
                    "delta": delta
                })
        return pd.DataFrame(spreads)
    except Exception as e:
        print(f"❌ Error al construir spreads: {e}")
        return pd.DataFrame()

if __name__ == "__main__":
    if cumple_condiciones_tecnicas():
        chain = get_option_chain()
        if chain.empty:
            print("⚠️ No se encontraron opciones válidas.")
        else:
            resultado = build_spreads(chain)
            if resultado.empty:
                print("⚠️ No se encontraron spreads que cumplan criterios.")
            else:
                resultado = resultado.sort_values(by="credit", ascending=False)
                print("✅ Spreads sugeridos:\n", resultado)
                top = resultado.iloc[0]
                mensaje = (
                    f"📈 <b>Oportunidad Bull Put Spread SPY</b>\n"
                    f"📉 Short: {top['short_strike']} | 📈 Long: {top['long_strike']}\n"
                    f"💰 Crédito: ${top['credit']} | Δ: {round(top['delta'], 2)}\n"
                    f"📅 Expira: 2025-04-25"
                )
                send_telegram(mensaje)
    else:
        print("❌ No se cumplen las condiciones técnicas.")