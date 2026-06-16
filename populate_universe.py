import pandas as pd
import requests
import io
import os

os.makedirs('config', exist_ok=True)

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

print("Fetching S&P 500...")
try:
    response = requests.get('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies', headers=headers)
    tables = pd.read_html(io.StringIO(response.text))
    df_sp500 = tables[0]
    df_sp500 = df_sp500[['Symbol', 'Security', 'GICS Sector']]
    df_sp500.columns = ['Ticker', 'Company', 'Sector']
    df_sp500['Ticker'] = df_sp500['Ticker'].str.replace('.', '-', regex=False)
    df_sp500.to_csv('config/sp500.csv', index=False)
    print(f"Saved {len(df_sp500)} S&P 500 tickers.")
except Exception as e:
    print("Error fetching S&P 500:", e)

print("Fetching Nasdaq 100...")
try:
    response = requests.get('https://en.wikipedia.org/wiki/Nasdaq-100', headers=headers)
    tables = pd.read_html(io.StringIO(response.text))
    df_ndx = None
    for table in tables:
        cols = [str(c).lower() for c in table.columns]
        if any('ticker' in c or 'symbol' in c for c in cols):
            df_ndx = table
            break
    if df_ndx is not None:
        ticker_col = next(c for c in df_ndx.columns if 'ticker' in str(c).lower() or 'symbol' in str(c).lower())
        company_col = next((c for c in df_ndx.columns if 'company' in str(c).lower() or 'security' in str(c).lower() or 'name' in str(c).lower()), None)
        sector_col = next((c for c in df_ndx.columns if 'sector' in str(c).lower() or 'gics' in str(c).lower() or 'industry' in str(c).lower()), None)
        
        df_ndx_out = pd.DataFrame()
        df_ndx_out['Ticker'] = df_ndx[ticker_col].astype(str).str.replace('.', '-', regex=False)
        df_ndx_out['Company'] = df_ndx[company_col] if company_col else df_ndx_out['Ticker']
        df_ndx_out['Sector'] = df_ndx[sector_col] if sector_col else 'Information Technology'
        
        df_ndx_out.to_csv('config/nasdaq100.csv', index=False)
        print(f"Saved {len(df_ndx_out)} Nasdaq 100 tickers.")
    else:
        print("Could not find Nasdaq 100 table.")
except Exception as e:
    print("Error fetching Nasdaq 100:", e)

print("Creating Sector ETFs...")
etfs = [
    ('XLK', 'Technology Select Sector SPDR', 'Technology'),
    ('XLV', 'Health Care Select Sector SPDR', 'Health Care'),
    ('XLF', 'Financial Select Sector SPDR', 'Financials'),
    ('XLY', 'Consumer Discretionary Select Sector SPDR', 'Consumer Discretionary'),
    ('XLP', 'Consumer Staples Select Sector SPDR', 'Consumer Staples'),
    ('XLE', 'Energy Select Sector SPDR', 'Energy'),
    ('XLU', 'Utilities Select Sector SPDR', 'Utilities'),
    ('XLB', 'Materials Select Sector SPDR', 'Materials'),
    ('XLI', 'Industrial Select Sector SPDR', 'Industrials'),
    ('XLRE', 'Real Estate Select Sector SPDR', 'Real Estate'),
    ('XLC', 'Communication Services Select Sector SPDR', 'Communication Services'),
    ('SPY', 'SPDR S&P 500 ETF', 'Benchmark'),
    ('QQQ', 'Invesco QQQ Trust', 'Benchmark'),
    ('IWM', 'iShares Russell 2000 ETF', 'Benchmark')
]

df_etfs = pd.DataFrame(etfs, columns=['Ticker', 'Company', 'Sector'])
df_etfs.to_csv('config/sector_etfs.csv', index=False)
print(f"Saved {len(df_etfs)} ETFs.")

