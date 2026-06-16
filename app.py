import os
import json
import datetime
import pandas as pd
import streamlit as st
from pathlib import Path

from utils.chart_loader import load_candlestick_chart
from utils.ui_helpers import apply_custom_css, render_metric_card

# ============================================================
# CONFIGURATION & SETUP
# ============================================================

st.set_page_config(
    page_title="OpportunityRadar",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="expanded"
)

apply_custom_css()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SCAN_FILE = DATA_DIR / "daily_scan.json"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"

# ============================================================
# DATA LOADING
# ============================================================

@st.cache_data(ttl=60)
def load_scan_data():
    """Load pre-computed scan results. No calculations performed here."""
    if not SCAN_FILE.exists():
        return None
    try:
        with open(SCAN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading daily_scan.json: {e}")
        return None

def load_watchlist():
    """Load the user's watchlist."""
    if not WATCHLIST_FILE.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump({"watchlist": []}, f)
        return []
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("watchlist", [])
    except Exception:
        return []

def save_watchlist(watchlist):
    """Save the watchlist."""
    with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
        json.dump({"watchlist": watchlist}, f, indent=2)

def is_in_watchlist(ticker, watchlist):
    return any(item["ticker"] == ticker for item in watchlist)

# ============================================================
# MAIN APPLICATION
# ============================================================

def main():
    scan_data = load_scan_data()
    
    if scan_data is None:
        st.warning("⚠️ daily_scan.json not found. Please run `python scanner_cron.py` to generate the Morning Brief data.")
        st.stop()
        
    watchlist = load_watchlist()

    # --- Sidebar Navigation & Stats ---
    st.sidebar.title("📡 OpportunityRadar")
    st.sidebar.markdown("### Navigation")
    
    view = st.sidebar.radio("Go to:", [
        "🚀 Momentum Leaders",
        "🔪 Speculative Reversals",
        "⭐ Watchlist"
    ])
    
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Scan Details")
    
    scan_date = scan_data.get("scan_date", "Unknown")
    universe_size = scan_data.get("universe_size", 0)
    breadth = scan_data.get("market_overview", {}).get("market_breadth", {})
    pct_ema50 = breadth.get("pct_above_ema50", 0)
    
    st.sidebar.markdown(f"**Date:** {scan_date}")
    st.sidebar.markdown(f"**Universe:** {universe_size} scanned")
    st.sidebar.markdown(f"**Breadth:** {pct_ema50}% > EMA50")

    # --- Top Market Pulse Banner ---
    overview = scan_data.get("market_overview", {})
    spy_pct = overview.get("spy_change_pct", 0)
    qqq_pct = overview.get("qqq_change_pct", 0)
    vix = overview.get("vix", 0)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card("SPY", f"{spy_pct:+.2f}%", spy_pct >= 0)
    with col2:
        render_metric_card("QQQ", f"{qqq_pct:+.2f}%", qqq_pct >= 0)
    with col3:
        vix_pos = False if vix > 25 else (True if vix < 20 else None)
        render_metric_card("VIX", f"{vix:.2f}", vix_pos)
    with col4:
        breadth_pos = True if pct_ema50 >= 50 else False
        render_metric_card("Breadth > EMA50", f"{pct_ema50:.1f}%", breadth_pos)

    st.markdown("<br>", unsafe_allow_html=True)

    # ============================================================
    # VIEW: MOMENTUM LEADERS
    # ============================================================
    if view == "🚀 Momentum Leaders":
        st.markdown("## 🚀 Momentum Leaders")
        
        main_ranking = scan_data.get("main_ranking", [])
        if not main_ranking:
            st.info("No momentum leaders identified today.")
        else:
            # --- Quick Filters ---
            fc1, fc2, fc3 = st.columns(3)
            
            sectors = sorted(list(set(item["sector"] for item in main_ranking)))
            signals = sorted(list(set(item["signal_type"] for item in main_ranking)))
            
            with fc1:
                min_score = st.slider("Minimum Score", min_value=0, max_value=100, value=70)
            with fc2:
                sel_sector = st.selectbox("Sector", ["All"] + sectors)
            with fc3:
                sel_signal = st.selectbox("Signal Type", ["All"] + signals)

            # Apply filters
            filtered_data = [
                item for item in main_ranking
                if item["score"] >= min_score
                and (sel_sector == "All" or item["sector"] == sel_sector)
                and (sel_signal == "All" or item["signal_type"] == sel_signal)
            ]
            
            if not filtered_data:
                st.warning("No opportunities match your filters.")
            else:
                # --- Main Opportunity Table ---
                df = pd.DataFrame(filtered_data)
                
                # Format dataframe for display
                disp_df = df[["rank", "ticker", "company", "score", "delta_score", "signal_type", "sector", "rvol"]].copy()
                
                st.dataframe(
                    disp_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "rank": st.column_config.NumberColumn("Rank", width="small"),
                        "ticker": st.column_config.TextColumn("Ticker", width="small"),
                        "company": st.column_config.TextColumn("Company", width="medium"),
                        "score": st.column_config.NumberColumn("Score", format="%.1f"),
                        "delta_score": st.column_config.NumberColumn("Delta", format="%+.1f"),
                        "signal_type": st.column_config.TextColumn("Signal", width="medium"),
                        "sector": st.column_config.TextColumn("Sector", width="medium"),
                        "rvol": st.column_config.NumberColumn("RVOL", format="%.2fx"),
                    }
                )
                
                st.markdown("---")
                st.markdown("### 📖 Investment Thesis Engine")
                
                # --- Thesis Engine ---
                tickers = [item["ticker"] for item in filtered_data]
                sel_ticker = st.selectbox("Select Ticker to view Thesis and Chart:", tickers)
                
                selected_item = next((item for item in filtered_data if item["ticker"] == sel_ticker), None)
                
                if selected_item:
                    thesis = selected_item.get("thesis", {})
                    
                    tc1, tc2 = st.columns([1, 1])
                    with tc1:
                        st.markdown(f"""
                        <div class="thesis-card thesis-card-blue">
                            <div class="thesis-title">Market Narrative</div>
                            <div class="thesis-content">{thesis.get('market_narrative', 'N/A')}</div>
                        </div>
                        <div class="thesis-card thesis-card-green">
                            <div class="thesis-title">Bull Case</div>
                            <div class="thesis-content">{thesis.get('bull_case', 'N/A')}</div>
                        </div>
                        <div class="thesis-card thesis-card-red">
                            <div class="thesis-title">Bear Case</div>
                            <div class="thesis-content">{thesis.get('bear_case', 'N/A')}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                    with tc2:
                        st.markdown(f"""
                        <div class="thesis-card">
                            <div class="thesis-title">Key Catalyst</div>
                            <div class="thesis-content">{thesis.get('key_catalyst', 'N/A')}</div>
                        </div>
                        <div class="thesis-card thesis-card-red">
                            <div class="thesis-title">Invalidation Level (Stop)</div>
                            <div class="thesis-content" style="font-family:'JetBrains Mono',monospace; font-size:20px; font-weight:700; color:#F6465D;">
                                ${thesis.get('invalidation_level', 'N/A')}
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # Watchlist button
                        in_wl = is_in_watchlist(sel_ticker, watchlist)
                        if in_wl:
                            if st.button("⭐ Remove from Watchlist", key=f"rm_{sel_ticker}", use_container_width=True):
                                watchlist = [w for w in watchlist if w["ticker"] != sel_ticker]
                                save_watchlist(watchlist)
                                st.rerun()
                        else:
                            if st.button("⭐ Add to Watchlist", key=f"add_{sel_ticker}", type="primary", use_container_width=True):
                                watchlist.append({
                                    "ticker": sel_ticker,
                                    "company": selected_item.get("company", sel_ticker),
                                    "sector": selected_item.get("sector", "Unknown"),
                                    "date_added": datetime.date.today().isoformat(),
                                    "initial_price": selected_item.get("price", 0),
                                    "initial_score": selected_item.get("score", 0)
                                })
                                save_watchlist(watchlist)
                                st.rerun()

                    # --- Price Chart ---
                    st.markdown("#### 3-Month Price Action")
                    with st.spinner("Loading chart data..."):
                        fig = load_candlestick_chart(sel_ticker)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.error("Failed to load chart data for this ticker.")

    # ============================================================
    # VIEW: SPECULATIVE REVERSALS
    # ============================================================
    elif view == "🔪 Speculative Reversals":
        st.markdown("## 🔪 Speculative Reversals")
        st.markdown("High-risk setups looking for a bottom. Exercise strict risk management.")
        
        spec_ranking = scan_data.get("speculative_ranking", [])
        if not spec_ranking:
            st.info("No speculative candidates identified today.")
        else:
            df_spec = pd.DataFrame(spec_ranking)
            disp_spec = df_spec[["rank", "ticker", "company", "spec_score", "sector", "rsi", "drawdown_pct"]].copy()
            
            st.dataframe(
                disp_spec,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "rank": st.column_config.NumberColumn("Rank", width="small"),
                    "ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "company": st.column_config.TextColumn("Company", width="medium"),
                    "spec_score": st.column_config.NumberColumn("Spec Score", format="%.1f"),
                    "sector": st.column_config.TextColumn("Sector", width="medium"),
                    "rsi": st.column_config.NumberColumn("RSI", format="%.1f"),
                    "drawdown_pct": st.column_config.NumberColumn("Drawdown", format="%.1f%%"),
                }
            )
            
            st.markdown("---")
            sel_spec = st.selectbox("Select Speculative Ticker:", [item["ticker"] for item in spec_ranking])
            
            selected_spec = next((item for item in spec_ranking if item["ticker"] == sel_spec), None)
            if selected_spec:
                thesis = selected_spec.get("spec_thesis", {})
                
                sc1, sc2 = st.columns([1, 1])
                with sc1:
                    st.markdown(f"""
                    <div class="thesis-card thesis-card-blue">
                        <div class="thesis-title">Narrative</div>
                        <div class="thesis-content">{thesis.get('narrative', 'N/A')}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with sc2:
                    risk = thesis.get('risk_level', 'High')
                    risk_color = "#F6465D" if risk == "High" else "#FCD535"
                    
                    st.markdown(f"""
                    <div class="thesis-card">
                        <div class="thesis-title">Risk Level</div>
                        <div class="thesis-content" style="color:{risk_color}; font-weight:700;">{risk}</div>
                    </div>
                    <div class="thesis-card thesis-card-red">
                        <div class="thesis-title">Hard Stop Loss</div>
                        <div class="thesis-content" style="font-family:'JetBrains Mono',monospace; font-size:20px; font-weight:700; color:#F6465D;">
                            ${thesis.get('stop_loss', 'N/A')}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with st.spinner("Loading chart data..."):
                    fig = load_candlestick_chart(sel_spec)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)

    # ============================================================
    # VIEW: WATCHLIST
    # ============================================================
    elif view == "⭐ Watchlist":
        st.markdown("## ⭐ Watchlist Intelligence")
        
        if not watchlist:
            st.info("Your watchlist is empty. Add stocks from the Momentum Leaders tab.")
        else:
            # Reconstruct watchlist view by grabbing current prices/scores if available
            wl_display = []
            
            main_dict = {item["ticker"]: item for item in scan_data.get("main_ranking", [])}
            spec_dict = {item["ticker"]: item for item in scan_data.get("speculative_ranking", [])}
            
            for item in watchlist:
                ticker = item["ticker"]
                current_score = item["initial_score"]
                
                # Try to get latest score
                if ticker in main_dict:
                    current_score = main_dict[ticker]["score"]
                elif ticker in spec_dict:
                    current_score = spec_dict[ticker]["spec_score"]
                    
                ret_pct = 0.0
                # To calculate exact return we'd need current price. We can fetch it or use scan data.
                # Since we shouldn't do large operations, we'll use scan data if available.
                if ticker in main_dict:
                    cp = main_dict[ticker]["price"]
                    ret_pct = ((cp / item["initial_price"]) - 1.0) * 100
                elif ticker in spec_dict:
                    cp = spec_dict[ticker]["price"]
                    ret_pct = ((cp / item["initial_price"]) - 1.0) * 100
                    
                wl_display.append({
                    "ticker": ticker,
                    "company": item["company"],
                    "date_added": item["date_added"],
                    "initial_score": item["initial_score"],
                    "current_score": current_score,
                    "return_pct": ret_pct
                })
                
            df_wl = pd.DataFrame(wl_display)
            
            st.dataframe(
                df_wl,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "ticker": st.column_config.TextColumn("Ticker", width="small"),
                    "company": st.column_config.TextColumn("Company", width="medium"),
                    "date_added": st.column_config.TextColumn("Date Added"),
                    "initial_score": st.column_config.NumberColumn("Initial Score", format="%.1f"),
                    "current_score": st.column_config.NumberColumn("Current Score", format="%.1f"),
                    "return_pct": st.column_config.NumberColumn("Return Since Added", format="%+.2f%%"),
                }
            )
            
            st.markdown("---")
            sel_wl = st.selectbox("Select Watchlist Ticker to remove or view:", [w["ticker"] for w in watchlist])
            
            if sel_wl:
                if st.button("❌ Remove from Watchlist", use_container_width=True):
                    watchlist = [w for w in watchlist if w["ticker"] != sel_wl]
                    save_watchlist(watchlist)
                    st.rerun()
                    
                with st.spinner("Loading chart data..."):
                    fig = load_candlestick_chart(sel_wl)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)

if __name__ == "__main__":
    main()
