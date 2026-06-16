import yfinance as yf
import plotly.graph_objects as go
import streamlit as st
import datetime
import pandas as pd

@st.cache_data(ttl=3600)
def load_candlestick_chart(ticker):
    """Load 3 months of OHLCV data and return a Plotly candlestick figure."""
    try:
        end_date = datetime.date.today()
        start_date = end_date - datetime.timedelta(days=90)
        
        df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        
        if df.empty:
            return None
            
        # Handle MultiIndex columns if yfinance returns them
        if isinstance(df.columns, pd.MultiIndex):
            # Extract the level 0 strings (Open, High, Low, Close, Volume)
            df.columns = df.columns.get_level_values(0)

        fig = go.Figure(data=[go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name=ticker
        )])

        fig.update_layout(
            title=f"{ticker} - 3 Month Price Action",
            yaxis_title="Price ($)",
            xaxis_title="Date",
            template="plotly_dark",
            margin=dict(l=20, r=20, t=40, b=20),
            height=400,
            xaxis_rangeslider_visible=False
        )
        
        return fig
    except Exception as e:
        return None
