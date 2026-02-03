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

# ==========================================
# 🎨 高級極簡 CSS (Luxury & Fast)
# ==========================================
st.markdown("""
<style>
    /* 核心背景與字體 */
    .main { background-color: #ffffff; }
    h1, h2, h3 { font-family: 'Inter', sans-serif; letter-spacing: -0.5px; }
    
    /* 頂部 KPI 卡片優化 */
    [data-testid="stMetric"] {
        background: #fbfbfb;
        border: 1px solid #f0f0f0;
        border-radius: 8px;
        padding: 1rem !important;
        box-shadow: none !important;
    }
    
    /* 按鈕樣式 (Neat & Clean) */
    .stButton>button {
        border-radius: 4px;
        font-weight: 500;
        border: 1px solid #e0e0e0;
        background-color: transparent;
        color: #333;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        border-color: #333;
        background-color: #333;
        color: white;
    }

    /* 圖表容器間距 */
    .chart-container { margin-bottom: 2rem; }

    /* 隱藏預設元件 */
    footer {visibility: hidden;}
    #MainMenu {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 密碼保護 (Fast Check)
# ==========================================
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

# ==========================================
# 🛰️ 資料處理中心 (Speed Optimized)
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/14IGIMj9iR5qOtmYT1e6FgN8t2tdQ5M1R_-hS6rw1RQs/export?format=csv"

@st.cache_data(ttl=600) # 10分鐘快取，極速讀取
def load_data():
    df = pd.read_csv(SHEET_URL)
    df.columns = df.columns.str.strip()
    
    # 清洗數字
    for col in ['Shares', 'Avg_Cost', 'Stop_Loss_Price']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', ''), errors='coerce').fillna(0)
    
    # 清洗權重
    if 'Target_Weight' in df.columns:
        df['Target_Weight'] = pd.to_numeric(df['Target_Weight'].astype(str).str.replace('%', ''), errors='coerce')
        df.loc[df['Target_Weight'] > 1.0, 'Target_Weight'] /= 100
    
    return df

def fetch_prices(df):
    tickers = [t.strip() for t in df[df['Ticker'] != 'Cash']['Ticker'].unique()]
    tickers.append("AUDUSD=X")
    
    # 抓取報價 (5天資料)
    data = yf.download(tickers, period="5d", progress=False)['Close'].ffill().iloc[-1]
    
    fx = data.get('AUDUSD=X', 0.70)
    if pd.isna(fx) or fx == 0: fx = 0.70
    
    # 計算衍生數據
    df['Current_Price'] = df['Ticker'].map(data).fillna(df['Avg_Cost'])
    df.loc[df['Ticker'] == 'Cash', 'Current_Price'] = 1.0
    
    # 市值與成本 (AUD 換算)
    df['MV_AUD'] = df.apply(lambda r: (r['Current_Price'] * r['Shares']) / fx if r['Currency'] == 'USD' else r['Current_Price'] * r['Shares'], axis=1)
    df['Cost_AUD'] = df.apply(lambda r: (r['Avg_Cost'] * r['Shares']) / fx if r['Currency'] == 'USD' else r['Avg_Cost'] * r['Shares'], axis=1)
    df['PnL_AUD'] = df['MV_AUD'] - df['Cost_AUD']
    
    return df, fx

# --- 🛠️ 圓餅圖優化 ---
def get_clean_pie_df(df, threshold=0.85):
    temp = df.groupby('Ticker')['MV_AUD'].sum().sort_values(ascending=False).reset_index()
    total = temp['MV_AUD'].sum()
    cumsum = temp['MV_AUD'].cumsum() / total
    
    main = temp[cumsum <= threshold]
    others = temp[cumsum > threshold]
    
    if not others.empty:
        other_label = f"Others ({', '.join(others['Ticker'].iloc[:2])}...)"
        other_row = pd.DataFrame({'Ticker': [other_label], 'MV_AUD': [others['MV_AUD'].sum()]})
        return pd.concat([main, other_row])
    return main

# ==========================================
# 💎 UI 呈現 (Neat & No Overlap)
# ==========================================
df_raw = load_data()

# 提煉本金
capital_row = df_raw[df_raw['Ticker'] == 'CAPITAL']
CAPITAL = capital_row['Shares'].sum() if not capital_row.empty else 743564
df_clean = df_raw[df_raw['Ticker'] != 'CAPITAL'].copy()

with st.spinner('Synchronizing with Global Markets...'):
    df, fx = fetch_prices(df_clean)

# KPI 區
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

# 圖表區 (使用 Container 避免 Overlap)
with st.container():
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("Asset Allocation")
        df_pie = get_clean_pie_df(df)
        fig1 = px.pie(df_pie, values='MV_AUD', names='Ticker', hole=0.5,
                      color_discrete_sequence=LUXURY_COLORS) # 🟢 修改這裡：改用我們定義的 LUXURY_COLORS
        fig1.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450, showlegend=False)
        fig1.update_traces(textinfo='label+percent', textposition='outside')
        st.plotly_chart(fig1, use_container_width=True)

   with c2:
        st.subheader("Strategy Distribution")
        df_strat = df[df['Ticker'] != 'Cash'].groupby('Strategy Role')['MV_AUD'].sum().reset_index()
        fig2 = px.pie(df_strat, values='MV_AUD', names='Strategy Role', hole=0.5,
                      color_discrete_map={'Core':'#2E4053', 'Satellite':'#5D6D7E', 'Speculative':'#EC7063'})
        fig2.update_layout(margin=dict(t=20, b=20, l=0, r=0), height=450, showlegend=False)
        fig2.update_traces(textinfo='label+percent', textposition='outside')
        st.plotly_chart(fig2, use_container_width=True)

st.markdown("---")

# 表格區
st.subheader("Holdings Analysis")
view = st.radio("View Mode", ["Summary", "Detailed"], horizontal=True, label_visibility="collapsed")

if view == "Summary":
    df_disp = df.groupby('Ticker').agg({
        'Shares': 'sum',
        'Current_Price': 'mean',
        'Cost_AUD': 'sum',
        'MV_AUD': 'sum',
        'PnL_AUD': 'sum'
    }).reset_index()
else:
    df_disp = df[['Ticker', 'Platform', 'Shares', 'Avg_Cost', 'Current_Price', 'MV_AUD', 'PnL_AUD']]

# 排序與編號 (從1開始)
df_disp = df_disp.sort_values('MV_AUD', ascending=False).reset_index(drop=True)
df_disp.index += 1

# 添加 TOTAL
total_row = pd.DataFrame({
    'Ticker': ['TOTAL'], 
    'MV_AUD': [df_disp['MV_AUD'].sum()], 
    'PnL_AUD': [df_disp['PnL_AUD'].sum()]
}, index=[' '])
df_final = pd.concat([df_disp, total_row])

# 樣式與呈現
st.dataframe(
    df_final.style.format({
        'Current_Price': "{:.2f}",
        'MV_AUD': "${:,.0f}",
        'PnL_AUD': "${:,.0f}",
        'Avg_Cost': "{:.2f}",
        'Cost_AUD': "${:,.0f}"
    }, na_rep="-").apply(lambda x: ['font-weight: bold; background-color: #fafafa' if x.name == 'TOTAL' else '' for i in x], axis=1),
    use_container_width=True
)

# 行動建議
action = df.groupby('Ticker').sum().reset_index() # 簡化邏輯
st.markdown("<br>", unsafe_allow_html=True)
if st.button('🔄 Sync Portfolio'):
    st.cache_data.clear()
    st.rerun()

