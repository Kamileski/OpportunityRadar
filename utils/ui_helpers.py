import streamlit as st

def format_score(score):
    """Format composite score to 1 decimal place."""
    try:
        return f"{float(score):.1f}"
    except (ValueError, TypeError):
        return str(score)

def format_delta(delta):
    """Format delta with explicit plus/minus sign."""
    try:
        d = float(delta)
        return f"{d:+.1f}"
    except (ValueError, TypeError):
        return str(delta)

def apply_custom_css():
    """Apply custom professional CSS to the dashboard."""
    st.markdown("""
    <style>
        /* Modern minimal look */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');
        
        .stApp {
            font-family: 'Inter', sans-serif;
        }
        
        .metric-card {
            background-color: #1E2329;
            border-radius: 8px;
            padding: 16px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border: 1px solid #2B3139;
            text-align: center;
        }
        
        .metric-label {
            font-size: 13px;
            color: #848E9C;
            text-transform: uppercase;
            font-weight: 600;
            margin-bottom: 8px;
        }
        
        .metric-value {
            font-family: 'JetBrains Mono', monospace;
            font-size: 24px;
            font-weight: 700;
            color: #EAECEF;
        }
        
        .value-green { color: #0ECB81; }
        .value-red { color: #F6465D; }
        
        .thesis-card {
            background-color: #181A20;
            border-left: 4px solid #FCD535;
            padding: 16px 20px;
            margin-bottom: 12px;
            border-radius: 0 8px 8px 0;
        }
        
        .thesis-card-green { border-left-color: #0ECB81; }
        .thesis-card-red { border-left-color: #F6465D; }
        .thesis-card-blue { border-left-color: #2962FF; }
        
        .thesis-title {
            font-size: 12px;
            text-transform: uppercase;
            font-weight: 700;
            color: #848E9C;
            margin-bottom: 8px;
        }
        
        .thesis-content {
            font-size: 14px;
            line-height: 1.5;
            color: #B7BDC6;
        }
    </style>
    """, unsafe_allow_html=True)

def render_metric_card(label, value, is_positive=None):
    """Render a styled metric card."""
    color_class = ""
    if is_positive is True:
        color_class = "value-green"
    elif is_positive is False:
        color_class = "value-red"
        
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value {color_class}">{value}</div>
    </div>
    """, unsafe_allow_html=True)
