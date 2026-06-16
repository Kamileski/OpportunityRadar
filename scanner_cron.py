"""
OpportunityRadar — Daily Scanner Engine (scanner_cron.py)
=========================================================
Backend engine that downloads market data, calculates indicators,
scores every instrument, and produces a ranked JSON output.

Run daily after market close:
    python scanner_cron.py

Output: data/daily_scan.json

Architecture:
    Stage 0: Load universe (~600 tickers from S&P500 + Nasdaq100 + ETFs)
    Stage 1: Batch download OHLCV via yfinance
    Stage 2: Calculate indicators (EMA, RSI, MACD, ATR, RVOL, RS)
    Stage 3: Score with Core 5 engine (RS 35% + Trend 20% + Vol 20% + MACD 15% + RSI 10%)
    Stage 4: Rank, filter, classify signals
    Stage 5: Generate template-based theses
    Stage 6: Build JSON output
"""

import os
import sys
import json
import shutil
import logging
import warnings
import datetime
import numpy as np
import pandas as pd
import yfinance as yf
from pathlib import Path
import universe_manager

# Suppress noisy warnings from yfinance and pandas
warnings.filterwarnings("ignore")

# ============================================================
# CONFIGURATION
# ============================================================

# Paths
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_FILE = DATA_DIR / "daily_scan.json"
PREV_SCAN_FILE = DATA_DIR / "daily_scan_prev.json"

# Core 5 Scoring Weights (must sum to 1.0)
WEIGHT_RS = 0.35       # Relative Strength vs SPY
WEIGHT_TREND = 0.20    # Trend Alignment (EMA stack + ADX)
WEIGHT_VOLUME = 0.20   # Relative Volume
WEIGHT_MACD = 0.15     # MACD Momentum
WEIGHT_RSI = 0.10      # RSI Context

# Ranking constraints
MAIN_RANKING_SIZE = 20          # Max stocks in main ranking
SPECULATIVE_RANKING_SIZE = 10   # Max stocks in speculative ranking
MAX_PER_SECTOR = 3              # Sector diversity cap

# Download settings
BATCH_SIZE = 300                # Tickers per yfinance batch call
DOWNLOAD_PERIOD = "1y"          # Need 252 days for EMA200 + RS
MIN_HISTORY_DAYS = 200          # Minimum days of data required

# Sector ETFs — used for sector performance tracking
SECTOR_ETFS = {
    "XLK": "Technology",
    "XLV": "Health Care",
    "XLF": "Financials",
    "XLY": "Consumer Discretionary",
    "XLP": "Consumer Staples",
    "XLE": "Energy",
    "XLU": "Utilities",
    "XLB": "Materials",
    "XLI": "Industrials",
    "XLRE": "Real Estate",
    "XLC": "Communication Services",
}

# Benchmark ETFs
BENCHMARK_TICKERS = ["SPY", "QQQ", "IWM"]

# Fallback tickers if Wikipedia scraping fails — 80 large-cap names
FALLBACK_TICKERS = {
    "AAPL": ("Apple Inc.", "Information Technology"),
    "MSFT": ("Microsoft Corp.", "Information Technology"),
    "AMZN": ("Amazon.com Inc.", "Consumer Discretionary"),
    "NVDA": ("NVIDIA Corp.", "Information Technology"),
    "GOOGL": ("Alphabet Inc.", "Communication Services"),
    "META": ("Meta Platforms Inc.", "Communication Services"),
    "TSLA": ("Tesla Inc.", "Consumer Discretionary"),
    "BRK-B": ("Berkshire Hathaway", "Financials"),
    "UNH": ("UnitedHealth Group", "Health Care"),
    "JNJ": ("Johnson & Johnson", "Health Care"),
    "JPM": ("JPMorgan Chase", "Financials"),
    "V": ("Visa Inc.", "Financials"),
    "PG": ("Procter & Gamble", "Consumer Staples"),
    "MA": ("Mastercard Inc.", "Financials"),
    "HD": ("Home Depot Inc.", "Consumer Discretionary"),
    "AVGO": ("Broadcom Inc.", "Information Technology"),
    "CVX": ("Chevron Corp.", "Energy"),
    "MRK": ("Merck & Co.", "Health Care"),
    "LLY": ("Eli Lilly & Co.", "Health Care"),
    "ABBV": ("AbbVie Inc.", "Health Care"),
    "PEP": ("PepsiCo Inc.", "Consumer Staples"),
    "KO": ("Coca-Cola Co.", "Consumer Staples"),
    "COST": ("Costco Wholesale", "Consumer Staples"),
    "TMO": ("Thermo Fisher Scientific", "Health Care"),
    "WMT": ("Walmart Inc.", "Consumer Staples"),
    "MCD": ("McDonald's Corp.", "Consumer Discretionary"),
    "CSCO": ("Cisco Systems", "Information Technology"),
    "ACN": ("Accenture plc", "Information Technology"),
    "ABT": ("Abbott Laboratories", "Health Care"),
    "DHR": ("Danaher Corp.", "Health Care"),
    "CMCSA": ("Comcast Corp.", "Communication Services"),
    "VZ": ("Verizon Communications", "Communication Services"),
    "ADBE": ("Adobe Inc.", "Information Technology"),
    "CRM": ("Salesforce Inc.", "Information Technology"),
    "NKE": ("Nike Inc.", "Consumer Discretionary"),
    "NFLX": ("Netflix Inc.", "Communication Services"),
    "AMD": ("Advanced Micro Devices", "Information Technology"),
    "INTC": ("Intel Corp.", "Information Technology"),
    "TXN": ("Texas Instruments", "Information Technology"),
    "QCOM": ("Qualcomm Inc.", "Information Technology"),
    "INTU": ("Intuit Inc.", "Information Technology"),
    "HON": ("Honeywell International", "Industrials"),
    "LOW": ("Lowe's Companies", "Consumer Discretionary"),
    "UPS": ("United Parcel Service", "Industrials"),
    "CAT": ("Caterpillar Inc.", "Industrials"),
    "BA": ("Boeing Co.", "Industrials"),
    "GE": ("GE Aerospace", "Industrials"),
    "RTX": ("RTX Corp.", "Industrials"),
    "DE": ("Deere & Co.", "Industrials"),
    "GS": ("Goldman Sachs", "Financials"),
    "MS": ("Morgan Stanley", "Financials"),
    "BLK": ("BlackRock Inc.", "Financials"),
    "AXP": ("American Express", "Financials"),
    "SPGI": ("S&P Global Inc.", "Financials"),
    "AMAT": ("Applied Materials", "Information Technology"),
    "LRCX": ("Lam Research", "Information Technology"),
    "KLAC": ("KLA Corp.", "Information Technology"),
    "SNPS": ("Synopsys Inc.", "Information Technology"),
    "CDNS": ("Cadence Design Systems", "Information Technology"),
    "NOW": ("ServiceNow Inc.", "Information Technology"),
    "PANW": ("Palo Alto Networks", "Information Technology"),
    "ANET": ("Arista Networks", "Information Technology"),
    "FTNT": ("Fortinet Inc.", "Information Technology"),
    "XOM": ("Exxon Mobil", "Energy"),
    "COP": ("ConocoPhillips", "Energy"),
    "SLB": ("Schlumberger Ltd.", "Energy"),
    "EOG": ("EOG Resources", "Energy"),
    "NEE": ("NextEra Energy", "Utilities"),
    "DUK": ("Duke Energy", "Utilities"),
    "SO": ("Southern Co.", "Utilities"),
    "AMT": ("American Tower", "Real Estate"),
    "PLD": ("Prologis Inc.", "Real Estate"),
    "PSA": ("Public Storage", "Real Estate"),
    "LIN": ("Linde plc", "Materials"),
    "APD": ("Air Products & Chemicals", "Materials"),
    "SHW": ("Sherwin-Williams", "Materials"),
    "ECL": ("Ecolab Inc.", "Materials"),
    "FCX": ("Freeport-McMoRan", "Materials"),
    "PYPL": ("PayPal Holdings", "Financials"),
    "ENPH": ("Enphase Energy", "Information Technology"),
    "SEDG": ("SolarEdge Technologies", "Information Technology"),
}


