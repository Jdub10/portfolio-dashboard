import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# --- 1. 頁面核心設定 ---
st.set_page_config(
    page_title="James' Commander Dashboard",
    layout="wide",
    page_icon="🔭",
    initial_sidebar_state="collapsed"
)

# --- 🎨 高級視覺優化 (High Class & Clean) ---
st.markdown("""
<style>
    .main { background-color: #ffffff; }
    h1, h2, h3 { font-family: 'Inter', sans-serif; letter-spacing: -0.5px; }
    [data-testid="stMetric"] {
        background: #fbfbfb;
        border: 1px solid #f0f0f0;
        border-radius: 8px;
        padding: 1rem !important;
    }
    .stButton>button {
        border-radius: 4px; font-weight: 500; border: 1px solid #e0e0e0;
        background-color: transparent; color: #333; transition: all 0.3s;
    }
    .stButton>button:hover { border-color: #333; background-color: #333; color: white; }
    footer, #MainMenu { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# --- 🔐 密碼保護 ---
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            st.text_input("ACCESS CODE", type="password", on_change=password_entered, key="password")
        return False
    return st.session_state["password_correct"]

if not check_password():
    st.stop()

# --- 🛰️ 資料與色彩中心 ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/14IGIMj9iR5qOtmYT1e6FgN8t2tdQ5M1R_-hS6rw1RQs/export?format=csv"
LUXURY_COLORS = ['#2E4053', '#5D6D7E', '#85929E', '#AED6F1', '#F5B041', '#EC7063', '#48C9B0', '#AF7AC5']

@st.cache_data(ttl=600)
def load_data():
    df = pd.read_csv(SHEET_URL)
    df.columns = df.columns.str.strip()
    for col in ['Shares', 'Avg_Cost', 'Stop_Loss_Price']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    if 'Target_Weight' in df.columns:
        df['Target_Weight'] = pd.to_numeric(df['Target_Weight'].astype(str).str.replace('%', ''), errors='coerce')
        df.loc[df['Target_Weight'] > 1.0, 'Target_Weight'] /= 100
    return df

def fetch_prices(df):
    tickers = [t.strip() for t in df[df['Ticker'] != 'Cash']['Ticker'].unique()]
    tickers.append("AUDUSD=X")
    data = yf.download(tickers, period="5d", progress=False)['Close'].ffill().iloc[-1]
    fx = data.get('AUDUSD=X', 0.70)
    if pd.isna(fx) or fx == 0: fx = 0.70
    
    df['Current_Price'] = df['Ticker'].map(data).fillna(df['Avg_Cost'])
    df.loc[df['Ticker'] == 'Cash', 'Current_Price'] = 1.0
    df['MV_AUD'] = df.apply(lambda r: (r['Current_Price'] * r['Shares']) / fx if r['Currency'] == 'USD' else r['Current_Price'] * r['Shares'], axis=1)
    df['Cost_AUD'] = df.apply(lambda r: (r['Avg_Cost'] * r['Shares']) / fx if r['Currency'] == 'USD' else r['Avg_Cost'] * r['Shares'], axis=1)
    df['PnL_AUD'] = df['MV_AUD'] - df['Cost_AUD']
    return df, fx

def get_clean_pie_df(df, threshold=0.85):
    temp = df.groupby('Ticker')['MV_AUD'].sum().sort_values(ascending=False).reset_index()
    total = temp['MV_AUD'].sum()
    cumsum = (temp['MV_AUD'].cumsum() / total) if total > 0 else 0
    main = temp[cumsum <= threshold]
    others = temp[cumsum > threshold]
    if not others.empty:
        other_label = f"Others ({', '.join(others['Ticker'].iloc[:2])}...)"
        other_row = pd.DataFrame({'Ticker': [other_label], 'MV_AUD': [others['MV_AUD'].sum()]})
        return pd.concat([main, other_row])
    return main

# --- 🚀 執行與介面 ---
df_raw = load_data()
capital_row = df_raw[df_raw['Ticker'] == 'CAPITAL']
CAPITAL = capital_row['Shares'].sum() if not capital_row.empty else 743564
df_clean = df_raw[df_raw['Ticker'] != 'CAPITAL'].copy()

with st.spinner('Syncing Market Data...'):
    df, fx = fetch_prices(df_clean)

total_mv = df['MV_AUD'].sum()
pnl_total = total_mv - CAPITAL
pnl_pct = (pnl_total / CAPITAL * 100) if CAPITAL > 0 else 0

st.title("Strategic Portfolio Dashboard")

m1, m2, m3, m4 = st.columns(4)
m1.metric("Net Worth", f"${total_mv:,.0f} AUD")
m2.metric("Total PnL", f"${pnl_total:,.0f}", f"{pnl_pct:.2f}%")
m3.metric("Capital", f"${CAPITAL:,.0f}")
m4.metric("FX Rate", f"{fx:.4f}")

st.markdown("<br>", unsafe_allow_html=True)

# --- 圖表區 (No Overlap Layout) ---
with st.container():
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Asset Allocation (Incl. Cash)")
        df_pie1 = get_clean_pie_df(df)
        fig1 = px.pie(df_pie1, values='MV_AUD', names='Ticker', hole=0.5, color_discrete_sequence=LUXURY_COLORS)
        fig1.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450, showlegend=True, legend=dict(orientation="h", y=-0.1))
        fig1.update_traces(textinfo='percent', textposition='inside')
        st.plotly_chart(fig1, use_container_width=True)

    with c2:
        st.subheader("Equity Distribution (Excl. Cash)")
        df_pie2 = get_clean_pie_df(df[df['Ticker'] != 'Cash'])
        fig2 = px.pie(df_pie2, values='MV_AUD', names='Ticker', hole=0.5, color_discrete_sequence=LUXURY_COLORS)
        fig2.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450, showlegend=True, legend=dict(orientation="h", y=-0.1))
        fig2.update_traces(textinfo='percent', textposition='inside')
        st.plotly_chart(fig2, use_container_width=True)

with st.container():
    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Sector Exposure")
        if 'Sector' in df.columns:
            df_sec = df[df['Ticker'] != 'Cash'].groupby('Sector')['MV_AUD'].sum().reset_index()
            fig3 = px.pie(df_sec, values='MV_AUD', names='Sector', hole=0.5, color_discrete_sequence=LUXURY_COLORS)
            fig3.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450, showlegend=True, legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig3, use_container_width=True)
    with c4:
        st.subheader("Strategy Role")
        if 'Strategy Role' in df.columns:
            df_strat = df[df['Ticker'] != 'Cash'].groupby('Strategy Role')['MV_AUD'].sum().reset_index()
            fig4 = px.pie(df_strat, values='MV_AUD', names='Strategy Role', hole=0.5, 
                          color_discrete_map={'Core':'#2E4053', 'Satellite':'#5D6D7E', 'Speculative':'#EC7063'})
            fig4.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450, showlegend=True, legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig4, use_container_width=True)

st.markdown("---")

# --- 表格區 (Consolidated & Fixed) ---
view = st.radio("View Mode", ["Summary", "Detailed"], horizontal=True, label_visibility="collapsed")

# 1. Prepare base data
df['Cost_AUD_Val'] = df['Cost_AUD']

if view == "Summary":
    df_disp = df.groupby('Ticker').agg({
        'Shares': 'sum',
        'Avg_Cost': 'mean', 
        'Cost_AUD_Val': 'sum',
        'Current_Price': 'mean',
        'MV_AUD': 'sum',
        'PnL_AUD': 'sum'
    }).reset_index()
    df_disp = df_disp.rename(columns={'Cost_AUD_Val': 'Total_Cost_AUD'})
else:
    df_disp = df[['Ticker', 'Platform', 'Shares', 'Avg_Cost', 'Cost_AUD', 'Current_Price', 'MV_AUD', 'PnL_AUD', 'Stop_Loss_Price']].copy()
    df_disp = df_disp.rename(columns={'Cost_AUD': 'Total_Cost_AUD'})

# 2. Calculate PnL % for each row
df_disp['PnL_%'] = (df_disp['PnL_AUD'] / df_disp['Total_Cost_AUD'] * 100).fillna(0)

# 3. Sort and clean index
df_disp = df_disp.sort_values('MV_AUD', ascending=False).reset_index(drop=True)
df_disp.index += 1

# 4. Create TOTAL row
total_row = pd.DataFrame({
    'Ticker': ['TOTAL'], 
    'Total_Cost_AUD': [df_disp['Total_Cost_AUD'].sum()],
    'MV_AUD': [df_disp['MV_AUD'].sum()], 
    'PnL_AUD': [df_disp['PnL_AUD'].sum()]
}, index=[' '])

# Calculate Total PnL %
if total_row['Total_Cost_AUD'].iloc[0] != 0:
    total_row['PnL_%'] = (total_row['PnL_AUD'] / total_row['Total_Cost_AUD'] * 100)
else:
    total_row['PnL_%'] = 0

# 5. Final Concat
df_final = pd.concat([df_disp, total_row])

# 6. Single Render Call
st.dataframe(
    df_final.style.format({
        'Current_Price': "{:.2f}", 
        'Avg_Cost': "{:.2f}",
        'Total_Cost_AUD': "${:,.0f}",
        'MV_AUD': "${:,.0f}", 
        'PnL_AUD': "${:,.0f}",
        'PnL_%': "{:.2f}%"
    }, na_rep="-")
    .apply(lambda x: ['font-weight: bold; background-color: #f0f2f6' if x.Ticker == 'TOTAL' else '' for i in x], axis=1),
    use_container_width=True
)

# 添加 TOTAL Row
total_row = pd.DataFrame({'Ticker': ['TOTAL'], 'MV_AUD': [df_disp['MV_AUD'].sum()], 'PnL_AUD': [df_disp['PnL_AUD'].sum()]}, index=[' '])
df_final = pd.concat([df_disp, total_df if 'total_df' in locals() else total_row])

st.dataframe(
    df_final.style.format({'Current_Price': "{:.2f}", 'MV_AUD': "${:,.0f}", 'PnL_AUD': "${:,.0f}", 'Avg_Cost': "{:.2f}"}, na_rep="-")
    .apply(lambda x: ['font-weight: bold; background-color: #fafafa' if x.name == 'TOTAL' or x.Ticker == 'TOTAL' else '' for i in x], axis=1),
    use_container_width=True
)

st.markdown("<br>", unsafe_allow_html=True)
if st.button('🔄 Sync Portfolio'):
    st.cache_data.clear()
    st.rerun()


