import time
import datetime
import pandas as pd
import yfinance as yf
import requests

# --- CONFIGURATION ---
# Get these for free by creating a bot via "BotFather" on Telegram
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"
TICKERS = ["SPY", "QQQ"]

def send_telegram_message(message: str):
    """Sends a push notification directly to your phone via Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send message: {e}")

def get_intraday_data(ticker: str) -> pd.DataFrame:
    """Fetches intraday 5-minute bars and calculates VWAP and EMAs."""
    df = yf.download(ticker, period="5d", interval="5m", progress=False)
    if df.empty:
        return df
    
    # Flatten multi-index columns if present (yfinance quirk)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
        
    df.columns = [c.lower() for c in df.columns]
    
    # Calculate 9 EMA and 200 EMA
    df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema_200"] = df["close"].ewm(span=200, adjust=False).mean()
    
    # Calculate Session VWAP
    df["date"] = df.index.date
    typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
    df["cum_vp"] = (typical_price * df["volume"]).groupby(df["date"]).cumsum()
    df["cum_vol"] = df["volume"].groupby(df["date"]).cumsum()
    df["vwap"] = df["cum_vp"] / df["cum_vol"]
    
    return df

def analyze_trend(ticker: str, df: pd.DataFrame) -> str:
    """Evaluates the latest price action against your 0DTE debit spread strategy."""
    latest = df.iloc[-1]
    
    ema_9 = latest["ema_9"]
    ema_200 = latest["ema_200"]
    vwap = latest["vwap"]
    current_price = latest["close"]
    
    # Your Strategy Logic
    if ema_9 > vwap and ema_200 > vwap:
        return f"🟢 **{ticker} 0DTE CALL Debit Spread**\nPrice: ${current_price:.2f} | Both 9 EMA & 200 EMA are established ABOVE VWAP. Momentum is bullish."
    elif ema_9 < vwap and ema_200 < vwap:
        return f"🔴 **{ticker} 0DTE PUT Debit Spread**\nPrice: ${current_price:.2f} | Both 9 EMA & 200 EMA are established BELOW VWAP. Momentum is bearish."
    else:
        return f"⚪ **{ticker} No Clear Signal**\nPrice: ${current_price:.2f} | EMAs are crossing VWAP boundaries. Wait for structural alignment."

def run_screener():
    """Runs the analysis and sends the formatted alert."""
    messages = [f"🎯 **Hourly 0DTE Options Screener** ({datetime.datetime.now().strftime('%H:%M ET')})\n"]
    
    for ticker in TICKERS:
        df = get_intraday_data(ticker)
        if not df.empty:
            result = analyze_trend(ticker, df)
            messages.append(result)
            
    final_message = "\n\n".join(messages)
    print(final_message)
    send_telegram_message(final_message)

# --- MAIN SCHEDULER LOOP ---
if __name__ == "__main__":
   run_screener()