# ============================================================
# SECTION 1: UNIVERSE LOADING
# ============================================================

def build_universe():
    """
    Build the complete instrument universe using the universe_manager.
    """
    # Use the external manager that loads from static CSVs
    universe = universe_manager.get_universe()
    
    # --- Benchmark ETFs ---
    # Ensure benchmarks are always present regardless of CSV contents
    benchmark_names = {"SPY": "SPDR S&P 500 ETF", "QQQ": "Invesco QQQ Trust", "IWM": "iShares Russell 2000 ETF"}
    for etf in benchmark_names.keys():
        if etf not in universe:
            universe[etf] = {
                "company": benchmark_names[etf],
                "sector": "Benchmark",
                "is_etf": True,
            }
            
    return universe


# ============================================================
# SECTION 2: DATA DOWNLOAD
# ============================================================

def download_ohlcv(tickers, period=DOWNLOAD_PERIOD):
    """
    Download OHLCV data for all tickers using batch yf.download().
    Splits into batches of BATCH_SIZE to avoid timeouts.
    Returns dict: {ticker: DataFrame with columns [Open, High, Low, Close, Volume]}
    """
    all_data = {}
    ticker_list = list(tickers)
    total_batches = (len(ticker_list) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(0, len(ticker_list), BATCH_SIZE):
        batch = ticker_list[batch_idx : batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1
        logging.info(f"  Downloading batch {batch_num}/{total_batches} ({len(batch)} tickers)...")

        try:
            data = yf.download(
                batch,
                period=period,
                interval="1d",
                auto_adjust=True,
                threads=True,
                progress=False,
            )

            if data is None or data.empty:
                logging.warning(f"  Batch {batch_num} returned empty data")
                continue

            # --- Handle single vs multi-ticker format ---
            if len(batch) == 1:
                # Single ticker: simple DataFrame with columns [Open, High, Low, Close, Volume]
                ticker = batch[0]
                df = data.dropna(how="all")
                if len(df) >= MIN_HISTORY_DAYS:
                    # Ensure columns are flat strings
                    df.columns = [str(c) if not isinstance(c, str) else c for c in df.columns]
                    all_data[ticker] = df
            else:
                # Multiple tickers: MultiIndex columns — (Field, Ticker)
                # Access: data['Close']['AAPL'] or data[('Close', 'AAPL')]
                for ticker in batch:
                    try:
                        # Build a clean per-ticker DataFrame
                        ticker_df = pd.DataFrame(index=data.index)
                        for field in ["Open", "High", "Low", "Close", "Volume"]:
                            try:
                                ticker_df[field] = data[(field, ticker)]
                            except KeyError:
                                # Try alternate access pattern for different yfinance versions
                                try:
                                    ticker_df[field] = data[field][ticker]
                                except (KeyError, TypeError):
                                    pass

                        ticker_df = ticker_df.dropna(how="all")

                        if len(ticker_df) >= MIN_HISTORY_DAYS and "Close" in ticker_df.columns:
                            all_data[ticker] = ticker_df
                    except Exception:
                        pass  # Skip problematic tickers silently

        except Exception as e:
            logging.error(f"  Batch {batch_num} download failed: {e}")

    return all_data


# ============================================================
# SECTION 3: INDICATOR CALCULATIONS
# ============================================================

def calc_ema(series, period):
    """Calculate Exponential Moving Average."""
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(series, period=14):
    """Calculate Relative Strength Index (Wilder's smoothing)."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def calc_macd(series, fast=12, slow=26, signal=9):
    """Calculate MACD Line, Signal Line, and Histogram."""
    ema_fast = calc_ema(series, fast)
    ema_slow = calc_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_atr(high, low, close, period=14):
    """Calculate Average True Range."""
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean()


def calculate_all_indicators(ohlcv, spy_close):
    """
    Calculate all required indicators for a single stock.
    Returns dict of latest indicator values, or None if insufficient data.

    Parameters:
        ohlcv: DataFrame with Open, High, Low, Close, Volume
        spy_close: Series of SPY close prices (for RS calculation)
    """
    try:
        close = ohlcv["Close"].astype(float)
        high = ohlcv["High"].astype(float)
        low = ohlcv["Low"].astype(float)
        volume = ohlcv["Volume"].astype(float)
    except (KeyError, ValueError):
        return None

    if len(close) < MIN_HISTORY_DAYS:
        return None

    # Drop any rows where close is NaN
    valid = close.dropna()
    if len(valid) < MIN_HISTORY_DAYS:
        return None

    # --- Moving Averages ---
    ema50 = calc_ema(close, 50)
    ema200 = calc_ema(close, 200)

    # --- RSI ---
    rsi = calc_rsi(close, 14)

    # --- MACD ---
    macd_line, macd_signal, macd_hist = calc_macd(close)

    # --- ATR ---
    atr = calc_atr(high, low, close, 14)

    # --- Relative Volume ---
    vol_sma20 = volume.rolling(20).mean()
    # Guard against division by zero
    safe_vol_sma = vol_sma20.replace(0, np.nan)
    rvol = volume / safe_vol_sma

    # --- EMA50 Slope (10-day % change) ---
    if len(ema50) > 10 and ema50.iloc[-10] != 0:
        ema50_slope = (ema50.iloc[-1] / ema50.iloc[-10] - 1.0) * 100.0
    else:
        ema50_slope = 0.0

    # --- Relative Strength vs SPY ---
    # Align dates between stock and SPY
    common_idx = close.index.intersection(spy_close.index)
    stock_aligned = close.reindex(common_idx).dropna()
    spy_aligned = spy_close.reindex(common_idx).dropna()
    # Re-intersect after dropna
    common_idx = stock_aligned.index.intersection(spy_aligned.index)
    stock_aligned = stock_aligned.reindex(common_idx)
    spy_aligned = spy_aligned.reindex(common_idx)

    rs_63 = 0.0
    rs_126 = 0.0

    if len(stock_aligned) >= 63 and stock_aligned.iloc[-63] > 0 and spy_aligned.iloc[-63] > 0:
        stock_ret_63 = (stock_aligned.iloc[-1] / stock_aligned.iloc[-63] - 1.0) * 100.0
        spy_ret_63 = (spy_aligned.iloc[-1] / spy_aligned.iloc[-63] - 1.0) * 100.0
        rs_63 = stock_ret_63 - spy_ret_63

    if len(stock_aligned) >= 126 and stock_aligned.iloc[-126] > 0 and spy_aligned.iloc[-126] > 0:
        stock_ret_126 = (stock_aligned.iloc[-1] / stock_aligned.iloc[-126] - 1.0) * 100.0
        spy_ret_126 = (spy_aligned.iloc[-1] / spy_aligned.iloc[-126] - 1.0) * 100.0
        rs_126 = stock_ret_126 - spy_ret_126

    # --- 52-Week High / Low ---
    h252 = high.tail(252)
    l252 = low.tail(252)
    high_52w = float(h252.max()) if len(h252) > 0 else float(close.iloc[-1])
    low_52w = float(l252.min()) if len(l252) > 0 else float(close.iloc[-1])

    # --- Daily change ---
    if len(close) >= 2 and close.iloc[-2] != 0:
        change_pct = (close.iloc[-1] / close.iloc[-2] - 1.0) * 100.0
    else:
        change_pct = 0.0

    # --- Assemble output ---
    # Guard against NaN in latest values
    def safe_float(val, default=0.0):
        try:
            v = float(val)
            return v if not np.isnan(v) and not np.isinf(v) else default
        except (ValueError, TypeError):
            return default

    return {
        "price": safe_float(close.iloc[-1]),
        "change_pct": safe_float(change_pct),
        "ema50": safe_float(ema50.iloc[-1]),
        "ema200": safe_float(ema200.iloc[-1]),
        "ema50_slope": safe_float(ema50_slope),
        "rsi": safe_float(rsi.iloc[-1], 50.0),
        "macd_line": safe_float(macd_line.iloc[-1]),
        "macd_signal": safe_float(macd_signal.iloc[-1]),
        "macd_histogram": safe_float(macd_hist.iloc[-1]),
        "macd_histogram_prev": safe_float(macd_hist.iloc[-2]) if len(macd_hist) >= 2 else 0.0,
        "atr": safe_float(atr.iloc[-1]),
        "rvol": safe_float(rvol.iloc[-1], 1.0),
        "rs_63": safe_float(rs_63),
        "rs_126": safe_float(rs_126),
        "high_52w": safe_float(high_52w),
        "low_52w": safe_float(low_52w),
        "volume": safe_float(volume.iloc[-1]),
        "avg_volume_20": safe_float(vol_sma20.iloc[-1]),
    }


# ============================================================
# SECTION 4: CORE 5 SCORING ENGINE
# ============================================================

def score_relative_strength(rs_63, rs_126, all_composite_rs):
    """
    Pillar 1: Relative Strength (35%)
    Percentile-ranked composite RS vs. entire universe.
    Higher percentile = stronger relative performer = higher score.
    """
    # Composite: weight recent performance more
    composite = 0.60 * rs_63 + 0.40 * rs_126

    if len(all_composite_rs) == 0:
        return 50.0

    # Percentile rank: what % of stocks have a LOWER RS?
    rank = sum(1 for v in all_composite_rs if v < composite)
    percentile = (rank / len(all_composite_rs)) * 100.0
    return round(min(100.0, max(0.0, percentile)), 1)


def score_trend_alignment(price, ema50, ema200, ema50_slope):
    """
    Pillar 2: Trend Alignment (20%)
    Evaluates EMA stack and slope for trend health.
    Perfect alignment (Price > EMA50 > EMA200, rising) = highest score.
    """
    if price <= 0 or ema50 <= 0 or ema200 <= 0:
        return 25.0

    if price > ema50 and ema50 > ema200:
        # Full bullish alignment
        if ema50_slope > 0.5:
            return 95.0       # Strong rising trend
        elif ema50_slope > 0.0:
            return 88.0       # Rising trend
        else:
            return 78.0       # Aligned but EMA50 flattening
    elif price > ema50 and ema50 <= ema200:
        # Above EMA50 but golden cross hasn't happened yet
        if ema50_slope > 0:
            return 62.0       # Early recovery
        else:
            return 52.0       # Weak recovery
    elif price <= ema50 and price > ema200:
        # Below EMA50 but above EMA200 — intermediate correction
        return 38.0
    else:
        # Below both EMAs — bearish structure
        return 12.0


def score_relative_volume(rvol):
    """
    Pillar 3: Relative Volume (20%)
    Higher volume = more institutional conviction.
    """
    if rvol >= 4.0:
        return 98.0
    elif rvol >= 3.0:
        return 93.0
    elif rvol >= 2.0:
        return 85.0
    elif rvol >= 1.5:
        return 75.0
    elif rvol >= 1.2:
        return 65.0
    elif rvol >= 1.0:
        return 55.0
    elif rvol >= 0.8:
        return 42.0
    elif rvol >= 0.5:
        return 30.0
    else:
        return 18.0


def score_macd_momentum(macd_line, histogram, histogram_prev):
    """
    Pillar 4: MACD Momentum (15%)
    Rewards acceleration — histogram increasing is the strongest signal.
    """
    hist_accel = histogram > histogram_prev

    if macd_line > 0 and histogram > 0 and hist_accel:
        return 93.0      # Bullish + accelerating = best
    elif macd_line > 0 and histogram > 0:
        return 76.0      # Bullish but decelerating
    elif macd_line <= 0 and histogram > 0 and hist_accel:
        return 72.0      # Bullish crossover from below zero (early signal)
    elif macd_line <= 0 and histogram > 0:
        return 60.0      # Improving from below
    elif macd_line > 0 and histogram <= 0:
        return 42.0      # Bearish crossover from above
    elif macd_line <= 0 and histogram <= 0 and hist_accel:
        return 35.0      # Bearish but improving
    else:
        return 18.0      # Bearish and decelerating


def score_rsi_context(rsi, trend_score):
    """
    Pillar 5: RSI Context (10%)
    Only meaningful when trend alignment is positive (score > 50).
    RSI 50-65 is the sweet spot in an uptrend.
    """
    # If no confirmed uptrend, RSI provides no useful signal
    if trend_score < 50:
        return 50.0

    # In confirmed uptrend context:
    if 50.0 <= rsi <= 65.0:
        return 92.0      # Sweet spot — strong but not extended
    elif 45.0 <= rsi < 50.0:
        return 72.0      # Mild pullback within trend
    elif 65.0 < rsi <= 72.0:
        return 78.0      # Strong momentum — still OK
    elif 72.0 < rsi <= 80.0:
        return 55.0      # Getting overbought
    elif rsi > 80.0:
        return 32.0      # Overbought — high risk of reversal
    elif 35.0 <= rsi < 45.0:
        return 48.0      # Losing momentum
    else:
        return 28.0      # Deep weakness in an uptrend = trend failure


def calculate_composite_score(indicators, all_composite_rs):
    """
    Calculate the final composite score using Core 5 weights.
    Returns dict with composite and individual pillar scores.
    """
    # Individual pillar scores
    rs_s = score_relative_strength(
        indicators["rs_63"], indicators["rs_126"], all_composite_rs
    )
    trend_s = score_trend_alignment(
        indicators["price"], indicators["ema50"],
        indicators["ema200"], indicators["ema50_slope"]
    )
    vol_s = score_relative_volume(indicators["rvol"])
    macd_s = score_macd_momentum(
        indicators["macd_line"], indicators["macd_histogram"],
        indicators["macd_histogram_prev"]
    )
    rsi_s = score_rsi_context(indicators["rsi"], trend_s)

    # Weighted composite (guaranteed 0-100 range)
    composite = (
        WEIGHT_RS * rs_s
        + WEIGHT_TREND * trend_s
        + WEIGHT_VOLUME * vol_s
        + WEIGHT_MACD * macd_s
        + WEIGHT_RSI * rsi_s
    )

    return {
        "composite": round(composite, 1),
        "rs_score": round(rs_s, 1),
        "trend_score": round(trend_s, 1),
        "volume_score": round(vol_s, 1),
        "macd_score": round(macd_s, 1),
        "rsi_score": round(rsi_s, 1),
    }


# ============================================================
# SECTION 5: HARD FILTER & SPECULATIVE FILTER
# ============================================================

def passes_hard_filter(ind):
    """
    Hard Filter for Main Ranking.
    EXCLUDE if Price < EMA50 AND EMA50 < EMA200 (full bearish structure).
    """
    return not (ind["price"] < ind["ema50"] and ind["ema50"] < ind["ema200"])


def is_speculative_candidate(ind):
    """
    Check if a stock qualifies for the Speculative Ranking.
    Criteria: deeply oversold, EMA50 reclaim attempt, or volume surge after drawdown.
    Must NOT pass the hard filter (mutual exclusion with main ranking).
    """
    rsi = ind["rsi"]
    price = ind["price"]
    ema50 = ind["ema50"]
    ema200 = ind["ema200"]
    rvol = ind["rvol"]
    high_52w = ind["high_52w"]

    # RSI deeply oversold
    if rsi < 30:
        return True

    # EMA50 reclaim while still below EMA200 (early recovery)
    if price > ema50 and ema50 < ema200 and ind.get("ema50_slope", 0) > 0:
        return True

    # Volume surge after significant drawdown
    drawdown = (price / high_52w - 1.0) * 100.0 if high_52w > 0 else 0
    if drawdown < -30 and rvol > 2.0:
        return True

    return False


def score_speculative(ind):
    """
    Score a speculative candidate (0-100).
    Separate scoring logic — not Core 5.
    """
    score = 40.0  # Base
    rsi = ind["rsi"]
    rvol = ind["rvol"]
    price = ind["price"]
    ema50 = ind["ema50"]
    high_52w = ind["high_52w"]
    drawdown = (price / high_52w - 1.0) * 100.0 if high_52w > 0 else 0

    # Oversold depth bonus (0-30)
    if rsi < 20:
        score += 30
    elif rsi < 25:
        score += 25
    elif rsi < 30:
        score += 20
    elif rsi < 35:
        score += 10

    # EMA50 reclaim bonus (0-20)
    if price > ema50:
        score += 20
    elif price > ema50 * 0.97:
        score += 10

    # Volume surge bonus (0-25)
    if rvol > 3.0:
        score += 25
    elif rvol > 2.0:
        score += 18
    elif rvol > 1.5:
        score += 12

    # Moderate drawdown is better than extreme (0-15)
    if -45 < drawdown < -20:
        score += 15      # Good reversal zone
    elif -55 < drawdown <= -45:
        score += 8       # Risky
    elif drawdown >= -20:
        score += 5       # Shallow drawdown

    return round(min(100.0, max(0.0, score)), 1)


# ============================================================
# SECTION 6: SIGNAL CLASSIFICATION
# ============================================================

def classify_signal(ind, scores):
    """
    Classify the primary signal type based on indicator and score patterns.
    Returns an emoji + label string.
    """
    rs_s = scores["rs_score"]
    trend_s = scores["trend_score"]
    vol_s = scores["volume_score"]
    macd_s = scores["macd_score"]
    rvol = ind["rvol"]
    price = ind["price"]
    high_52w = ind["high_52w"]

    proximity_52wh = (price / high_52w * 100.0) if high_52w > 0 else 0

    # --- Priority-ordered classification ---

    # New High Leader: at or near 52-week high with volume
    if proximity_52wh >= 97 and vol_s >= 60:
        return "🏔️ New High Leader"

    # Momentum Breakout: strong volume + strong MACD acceleration
    if vol_s >= 80 and macd_s >= 70 and rvol >= 1.5:
        return "🚀 Momentum Breakout"

    # Sector Leader: top RS + confirmed trend
    if rs_s >= 85 and trend_s >= 78:
        return "👑 Sector Leader"

    # Volume Surge: exceptional volume
    if rvol >= 2.5 and ind["change_pct"] > 1.0:
        return "💥 Volume Surge"

    # Early Trend: trend forming but not yet strong
    if 55 <= trend_s < 78 and macd_s >= 55:
        return "🌱 Early Trend"

    # Strong Momentum: good composite
    if scores["composite"] >= 70:
        return "📈 Strong Momentum"

    # Default
    return "📊 Improving"


# ============================================================
# SECTION 7: THESIS ENGINE (Deterministic Templates)
# ============================================================

def generate_thesis(ticker, company, sector, ind, scores):
    """
    Generate a structured investment thesis using deterministic templates.
    No LLM, no NLP — pure rule-based text generation.
    """
    price = ind["price"]
    ema50 = ind["ema50"]
    ema200 = ind["ema200"]
    atr = ind["atr"]
    rsi = ind["rsi"]
    rs_63 = ind["rs_63"]
    rvol = ind["rvol"]
    macd_hist = ind["macd_histogram"]
    macd_hist_prev = ind["macd_histogram_prev"]
    ema50_slope = ind["ema50_slope"]
    change_pct = ind["change_pct"]

    # --- Invalidation Level ---
    # EMA50 minus 1× ATR (a standard risk management level)
    invalidation = round(ema50 - atr, 2) if atr > 0 else round(ema50 * 0.95, 2)

    # ========================================
    # MARKET NARRATIVE (Why Now?)
    # ========================================
    # RS description
    if scores["rs_score"] >= 80:
        rs_phrase = f"significantly outperforming SPY by {abs(rs_63):.1f}% over the last quarter"
    elif scores["rs_score"] >= 60:
        rs_phrase = f"outperforming SPY by {abs(rs_63):.1f}% over the last quarter"
    elif rs_63 > 0:
        rs_phrase = f"modestly outperforming SPY by {rs_63:.1f}% over the last quarter"
    else:
        rs_phrase = f"tracking near SPY with {rs_63:+.1f}% relative performance over the last quarter"

    # Volume description
    if rvol >= 2.0:
        vol_phrase = (
            f"Volume is {rvol:.1f}× above its 20-day average, "
            f"indicating significant institutional interest."
        )
    elif rvol >= 1.3:
        vol_phrase = (
            f"Volume is running {rvol:.1f}× above average, "
            f"suggesting growing market interest."
        )
    else:
        vol_phrase = "Volume is near average levels."

    market_narrative = (
        f"{ticker} is {rs_phrase} with strong momentum "
        f"in the {sector} sector. {vol_phrase}"
    )

    # ========================================
    # BULL CASE
    # ========================================
    if scores["trend_score"] >= 78:
        trend_phrase = (
            f"Trend structure is fully aligned — price (${price:.2f}) is above both "
            f"the 50-day EMA (${ema50:.2f}) and 200-day EMA (${ema200:.2f}), "
            f"both of which are rising."
        )
    elif scores["trend_score"] >= 55:
        trend_phrase = (
            f"Price (${price:.2f}) is above the 50-day EMA (${ema50:.2f}). "
            f"Trend is developing but not yet fully confirmed above the 200-day EMA."
        )
    else:
        trend_phrase = (
            f"Price at ${price:.2f} is working to establish a new trend. "
            f"EMA50 at ${ema50:.2f}."
        )

    if macd_hist > 0 and macd_hist > macd_hist_prev:
        macd_phrase = "MACD histogram is positive and accelerating, confirming bullish momentum."
    elif macd_hist > 0:
        macd_phrase = "MACD histogram is positive, supporting the current move."
    elif macd_hist > macd_hist_prev:
        macd_phrase = "MACD is showing early signs of momentum improvement."
    else:
        macd_phrase = "MACD is yet to fully confirm the trend."

    bull_case = (
        f"{trend_phrase} {macd_phrase} "
        f"Trend remains intact while price holds above ${ema50:.2f}."
    )

    # ========================================
    # BEAR CASE
    # ========================================
    if rsi > 80:
        rsi_warning = (
            f"RSI at {rsi:.0f} is overbought — expect a corrective pullback "
            f"before any continuation."
        )
    elif rsi > 70:
        rsi_warning = (
            f"RSI at {rsi:.0f} is approaching overbought territory, "
            f"increasing the risk of a short-term pullback."
        )
    else:
        rsi_warning = f"RSI at {rsi:.0f} is in a healthy range."

    bear_case = (
        f"Invalidation occurs on a daily close below ${invalidation:.2f} "
        f"(EMA50 minus 1× ATR). {rsi_warning} "
        f"A break below EMA50 (${ema50:.2f}) would signal trend deterioration."
    )

    # ========================================
    # KEY CATALYST
    # ========================================
    if rvol >= 2.0 and change_pct > 2.0:
        catalyst = (
            f"Significant volume surge ({rvol:.1f}× average) accompanied by a "
            f"{change_pct:.1f}% price move suggests institutional accumulation "
            f"or a catalyst-driven event."
        )
    elif rvol >= 2.0 and change_pct > 0:
        catalyst = (
            f"Volume surge ({rvol:.1f}× average) on a positive session "
            f"indicates growing institutional interest."
        )
    elif scores["rs_score"] >= 85:
        catalyst = (
            f"Persistent relative strength (top {100 - scores['rs_score']:.0f}th percentile) "
            f"indicates sustained institutional demand and sector leadership."
        )
    elif macd_hist > 0 and macd_hist_prev <= 0:
        catalyst = (
            "Fresh MACD bullish crossover signals a momentum shift. "
            "Watch for follow-through volume confirmation."
        )
    elif ema50_slope > 0.5:
        catalyst = (
            f"Rising 50-day EMA (slope: +{ema50_slope:.2f}%) confirms "
            f"a strengthening medium-term trend. Institutional buyers are defending this level."
        )
    else:
        catalyst = (
            f"Composite score driven by confluence of {sector} sector strength "
            f"and improving technical momentum across multiple timeframes."
        )

    return {
        "market_narrative": market_narrative,
        "bull_case": bull_case,
        "bear_case": bear_case,
        "key_catalyst": catalyst,
        "invalidation_level": invalidation,
    }


def generate_speculative_thesis(ticker, ind):
    """
    Generate a short thesis for speculative (reversal) candidates.
    """
    price = ind["price"]
    ema50 = ind["ema50"]
    atr = ind["atr"]
    rsi = ind["rsi"]
    rvol = ind["rvol"]
    high_52w = ind["high_52w"]
    drawdown = (price / high_52w - 1.0) * 100.0 if high_52w > 0 else 0

    # Stop loss: price minus 1.5× ATR
    stop_loss = round(price - 1.5 * atr, 2) if atr > 0 else round(price * 0.92, 2)

    # Oversold description
    if rsi < 25:
        oversold_phrase = f"RSI at {rsi:.0f} indicates extremely oversold conditions"
    elif rsi < 30:
        oversold_phrase = f"RSI at {rsi:.0f} indicates deeply oversold conditions"
    else:
        oversold_phrase = f"RSI at {rsi:.0f} suggests potential bottoming"

    # Volume context
    if rvol > 2.0:
        vol_phrase = "Volume surge suggests potential capitulation and reversal."
    elif rvol > 1.3:
        vol_phrase = "Above-average volume supports potential reversal interest."
    else:
        vol_phrase = "Monitoring for reversal confirmation with volume."

    narrative = (
        f"{ticker} is down {drawdown:.0f}% from its 52-week high of ${high_52w:.2f}. "
        f"{oversold_phrase}. {vol_phrase}"
    )

    risk_level = "High" if drawdown < -40 else "Medium"

    return {
        "narrative": narrative,
        "risk_level": risk_level,
        "stop_loss": stop_loss,
    }


# ============================================================
# SECTION 8: MARKET OVERVIEW
# ============================================================

def build_market_overview(all_indicators, universe):
    """
    Calculate market-level metrics for the dashboard KPI cards.
    """
    # --- Benchmark changes ---
    spy_chg = all_indicators.get("SPY", {}).get("change_pct", 0)
    qqq_chg = all_indicators.get("QQQ", {}).get("change_pct", 0)
    iwm_chg = all_indicators.get("IWM", {}).get("change_pct", 0)

    # --- VIX ---
    vix_val = 0.0
    try:
        vix_data = yf.download("^VIX", period="5d", progress=False)
        if vix_data is not None and len(vix_data) > 0:
            # Handle both single-level and multi-level columns
            if isinstance(vix_data.columns, pd.MultiIndex):
                vix_val = float(vix_data["Close"].iloc[-1].iloc[0])
            else:
                vix_val = float(vix_data["Close"].iloc[-1])
    except Exception:
        pass

    # --- Market Breadth (calculated from universe, excluding ETFs) ---
    total_stocks = 0
    above_ema50 = 0
    above_ema200 = 0
    new_highs = 0
    new_lows = 0

    for ticker, ind in all_indicators.items():
        if universe.get(ticker, {}).get("is_etf", False):
            continue
        if universe.get(ticker, {}).get("sector", "") == "Benchmark":
            continue

        total_stocks += 1
        if ind["price"] > ind["ema50"]:
            above_ema50 += 1
        if ind["price"] > ind["ema200"]:
            above_ema200 += 1
        if ind["high_52w"] > 0 and ind["price"] >= ind["high_52w"] * 0.98:
            new_highs += 1
        if ind["low_52w"] > 0 and ind["price"] <= ind["low_52w"] * 1.02:
            new_lows += 1

    pct_above_ema50 = round((above_ema50 / total_stocks) * 100, 1) if total_stocks > 0 else 0
    pct_above_ema200 = round((above_ema200 / total_stocks) * 100, 1) if total_stocks > 0 else 0

    # --- Sector Performance ---
    sector_perf = []
    for etf, sector_name in SECTOR_ETFS.items():
        if etf in all_indicators:
            sector_perf.append({
                "name": sector_name,
                "etf": etf,
                "change_pct": round(all_indicators[etf].get("change_pct", 0), 2),
            })
    sector_perf.sort(key=lambda x: x["change_pct"], reverse=True)

    top_sector = sector_perf[0] if sector_perf else {"name": "Unknown", "etf": "", "change_pct": 0}

    return {
        "spy_change_pct": round(spy_chg, 2),
        "qqq_change_pct": round(qqq_chg, 2),
        "iwm_change_pct": round(iwm_chg, 2),
        "vix": round(vix_val, 1),
        "market_breadth": {
            "pct_above_ema50": pct_above_ema50,
            "pct_above_ema200": pct_above_ema200,
            "new_highs": new_highs,
            "new_lows": new_lows,
            "total_stocks": total_stocks,
        },
        "top_sector": {
            "name": top_sector["name"],
            "etf": top_sector["etf"],
            "change_pct": top_sector["change_pct"],
        },
        "sectors": sector_perf,
    }


# ============================================================
# SECTION 9: PREVIOUS SCORE LOADING (for Delta calculation)
# ============================================================

def load_previous_scores():
    """
    Load previous day's composite scores from the last scan file.
    Returns dict: {ticker: previous_score}
    """
    # Try the explicit previous file first, then the current output file
    for path in [PREV_SCAN_FILE, OUTPUT_FILE]:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    prev_data = json.load(f)
                return {
                    item["ticker"]: item["score"]
                    for item in prev_data.get("main_ranking", [])
                }
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return {}


# ============================================================
# SECTION 10: MAIN PIPELINE
# ============================================================

def run_pipeline():
    """
    Execute the full scanning pipeline.

    Stage 0: Build universe
    Stage 1: Download OHLCV data
    Stage 2: Calculate indicators
    Stage 3: Score all stocks (Core 5)
    Stage 4: Rank, filter, classify
    Stage 5: Generate theses
    Stage 6: Build and save output JSON
    """
    start_time = datetime.datetime.now()

    logging.info("=" * 65)
    logging.info("  OpportunityRadar — Daily Scanner")
    logging.info(f"  Started: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logging.info("=" * 65)

    # ─────────────────────────────────────────────
    # STAGE 0: Build Universe
    # ─────────────────────────────────────────────
    logging.info("\n[Stage 0] Building instrument universe...")
    universe = build_universe()
    logging.info(f"  Universe size: {len(universe)} instruments")

    # ─────────────────────────────────────────────
    # STAGE 1: Download OHLCV Data
    # ─────────────────────────────────────────────
    logging.info("\n[Stage 1] Downloading market data (this may take 2-4 minutes)...")
    ohlcv_data = download_ohlcv(list(universe.keys()))
    logging.info(f"  Successfully downloaded: {len(ohlcv_data)} instruments")

    if "SPY" not in ohlcv_data:
        logging.error("CRITICAL: SPY data unavailable. Cannot calculate RS. Aborting.")
        sys.exit(1)

    spy_close = ohlcv_data["SPY"]["Close"].astype(float)

    # ─────────────────────────────────────────────
    # STAGE 2: Calculate Indicators
    # ─────────────────────────────────────────────
    logging.info("\n[Stage 2] Calculating indicators...")
    all_indicators = {}
    failed = 0

    for ticker in ohlcv_data:
        try:
            result = calculate_all_indicators(ohlcv_data[ticker], spy_close)
            if result is not None:
                all_indicators[ticker] = result
            else:
                failed += 1
        except Exception as e:
            failed += 1
            logging.debug(f"  Indicator calc failed for {ticker}: {e}")

    logging.info(f"  Indicators computed: {len(all_indicators)} (skipped: {failed})")

    # ─────────────────────────────────────────────
    # STAGE 3: Score All Stocks
    # ─────────────────────────────────────────────
    logging.info("\n[Stage 3] Scoring with Core 5 engine...")

    # First pass: collect all RS composite values for percentile ranking
    all_composite_rs = []
    for ticker, ind in all_indicators.items():
        if not universe.get(ticker, {}).get("is_etf", False):
            all_composite_rs.append(0.60 * ind["rs_63"] + 0.40 * ind["rs_126"])

    # Load previous scores for delta calculation
    prev_scores = load_previous_scores()

    # Second pass: calculate composite scores + apply filters
    main_candidates = []     # Stocks that pass the hard filter
    spec_candidates = []     # Speculative reversal candidates

    for ticker, ind in all_indicators.items():
        # Skip ETFs and benchmarks from stock rankings
        info = universe.get(ticker, {})
        if info.get("is_etf", False) or info.get("sector") == "Benchmark":
            continue

        scores = calculate_composite_score(ind, all_composite_rs)

        if passes_hard_filter(ind):
            main_candidates.append({
                "ticker": ticker,
                "ind": ind,
                "scores": scores,
            })
        elif is_speculative_candidate(ind):
            # Only stocks that FAIL the hard filter can be speculative
            spec_candidates.append({
                "ticker": ticker,
                "ind": ind,
                "spec_score": score_speculative(ind),
            })

    logging.info(f"  Main candidates (passed filter): {len(main_candidates)}")
    logging.info(f"  Speculative candidates: {len(spec_candidates)}")

    # ─────────────────────────────────────────────
    # STAGE 4: Rank & Apply Diversity Constraint
    # ─────────────────────────────────────────────
    logging.info("\n[Stage 4] Ranking and applying sector diversity...")

    # Sort main by composite score descending
    main_candidates.sort(key=lambda x: x["scores"]["composite"], reverse=True)

    # Capture raw top 20 before sector diversity
    raw_top_main = main_candidates[:MAIN_RANKING_SIZE]

    # Apply sector diversity cap (max 3 per sector)
    top_main = []
    sector_count = {}
    for candidate in main_candidates:
        sector = universe.get(candidate["ticker"], {}).get("sector", "Unknown")
        current = sector_count.get(sector, 0)
        if current < MAX_PER_SECTOR:
            top_main.append(candidate)
            sector_count[sector] = current + 1
        if len(top_main) >= MAIN_RANKING_SIZE:
            break

    # Sort speculative by score descending
    spec_candidates.sort(key=lambda x: x["spec_score"], reverse=True)
    top_spec = spec_candidates[:SPECULATIVE_RANKING_SIZE]

    logging.info(f"  Main Top {len(top_main)}, Speculative Top {len(top_spec)}")

    # ─────────────────────────────────────────────
    # STAGE 5: Generate Theses & Build Output
    # ─────────────────────────────────────────────
    logging.info("\n[Stage 5] Generating theses and building output...")

    # --- Main Ranking Output ---
    main_ranking_output = []
    for rank, cand in enumerate(top_main, 1):
        ticker = cand["ticker"]
        ind = cand["ind"]
        scores = cand["scores"]
        info = universe.get(ticker, {})

        thesis = generate_thesis(
            ticker, info.get("company", ticker),
            info.get("sector", "Unknown"), ind, scores,
        )
        signal = classify_signal(ind, scores)

        prev_score = prev_scores.get(ticker, scores["composite"])
        delta = round(scores["composite"] - prev_score, 1)

        main_ranking_output.append({
            "rank": rank,
            "ticker": ticker,
            "company": info.get("company", ticker),
            "sector": info.get("sector", "Unknown"),
            "score": scores["composite"],
            "prev_score": round(prev_score, 1),
            "delta_score": delta,
            "signal_type": signal,
            "signal_age_days": 1,
            "price": round(ind["price"], 2),
            "change_pct": round(ind["change_pct"], 2),
            "rs_score": scores["rs_score"],
            "trend_score": scores["trend_score"],
            "volume_score": scores["volume_score"],
            "macd_score": scores["macd_score"],
            "rsi_score": scores["rsi_score"],
            "rvol": round(ind["rvol"], 2),
            "rsi": round(ind["rsi"], 1),
            "ema50": round(ind["ema50"], 2),
            "ema200": round(ind["ema200"], 2),
            "atr": round(ind["atr"], 2),
            "thesis": thesis,
        })

    # --- Speculative Ranking Output ---
    spec_ranking_output = []
    for rank, cand in enumerate(top_spec, 1):
        ticker = cand["ticker"]
        ind = cand["ind"]
        info = universe.get(ticker, {})

        thesis = generate_speculative_thesis(ticker, ind)

        spec_ranking_output.append({
            "rank": rank,
            "ticker": ticker,
            "company": info.get("company", ticker),
            "sector": info.get("sector", "Unknown"),
            "spec_score": cand["spec_score"],
            "price": round(ind["price"], 2),
            "change_pct": round(ind["change_pct"], 2),
            "rsi": round(ind["rsi"], 1),
            "rvol": round(ind["rvol"], 2),
            "ema50": round(ind["ema50"], 2),
            "high_52w": round(ind["high_52w"], 2),
            "drawdown_pct": round(
                (ind["price"] / ind["high_52w"] - 1.0) * 100.0 if ind["high_52w"] > 0 else 0, 1
            ),
            "spec_thesis": thesis,
        })

    # ─────────────────────────────────────────────
    # STAGE 6: Market Overview & Save Output
    # ─────────────────────────────────────────────
    logging.info("\n[Stage 6] Building market overview and saving results...")

    market_overview = build_market_overview(all_indicators, universe)

    # Count new/improved signals
    new_signals = sum(
        1 for s in main_ranking_output
        if s["delta_score"] > 3.0 or s["ticker"] not in prev_scores
    )

    # --- Assemble final output ---
    scan_result = {
        "scan_date": datetime.date.today().isoformat(),
        "scan_timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "universe_size": len(all_indicators),
        "passed_filter": len(main_candidates),
        "new_signals_count": new_signals,
        "market_overview": market_overview,
        "main_ranking": main_ranking_output,
        "speculative_ranking": spec_ranking_output,
    }

    # --- Save previous scan for delta tracking ---
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_FILE.exists():
        try:
            shutil.copy2(OUTPUT_FILE, PREV_SCAN_FILE)
        except Exception:
            pass

    # --- Write output JSON ---
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(scan_result, f, indent=2, ensure_ascii=False, default=str)
        logging.info(f"  Results saved to: {OUTPUT_FILE}")
        
        # --- Assemble and Write Validation JSON ---
        validation_data = {
            "all_scores": [cand["scores"]["composite"] for cand in main_candidates],
            "all_rs_values": all_composite_rs,
            "raw_top_20": [
                {
                    "rank": i + 1,
                    "ticker": cand["ticker"],
                    "company": universe.get(cand["ticker"], {}).get("company", cand["ticker"]),
                    "sector": universe.get(cand["ticker"], {}).get("sector", "Unknown"),
                    "score": cand["scores"]["composite"]
                }
                for i, cand in enumerate(raw_top_main)
            ]
        }
        VALIDATION_FILE = DATA_DIR / "validation_data.json"
        with open(VALIDATION_FILE, "w", encoding="utf-8") as f:
            json.dump(validation_data, f, indent=2, ensure_ascii=False, default=str)
        logging.info(f"  Validation data saved to: {VALIDATION_FILE}")
            
    except Exception as e:
        logging.error(f"  Failed to save results: {e}")
        sys.exit(1)

    # ─────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────
    elapsed = (datetime.datetime.now() - start_time).total_seconds()
    logging.info("\n" + "=" * 65)
    logging.info("  SCAN COMPLETE")
    logging.info(f"  Duration: {elapsed:.0f} seconds")
    logging.info(f"  Universe scanned: {len(all_indicators)} instruments")
    logging.info(f"  Main Ranking: {len(main_ranking_output)} stocks")
    logging.info(f"  Speculative Ranking: {len(spec_ranking_output)} stocks")
    logging.info(f"  New/Improved signals: {new_signals}")
    if main_ranking_output:
        top = main_ranking_output[0]
        logging.info(f"  #1 Opportunity: {top['ticker']} — Score: {top['score']}")
    logging.info("=" * 65)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    try:
        run_pipeline()
    except KeyboardInterrupt:
        logging.info("\nScan interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logging.error(f"\nFatal error: {e}")
        logging.error("The scanner encountered an unexpected error. Check your network connection and try again.")
        sys.exit(1)
