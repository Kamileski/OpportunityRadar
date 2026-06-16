import os
import csv
import logging
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"

def load_csv(filename):
    """Load a CSV file and return a list of dicts."""
    filepath = CONFIG_DIR / filename
    if not filepath.exists():
        logging.warning(f"  Missing file: {filepath}")
        return []
    
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if 'Ticker' in row and row['Ticker'].strip():
                    results.append({
                        'Ticker': row['Ticker'].strip(),
                        'Company': row.get('Company', row['Ticker']).strip(),
                        'Sector': row.get('Sector', 'Unknown').strip()
                    })
    except Exception as e:
        logging.error(f"  Failed to read {filename}: {e}")
    return results

def get_universe():
    """
    Build the complete instrument universe from static CSV files.
    Validates, removes duplicates, and logs a validation report.
    Returns dict: {ticker: {'company': str, 'sector': str, 'is_etf': bool}}
    """
    universe = {}
    
    # Load raw data
    sp500_data = load_csv('sp500.csv')
    ndx_data = load_csv('nasdaq100.csv')
    etf_data = load_csv('sector_etfs.csv')
    
    total_raw = len(sp500_data) + len(ndx_data) + len(etf_data)
    duplicates = 0
    
    # S&P 500
    sp500_count = 0
    for row in sp500_data:
        ticker = row['Ticker']
        if ticker not in universe:
            universe[ticker] = {
                'company': row['Company'],
                'sector': row['Sector'],
                'is_etf': False
            }
            sp500_count += 1
        else:
            duplicates += 1
            
    # Nasdaq 100
    ndx_count = 0
    for row in ndx_data:
        ticker = row['Ticker']
        if ticker not in universe:
            universe[ticker] = {
                'company': row['Company'],
                'sector': row['Sector'],
                'is_etf': False
            }
            ndx_count += 1
        else:
            duplicates += 1
            
    # Sector ETFs
    etf_count = 0
    for row in etf_data:
        ticker = row['Ticker']
        if ticker not in universe:
            universe[ticker] = {
                'company': row['Company'],
                'sector': row['Sector'],
                'is_etf': True
            }
            etf_count += 1
        else:
            duplicates += 1

    logging.info("  Universe Summary:")
    logging.info(f"    S&P500: {sp500_count}")
    logging.info(f"    Nasdaq100: {ndx_count}")
    logging.info(f"    ETFs: {etf_count}")
    logging.info(f"    Duplicates removed: {duplicates}")
    logging.info(f"    Final universe: {len(universe)}")
    
    return universe
