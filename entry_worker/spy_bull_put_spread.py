import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os

# 🔐 Cargar API Key desde archivo .env
load_dotenv()
TRADIER_API_TOKEN = os.getenv('TRADIER_API_KEY')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

BASE_URL = "https://api.tradier.com/v1"
HEADERS = {
    'Authorization': f'Bearer {TRADIER_API_TOKEN}',
    'Accept': 'application/json'
}

# 🎯 Mostrar criterios configurados
def mostrar_criterios():
    print("\n🔎 CRITERIOS DE FILTRADO PARA SPY BULL PUT SPREAD")
    print("--------------------------------------------------")
    print("✔️  Subyacente: SPY")
    print("✔️  Tipo: Bull Put Spread (Short Put + Long Put)")
    print("✔️  Delta pierna vendida: entre -0.22 y -0.28")
    print("✔️  Ancho del spread: $5")
    print("✔️  Crédito mínimo recibido: $0.75")
    print("✔️  Días hasta vencimiento (DTE): entre 15 y 30 días")
    print("✔️  Mismo vencimiento para ambas patas")
    print("✔️  RSI diario entre 45 y 65")
    print("✔️  Precio > SMA 30 diario\n")

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

def get_option_expirations(symbol="SPY"):
    url = f"{BASE_URL}/markets/options/expirations"
    params = {"symbol": symbol, "includeAllRoots": "true", "strikes": "false"}
    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()
    return data['expirations']['date']

def filter_expirations(expirations, min_days=15, max_days=30):
    today = datetime.today().date()
    return [d for d in expirations if min_days <= (datetime.strptime(d, "%Y-%m-%d").date() - today).days <= max_days]

def get_option_chain(symbol, expiration):
    url = f"{BASE_URL}/markets/options/chains"
    params = {"symbol": symbol, "expiration": expiration, "greeks": "true"}
    response = requests.get(url, headers=HEADERS, params=params)
    data = response.json()
    return data['options']['option']

def build_spreads(options):
    puts = [opt for opt in options if opt['option_type'] == 'put' and opt['greeks']]
    spreads = []

    for short in puts:
        if abs(short['greeks']['delta']) < 0.28 and abs(short['greeks']['delta']) > 0.22:
            for long in puts:
                if long['strike'] == short['strike'] - 5 and long['expiration_date'] == short['expiration_date']:
                    credit = short['bid'] - long['ask']
                    if credit >= 0.75:
                        spreads.append({
                            "expiration": short["expiration_date"],
                            "short_strike": short["strike"],
                            "long_strike": long["strike"],
                            "credit": round(credit, 2),
                            "short_delta": round(short["greeks"]["delta"], 3),
                            "dte": (datetime.strptime(short["expiration_date"], "%Y-%m-%d").date() - datetime.today().date()).days
                        })
    return pd.DataFrame(spreads)

def vix_en_rango(min_vix=12, max_vix=25):
    print("🔍 Verificando nivel de VIX actual...")
    vix_url = f"{BASE_URL}/markets/quotes"
    vix_params = {"symbols": "VIX"}
    try:
        response = requests.get(vix_url, headers=HEADERS, params=vix_params)
        vix_data = response.json()
        vix = float(vix_data['quotes']['quote']['last'])
        print(f"📊 VIX actual: {vix:.2f}")
        return min_vix <= vix <= max_vix
    except Exception as e:
        print(f"⚠️ Error al obtener el VIX: {e}")
        return False  # Prevención por defecto


def cumple_condiciones_tecnicas():
    print("🔎 Evaluando condiciones técnicas (RSI y SMA)...")

    hist_url = f"{BASE_URL}/markets/history"
    hist_params = {"symbol": "SPY", "interval": "daily", "start": "2024-01-01"}
    hist_resp = requests.get(hist_url, headers=HEADERS, params=hist_params)
    daily_data = pd.DataFrame(hist_resp.json()['history']['day'])
    daily_data['close'] = daily_data['close'].astype(float)

    sma30 = daily_data['close'].rolling(window=30).mean().iloc[-1]
    precio_actual = daily_data['close'].iloc[-1]

    delta = daily_data['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi_actual = rsi.iloc[-1]

    print(f"📈 RSI diario actual: {rsi_actual:.2f}")
    print(f"📉 Precio actual: ${precio_actual:.2f}")
    print(f"📊 SMA 30 días: ${sma30:.2f}\n")

    return (45 < rsi_actual < 65) and (precio_actual > sma30)

def buscar_spreads_SPY():
    mostrar_criterios()
    expirations = get_option_expirations("SPY")
    filtradas = filter_expirations(expirations)

    all_spreads = []

    for fecha in filtradas:
        chain = get_option_chain("SPY", fecha)
        spreads_df = build_spreads(chain)
        if not spreads_df.empty:
            all_spreads.append(spreads_df)

    if all_spreads:
        resultado = pd.concat(all_spreads)
        resultado = resultado.sort_values(by="credit", ascending=False)
        print("📊 OPORTUNIDADES DETECTADAS:\n")
        print(resultado.to_string(index=False))

        # Enviar alerta por Telegram con resumen
        top = resultado.iloc[0]
        mensaje = (
            f"📢 <b>Oportunidad SPY Bull Put Spread</b>\n"
            f"📅 Expira: {top['expiration']}  ({top['dte']} DTE)\n"
            f"📉 Short Put: {top['short_strike']} | 📈 Long Put: {top['long_strike']}\n"
            f"💰 Crédito: ${top['credit']}  | 📊 Delta: {top['short_delta']}"
        )
        send_telegram(mensaje)
    else:
        print("❌ No se encontraron spreads que cumplan los criterios.")

if __name__ == "__main__":
    if vix_en_rango():
        if cumple_condiciones_tecnicas():
            buscar_spreads_SPY()
        else:
            print("❌ No se cumplen las condiciones técnicas (RSI > 65 y Precio < SMA 30).")
    else:
        print("❌ Nivel de VIX fuera de rango (> 12 y < 25). No se ejecutan spreads.")

