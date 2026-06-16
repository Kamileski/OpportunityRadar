import json
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SCAN_FILE = DATA_DIR / "daily_scan.json"
VALIDATION_FILE = DATA_DIR / "validation_data.json"

st.set_page_config(
    page_title="OpportunityRadar — Validation Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🔍 OpportunityRadar — Validation Dashboard")
st.markdown("Audit the scanner's internals and ensure it behaves as intended.")

# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(ttl=60)
def load_data():
    scan_data = {}
    val_data = {}
    
    if SCAN_FILE.exists():
        try:
            with open(SCAN_FILE, "r", encoding="utf-8") as f:
                scan_data = json.load(f)
        except Exception as e:
            st.error(f"Error loading daily_scan.json: {e}")

    if VALIDATION_FILE.exists():
        try:
            with open(VALIDATION_FILE, "r", encoding="utf-8") as f:
                val_data = json.load(f)
        except Exception as e:
            st.error(f"Error loading validation_data.json: {e}")
            
    return scan_data, val_data

scan_data, val_data = load_data()

if not scan_data or not val_data:
    st.warning("Data files not found. Run the scanner first: `python scanner_cron.py`")
    st.stop()

# ============================================================
# HELPER FOR HISTOGRAMS
# ============================================================
def create_histogram(data_series, bins=20):
    if not data_series:
        return pd.DataFrame()
    counts, edges = np.histogram(data_series, bins=bins)
    df = pd.DataFrame({
        "Range": [f"{edges[i]:.1f} - {edges[i+1]:.1f}" for i in range(len(counts))],
        "Count": counts
    })
    return df.set_index("Range")

# ============================================================
# DASHBOARD TABS
# ============================================================

tab_overview, tab_rankings, tab_distributions = st.tabs([
    "📊 Breadth & Hard Filter", 
    "🏆 Rankings & Diversity", 
    "📈 Score Distributions"
])

with tab_overview:
    st.header("1. Market Breadth & Hard Filter")
    
    # Breadth
    breadth = scan_data.get("market_overview", {}).get("market_breadth", {})
    total = breadth.get("total_stocks", 0)
    passed = scan_data.get("passed_filter", 0)
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total Universe (ex-ETFs)", total)
    with c2:
        st.metric("% Above EMA50", f"{breadth.get('pct_above_ema50', 0):.1f}%")
    with c3:
        st.metric("% Above EMA200", f"{breadth.get('pct_above_ema200', 0):.1f}%")
    with c4:
        st.metric("Passed Hard Filter", passed, f"{(passed/total*100) if total > 0 else 0:.1f}%")
        
    c5, c6 = st.columns(2)
    with c5:
        st.metric("New Highs (within 2%)", breadth.get("new_highs", 0))
    with c6:
        st.metric("New Lows (within 2%)", breadth.get("new_lows", 0))

with tab_rankings:
    st.header("2. Sector Diversity Enforcement")
    
    # Diversified vs Raw Top 20
    diversified = scan_data.get("main_ranking", [])
    raw = val_data.get("raw_top_20", [])
    
    # Sector distributions
    div_sectors = pd.Series([s.get("sector", "Unknown") for s in diversified]).value_counts()
    raw_sectors = pd.Series([s.get("sector", "Unknown") for s in raw]).value_counts()
    
    sc1, sc2 = st.columns(2)
    with sc1:
        st.subheader("Diversified Top 20 Sectors")
        st.bar_chart(div_sectors)
    with sc2:
        st.subheader("Raw Top 20 Sectors")
        st.bar_chart(raw_sectors)
        
    st.markdown("---")
    
    rc1, rc2 = st.columns(2)
    with rc1:
        st.subheader("Raw Top 20 Ranking")
        if raw:
            df_raw = pd.DataFrame(raw)
            st.dataframe(df_raw[["rank", "ticker", "sector", "score"]], use_container_width=True)
    with rc2:
        st.subheader("Diversified Top 20 Ranking")
        if diversified:
            df_div = pd.DataFrame(diversified)
            st.dataframe(df_div[["rank", "ticker", "sector", "score"]], use_container_width=True)

with tab_distributions:
    st.header("3. Mathematical Distributions")
    
    dc1, dc2 = st.columns(2)
    
    with dc1:
        st.subheader("Composite Score Distribution")
        st.markdown("Distribution of final scores for stocks passing the hard filter.")
        scores = val_data.get("all_scores", [])
        if scores:
            hist_scores = create_histogram(scores, bins=20)
            st.bar_chart(hist_scores)
            
    with dc2:
        st.subheader("Relative Strength Distribution")
        st.markdown("Distribution of the raw Composite Relative Strength before percentile ranking.")
        rs_vals = val_data.get("all_rs_values", [])
        if rs_vals:
            # Drop NaN or infinites if any slipped in
            rs_clean = [v for v in rs_vals if not np.isnan(v) and not np.isinf(v)]
            hist_rs = create_histogram(rs_clean, bins=30)
            st.bar_chart(hist_rs)

