# 📡 OpportunityRadar

OpportunityRadar is an end-of-day momentum screener and opportunity ranking engine built for quantitative swing traders and position traders. It focuses on identifying high-probability breakouts, established momentum leaders, and speculative reversals across the S&P 500, Nasdaq 100, and leading sector ETFs.

The project is split into two strict layers:
1. **The Engine** (`scanner_cron.py`): A heavy-duty offline calculation pipeline that downloads data, calculates indicators (Core 5), and generates an investment thesis for each opportunity.
2. **The Dashboard** (`app.py`): A hyper-fast, read-only Streamlit UI designed to be your 10-minute Morning Brief.

---

## 🎯 Features

*   **Core 5 Scoring Engine**: Analyzes Relative Strength (35%), Trend Alignment (20%), Relative Volume (20%), MACD Momentum (15%), and RSI Context (10%).
*   **Static Local Universe**: Uses static `.csv` files for deterministic universe selection, bypassing unreliability from web scraping.
*   **Sector Diversity Cap**: Limits the top ranking to a maximum of 3 stocks per sector to prevent overexposure to macro-trends.
*   **Automated Thesis Engine**: Translates technical momentum scores into readable Bull Cases, Bear Cases, and Key Catalysts.
*   **Instant UI**: The `app.py` dashboard reads from pre-calculated JSON output, allowing for zero-latency load times.
*   **Watchlist Intelligence**: Track your saved opportunities and their performance since the date they were added.
*   **Internal Validation**: Includes a dedicated `1_Validation.py` dashboard to audit score distributions and hard-filter pass rates.

---

## 📦 Installation

Ensure you have Python 3.10+ installed.

1.  Clone the repository:
    ```bash
    git clone https://github.com/yourusername/OpportunityRadar.git
    cd OpportunityRadar
    ```
2.  Create and activate a virtual environment (recommended):
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

---

## 🚀 First Run & Daily Workflow

### 1. Run the Scanner (Nightly / Early Morning)
The scanner handles all heavy lifting, downloading market data, and computing the rankings. This takes roughly 1–3 minutes.
```bash
python scanner_cron.py
```
*Note: This command should ideally be scheduled via cron (Linux/macOS) or Task Scheduler (Windows) to run after the daily market close.*

### 2. Open the Morning Brief (Daily)
Once the scanner finishes, launch the UI to review the top opportunities in under 10 minutes.
```bash
streamlit run app.py
```

### 3. (Optional) Run the Validation Audit
If you want to view internal engine metrics, histograms, and pre-diversity rankings:
```bash
streamlit run pages/1_Validation.py
```

---

## 📂 Project Structure

```text
OpportunityRadar/
├── app.py                      # Main UI Application (Morning Brief)
├── scanner_cron.py             # Backend Calculation Engine
├── universe_manager.py         # Static Universe Loading & Validation
├── requirements.txt            # Python Dependencies
├── README.md                   # Project Documentation
├── .gitignore                  # Git Ignore Rules
├── config/
│   ├── sp500.csv               # Static S&P 500 constituents
│   ├── nasdaq100.csv           # Static Nasdaq 100 constituents
│   └── sector_etfs.csv         # Core benchmark ETFs
├── data/
│   ├── daily_scan.json         # Core output from the scanner (read by app.py)
│   ├── validation_data.json    # Secondary output (read by 1_Validation.py)
│   └── watchlist.json          # Persisted user watchlist
├── pages/
│   └── 1_Validation.py         # Internal Validation Dashboard UI
└── utils/
    ├── chart_loader.py         # Plotly Candlestick generation logic
    └── ui_helpers.py           # Custom CSS and metric card components
```

---

## 🛠️ Troubleshooting

*   **Missing Data in UI (`daily_scan.json not found`)**: 
    You must execute `python scanner_cron.py` successfully at least once before starting the Streamlit app.
*   **`yfinance` Download Errors / Timeouts**: 
    `scanner_cron.py` uses batching and threading to mitigate Yahoo Finance rate limits. If a batch fails, it will gracefully log the error and continue. The stocks in the failed batch will simply be omitted from that day's scan.
*   **"No momentum leaders identified today"**:
    If the broader market enters a severe bear structure, the Hard Filter (Price < EMA50 < EMA200) will actively protect your capital by returning 0 candidates. This is an intended feature, not a bug.
