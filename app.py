import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# --- 1. 頁面設定 ---
st.set_page_config(page_title="James' Commander Dashboard", layout="wide")

# ==========================================
# 🔴 Google Sheet CSV 連結
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/14IGIMj9iR5qOtmYT1e6FgN8t2tdQ5M1R_-hS6rw1RQs/export?format=csv"

# --- 2. 核心函數：讀取與清洗數據 ---
@st.cache_data(ttl=60)
def load_and_clean_data():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip()
        
        required_cols = ['Shares', 'Avg_Cost', 'Target_Weight']
        for col in required_cols:
            if col not in df.columns:
                st.error(f"❌ 資料表缺少欄位: {col}")
                return pd.DataFrame()

        cols_to_clean = ['Shares', 'Avg_Cost', 'Stop_Loss_Price']
        for col in cols_to_clean:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        if df['Target_Weight'].dtype == object:
             df['Target_Weight'] = df['Target_Weight'].astype(str).str.replace('%', '', regex=True)
             df['Target_Weight'] = pd.to_numeric(df['Target_Weight'], errors='coerce')
        
        # 自動修正百分比 (若填 18.9 轉為 0.189)
        mask = df['Target_Weight'] > 1.0
        df.loc[mask, 'Target_Weight'] = df.loc[mask, 'Target_Weight'] / 100
        
        return df
    except Exception as e:
        st.error(f"❌ 無法讀取資料: {e}")
        return pd.DataFrame()

def fetch_live_data(df):
    tickers_list = df[df['Ticker'] != 'Cash']['Ticker'].unique().tolist()
    tickers_list = [t.strip() for t in tickers_list]
    
    if "AUDUSD=X" not in tickers_list:
        tickers_list.append("AUDUSD=X")
    
    # 下載數據 (使用 5d + ffill 解決週末空值)
    try:
        data = yf.download(tickers_list, period="5d", progress=False)
        
        if data.empty:
            st.error("❌ Yahoo Finance 回傳空資料！")
            latest_prices = pd.Series()
        else:
            if 'Close' in data.columns:
                close_data = data['Close']
                # 🚨 關鍵：填補空值並取最後一筆
                latest_prices = close_data.ffill().iloc[-1]
            else:
                latest_prices = data.iloc[-1]
                
    except Exception as e:
        st.error(f"Yahoo Finance 下載失敗: {e}")
        latest_prices = pd.Series()

    # 取得匯率
    fx_rate = latest_prices.get('AUDUSD=X', 0.70)
    if pd.isna(fx_rate) or fx_rate == 0: fx_rate = 0.70

    # 計算個別市值
    current_prices = []
    market_values_aud = []
    dist_to_stop = []

    for _, row in df.iterrows():
        ticker = row['Ticker'].strip()
        currency = row['Currency']
        shares = row['Shares']
        cost = row['Avg_Cost']
        
        # 價格處理
        if ticker == 'Cash':
            price = 1.0
            mv = shares / fx_rate if currency == 'USD' else shares
        else:
            try:
                price = latest_prices.get(ticker)
                if pd.isna(price): price = cost
            except:
                price = cost
            
            mv = (price * shares) / fx_rate if currency == 'USD' else price * shares

        # 停損距離
        stop_price = row.get('Stop_Loss_Price', 0)
        if ticker != 'Cash' and stop_price > 0:
            dist = (price - stop_price) / price
        else:
            dist = 1.0 

        current_prices.append(price)
        market_values_aud.append(mv)
        dist_to_stop.append(dist)

    df['Current_Price'] = current_prices
    df['Market_Value_AUD'] = market_values_aud
    df['Dist_to_Stop'] = dist_to_stop
    
    return df, fx_rate

# --- 3. 主介面邏輯 ---
st.title("🚀 James' Commander Dashboard")

if st.button('🔄 Refresh Data'):
    st.cache_data.clear()

df_raw = load_and_clean_data()

