import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import pandas_ta as ta
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------
# App Configuration & CSS
# ---------------------------------------------------------
st.set_page_config(page_title="Multi-Day Spread Tracker", page_icon="🔭", layout="wide")

st.markdown("""
<style>
.ticker-card {
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 15px;
    text-align: center;
    background-color: rgba(255, 255, 255, 0.03);
    margin-bottom: 20px;
}
.status-bull { color: #00e676; font-weight: bold; font-size: 1.1rem; }
.status-bear { color: #ff5252; font-weight: bold; font-size: 1.1rem; }
.status-neutral { color: #b0bec5; font-weight: bold; font-size: 1.1rem; }
.action-text { font-size: 0.9rem; margin-top: 8px; color: #e0e0e0; }
</style>
""", unsafe_allow_html=True)

TICKERS = ["SPY", "QQQ", "NVDA", "GOOGL", "AAPL", "AMZN"]

# ---------------------------------------------------------
# Data Fetching & Indicator Logic
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_daily_data(ticker):
    """Fetches 1 year of daily data and applies the MultiIndex flattener."""
    df = yf.Ticker(ticker).history(period="1y", interval="1d")
    if df.empty: return df
    
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    return df

def generate_swing_signals(df: pd.DataFrame, adx_thresh: float = 20.0):
    """Computes daily thresholds for multi-day debit spreads."""
    df = df.copy()
    
    # 1. Moving Averages
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["sma_200"] = df["close"].rolling(window=200).mean()
    
    # 2. Volatility (ATR)
    df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    
    # 3. Momentum (RSI)
    df["rsi"] = ta.rsi(df["close"], length=14)
    
    # 4. Trend Strength (ADX & DMI)
    adx_df = ta.adx(df["high"], df["low"], df["close"], length=14)
    if adx_df is not None:
        df = pd.concat([df, adx_df], axis=1)
    else:
        df["ADX_14"], df["DMP_14"], df["DMN_14"] = 0.0, 0.0, 0.0

    # Bullish Call Spread Trigger
    call_trigger = (
        (df["close"] > df["ema_50"]) & 
        (df["ema_20"] > df["ema_50"]) & 
        (df["rsi"] >= 45) & (df["rsi"] <= 70) &
        (df["ADX_14"] >= adx_thresh) & 
        (df["DMP_14"] > df["DMN_14"])
    )
    
    # Bearish Put Spread Trigger
    put_trigger = (
        (df["close"] < df["ema_50"]) & 
        (df["ema_20"] < df["ema_50"]) & 
        (df["rsi"] >= 30) & (df["rsi"] <= 55) &
        (df["ADX_14"] >= adx_thresh) & 
        (df["DMN_14"] > df["DMP_14"])
    )
    
    df["signal"] = 0
    df.loc[call_trigger, "signal"] = 1
    df.loc[put_trigger, "signal"] = -1
    
    return df

def get_swing_recommendation(price, atr, signal):
    """Dynamically sizes the spread based on daily ATR."""
    spread_width = max(np.ceil(atr * 1.0), 1.0)
    
    if signal == 1:
        long_strike = np.floor(price)
        short_strike = long_strike + spread_width
        return {"status": "🟢 CALL SPREAD", "class": "status-bull", 
                "action": f"Buy ${long_strike:.0f}C <br> Sell ${short_strike:.0f}C"}
    elif signal == -1:
        long_strike = np.ceil(price)
        short_strike = long_strike - spread_width
        return {"status": "🔴 PUT SPREAD", "class": "status-bear", 
                "action": f"Buy ${long_strike:.0f}P <br> Sell ${short_strike:.0f}P"}
    else:
        return {"status": "⚪ MONITORING", "class": "status-neutral", 
                "action": "Awaiting clear<br>daily trend."}

# ---------------------------------------------------------
# Main UI App
# ---------------------------------------------------------
st.title("🔭 Multi-Day Debit Spread Screener")
st.caption("Target Expiration: 21 to 45 DTE. Scans Daily bars for EMA Alignment, RSI Momentum, and ADX Trend Strength.")

# Process all tickers
all_data = {}
for ticker in TICKERS:
    raw = fetch_daily_data(ticker)
    if not raw.empty:
        all_data[ticker] = generate_swing_signals(raw)

# --- THE AT-A-GLANCE BANNER ---
cols = st.columns(len(TICKERS))
for i, ticker in enumerate(TICKERS):
    if ticker in all_data:
        df = all_data[ticker]
        latest = df.iloc[-1]
        rec = get_swing_recommendation(latest["close"], latest["atr"], latest["signal"])
        
        with cols[i]:
            st.markdown(f"""
            <div class="ticker-card">
                <h3>{ticker}</h3>
                <h4>${latest['close']:.2f}</h4>
                <div class="{rec['class']}">{rec['status']}</div>
                <div class="action-text">{rec['action']}</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")
st.subheader("📊 Detailed Technical Charts")

# --- INDIVIDUAL TICKER TABS ---
tabs = st.tabs(TICKERS)
for i, ticker in enumerate(TICKERS):
    with tabs[i]:
        if ticker not in all_data:
            st.error(f"Data unavailable for {ticker}")
            continue
            
        df = all_data[ticker].tail(120) # Show last 6 months
        
        fig = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
            row_heights=[0.5, 0.25, 0.25],
            subplot_titles=("Daily Price & EMAs", "RSI (14)", "ADX & Trend Strength")
        )
        
        # Row 1: Price and MAs
        fig.add_trace(go.Candlestick(x=df.index, open=df["open"], high=df["high"], 
                                     low=df["low"], close=df["close"], name="Price"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_20"], line=dict(color="#29b6f6", width=1.5), name="20 EMA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["ema_50"], line=dict(color="#ab47bc", width=1.5), name="50 EMA"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["sma_200"], line=dict(color="#ffa726", width=2, dash="dot"), name="200 SMA"), row=1, col=1)
        
        # Row 2: RSI
        fig.add_trace(go.Scatter(x=df.index, y=df["rsi"], line=dict(color="#00e676", width=1.5), name="RSI"), row=2, col=1)
        fig.add_hline(y=70, line_dash="dot", line_color="#ff5252", row=2, col=1)
        fig.add_hline(y=30, line_dash="dot", line_color="#00e676", row=2, col=1)
        
        # Row 3: ADX & DMI
        fig.add_trace(go.Scatter(x=df.index, y=df["ADX_14"], line=dict(color="#FFD700", width=2), name="ADX"), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["DMP_14"], line=dict(color="#00e676", width=1), name="+DI"), row=3, col=1)
        fig.add_trace(go.Scatter(x=df.index, y=df["DMN_14"], line=dict(color="#ff5252", width=1), name="-DI"), row=3, col=1)
        fig.add_hline(y=20, line_dash="dot", line_color="#b0bec5", row=3, col=1, annotation_text="Trend Threshold (20)")
        
        fig.update_layout(height=800, template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=30, b=20))
        st.plotly_chart(fig, use_container_width=True)