if not df_raw.empty:
    with st.spinner('連線報價伺服器中...'):
        df_updated, fx_rate = fetch_live_data(df_raw)

    total_net_worth = df_updated['Market_Value_AUD'].sum()
    CAPITAL_INJECTED = 743564 
    unrealized_pnl = total_net_worth - CAPITAL_INJECTED
    pnl_pct = (unrealized_pnl / CAPITAL_INJECTED) * 100

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總資產 (AUD)", f"${total_net_worth:,.0f}")
    col2.metric("總投入本金", f"${CAPITAL_INJECTED:,.0f}")
    col3.metric("未實現損益", f"${unrealized_pnl:,.0f}", f"{pnl_pct:.2f}%", 
                delta_color="normal" if unrealized_pnl > 0 else "inverse")
    col4.metric("即時匯率", f"{fx_rate:.4f}")

    st.markdown("---")

    col_chart1, col_chart2 = st.columns(2)
    df_equity = df_updated[df_updated['Ticker'] != 'Cash']
    
    with col_chart1:
        st.subheader("🍰 板塊配置")
        if 'Sector' in df_equity.columns:
            fig1 = px.pie(df_equity, values='Market_Value_AUD', names='Sector', hole=0.4)
            st.plotly_chart(fig1, use_container_width=True)

    with col_chart2:
        st.subheader("⚔️ 戰略角色")
        if 'Strategy Role' in df_equity.columns:
            fig2 = px.pie(df_equity, values='Market_Value_AUD', names='Strategy Role', hole=0.4,
                         color_discrete_map={'Core':'#00cc96', 'Satellite':'#636efa', 'Speculative':'#EF553B'})
            st.plotly_chart(fig2, use_container_width=True)

    # ==========================================
    # 🌟 關鍵修改：合併計算 Drift (Consolidated View)
    # ==========================================
    st.subheader("📊 持股監控 (跨平台合併計算)")

    # 1. 先依 Ticker 分組，計算該股票的「總市值」與「總目標」
    ticker_stats = df_updated.groupby('Ticker')[['Market_Value_AUD', 'Target_Weight']].sum().reset_index()
    ticker_stats.rename(columns={
        'Market_Value_AUD': 'Total_Ticker_Value',
        'Target_Weight': 'Total_Ticker_Target' # 這裡會把 0% 和 8% 加總變成 8%
    }, inplace=True)

    # 2. 計算全域 Drift
    ticker_stats['Ticker_Allocation_%'] = ticker_stats['Total_Ticker_Value'] / total_net_worth
    ticker_stats['Global_Drift_%'] = ticker_stats['Ticker_Allocation_%'] - ticker_stats['Total_Ticker_Target']

    # 3. 將計算結果合併回原始表格 (讓每一行都知道自己的總目標是多少)
    df_final = pd.merge(df_updated, ticker_stats[['Ticker', 'Total_Ticker_Target', 'Global_Drift_%']], on='Ticker', how='left')

    # 準備顯示
    cols_to_show = ['Ticker', 'Platform', 'Sector', 'Shares', 'Avg_Cost', 'Current_Price', 'Market_Value_AUD', 'Total_Ticker_Target', 'Global_Drift_%']
    display_df = df_final[cols_to_show].copy()

    # 樣式設定
    def style_rows(row):
        # 停損紅燈
        if row['Ticker'] != 'Cash' and row.get('Stop_Loss_Price', 0) > 0: # 需注意 merge 後可能遺失 Stop Loss，若有保留則繼續用
            pass 
        return [''] * len(row)

    st.dataframe(
        display_df.style
        .format({
            'Market_Value_AUD': "${:,.0f}",
            'Avg_Cost': "{:,.2f}",
            'Current_Price': "{:,.2f}",
            'Total_Ticker_Target': "{:.1%}",   # 顯示合併後的目標 (8.0%)
            'Global_Drift_%': "{:.2%}"        # 顯示合併後的 Drift
        })
        .applymap(lambda x: 'color: green; font-weight: bold' if x > 0.005 else 'color: red; font-weight: bold' if x < -0.005 else '', subset=['Global_Drift_%'])
    )

    # --- 戰略建議 (使用合併後的 Drift) ---
    st.markdown("### ⚡ 總司令行動建議")
    
    # 針對 Ticker 給建議，而不是針對 Row (避免重複建議)
    # 篩選出需要買進的 Ticker (Drift < -0.5%)
    action_tickers = ticker_stats[ticker_stats['Global_Drift_%'] < -0.005]
    
    if not action_tickers.empty:
        for _, row in action_tickers.iterrows():
            shortfall = abs(row['Global_Drift_%']) * total_net_worth
            st.info(f"🟢 **加碼訊號 ({row['Ticker']})**: 整體部位低於目標 {abs(row['Global_Drift_%']):.1%}。建議總共加碼 **${shortfall:,.0f} AUD**。")
    else:
        st.success("✅ 投資組合平衡完美 (Based on Consolidated View)")

else:
    st.info("⏳ 等待數據中...")
