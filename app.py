import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# --- 1. 頁面設定 ---
st.set_page_config(page_title="James' Portfolio Dashboard", layout="wide")

# ==========================================
# 🔴 請將您的 Google Sheet CSV 連結貼在下方引號內
# 格式必須是: https://docs.google.com/.../export?format=csv
# ==========================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/14IGIMj9iR5qOtmYT1e6FgN8t2tdQ5M1R_-hS6rw1RQs/export?format=csv"  

# --- 2. 核心函數：讀取與清洗數據 ---
@st.cache_data(ttl=60) # 每60秒刷新一次快取
def load_and_clean_data():
    try:
        # 讀取 Google Sheet CSV
        df = pd.read_csv(SHEET_URL)
        
        # 清洗欄位名稱 (去除前後空白)
        df.columns = df.columns.str.strip()
        
        # 確保必要欄位存在
        required_cols = ['Shares', 'Avg_Cost', 'Target_Weight']
        for col in required_cols:
            if col not in df.columns:
                st.error(f"❌ 資料表缺少欄位: {col}，請檢查 Google Sheet 標題列。")
                return pd.DataFrame()

        # 清洗數字欄位 (去除逗號, 轉換型別)
        cols_to_clean = ['Shares', 'Avg_Cost', 'Stop_Loss_Price']
        for col in cols_to_clean:
            if col in df.columns:
                # 轉成字串 -> 去除逗號 -> 轉回數字
                df[col] = df[col].astype(str).str.replace(',', '', regex=True)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

        # 清洗 Target_Weight (處理 % 符號)
        # 如果您在 Excel 填 18.9%，這裡會自動轉成 0.189
        if df['Target_Weight'].dtype == object:
             df['Target_Weight'] = df['Target_Weight'].astype(str).str.replace('%', '', regex=True)
             df['Target_Weight'] = pd.to_numeric(df['Target_Weight'], errors='coerce')
        
        # 如果數字大於 1 (例如填了 18.9 代表 18.9%)，自動除以 100
        # 假設沒有任何單一持股目標會超過 100% (即 1.0)
        mask = df['Target_Weight'] > 1.0
        df.loc[mask, 'Target_Weight'] = df.loc[mask, 'Target_Weight'] / 100
        
        return df
    except Exception as e:
        st.error(f"❌ 無法讀取資料，請檢查連結是否正確。錯誤訊息: {e}")
        return pd.DataFrame()

def fetch_live_data(df):
    # 1. 取得股票代號 (排除 Cash)
    tickers_list = df[df['Ticker'] != 'Cash']['Ticker'].unique().tolist()
    
    # 2. 清理代號 (移除空白)
    tickers_list = [t.strip() for t in tickers_list]
    
    # 3. 加入匯率
    if "AUDUSD=X" not in tickers_list:
        tickers_list.append("AUDUSD=X")
    
    st.write(f"正在抓取以下代號: {tickers_list}") # 顯示除錯訊息，讓您知道它在抓什麼

    # 4. 下載數據 (使用更寬鬆的設定)
    try:
        # 下載 2 天的數據以防時差導致抓不到今天的
        data = yf.download(tickers_list, period="2d", group_by='ticker', auto_adjust=True)
        
        # 處理資料結構 (Yahoo 回傳格式有時會變)
        if len(tickers_list) == 1:
            # 如果只有一支股票，結構不同，統一轉成 DataFrame
            latest_prices = data['Close'].iloc[-1]
        else:
            # 多支股票，取 'Close' 欄位的最後一行
            # 注意：yfinance 新版回傳可能是 MultiIndex，需要小心處理
            try:
                latest_prices = data.xs('Close', level=1, axis=1).iloc[-1]
            except:
                # 舊版相容
                latest_prices = data['Close'].iloc[-1]
                
    except Exception as e:
        st.error(f"Yahoo Finance 下載失敗: {e}")
        latest_prices = pd.Series()

    # 5. 取得匯率
    fx_rate = latest_prices.get('AUDUSD=X', 0.70)
    if pd.isna(fx_rate): fx_rate = 0.70

    # 6. 填入數據
    current_prices = []
    market_values_aud = []
    dist_to_stop = []

    for _, row in df.iterrows():
        ticker = row['Ticker'].strip()
        currency = row['Currency']
        shares = row['Shares']
        cost = row['Avg_Cost']
        
        # --- A. 處理價格 ---
        if ticker == 'Cash':
            price = 1.0
            mv = shares / fx_rate if currency == 'USD' else shares
        else:
            # 嘗試從下載的數據中找價格
            try:
                # 先找完全匹配的
                price = latest_prices.get(ticker)
                
                # 如果找不到，且是 NaN，則使用成本價
                if pd.isna(price):
                    price = cost
            except:
                price = cost
            
            # 市值換算
            mv = (price * shares) / fx_rate if currency == 'USD' else price * shares

        # --- B. 計算停損 ---
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

    # --- 總資產計算 ---
    total_net_worth = df_updated['Market_Value_AUD'].sum()
    
    # 這裡可以手動輸入您的總入金 (Capital Injected) 以求精確
    CAPITAL_INJECTED = 743564 
    
    unrealized_pnl = total_net_worth - CAPITAL_INJECTED
    pnl_pct = (unrealized_pnl / CAPITAL_INJECTED) * 100

    # --- 頂層 KPI ---
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總資產 (AUD)", f"${total_net_worth:,.0f}")
    col2.metric("總投入本金", f"${CAPITAL_INJECTED:,.0f}")
    col3.metric("未實現損益", f"${unrealized_pnl:,.0f}", f"{pnl_pct:.2f}%", 
                delta_color="normal" if unrealized_pnl > 0 else "inverse")
    col4.metric("即時匯率 (AUD/USD)", f"{fx_rate:.4f}")

    st.markdown("---")

    # --- 圖表分析區 ---
    col_chart1, col_chart2 = st.columns(2)
    df_equity = df_updated[df_updated['Ticker'] != 'Cash'] # 排除現金看分佈
    
    with col_chart1:
        st.subheader("🍰 板塊配置 (Sector)")
        if 'Sector' in df_equity.columns:
            fig1 = px.pie(df_equity, values='Market_Value_AUD', names='Sector', hole=0.4)
            st.plotly_chart(fig1, use_container_width=True)

    with col_chart2:
        st.subheader("⚔️ 戰略角色 (Strategy)")
        if 'Strategy Role' in df_equity.columns:
            fig2 = px.pie(df_equity, values='Market_Value_AUD', names='Strategy Role', hole=0.4,
                         color_discrete_map={'Core':'#00cc96', 'Satellite':'#636efa', 'Speculative':'#EF553B'})
            st.plotly_chart(fig2, use_container_width=True)

    # --- 持股明細與 Drift ---
    st.subheader("📊 持股監控與再平衡")

    # 計算 Drift
    df_updated['Portfolio %'] = df_updated['Market_Value_AUD'] / total_net_worth
    df_updated['Drift %'] = df_updated['Portfolio %'] - df_updated['Target_Weight']

    # 選擇要顯示的欄位
    cols_to_show = ['Ticker', 'Platform', 'Sector', 'Strategy Role', 'Shares', 'Avg_Cost', 'Current_Price', 'Stop_Loss_Price', 'Dist_to_Stop', 'Market_Value_AUD', 'Target_Weight', 'Drift %']
    # 確保欄位存在才顯示
    display_cols = [c for c in cols_to_show if c in df_updated.columns]
    
    display_df = df_updated[display_cols].copy()

    # 樣式函數
    def style_rows(row):
        # 停損紅色警報
        if row['Ticker'] != 'Cash' and row.get('Stop_Loss_Price', 0) > 0:
            if row['Current_Price'] < row['Stop_Loss_Price']:
                return ['background-color: #ffcccc; color: black'] * len(row)
        return [''] * len(row)

    st.dataframe(
        display_df.style
        .format({
            'Market_Value_AUD': "${:,.0f}",
            'Avg_Cost': "{:,.2f}",
            'Current_Price': "{:,.2f}",
            'Stop_Loss_Price': "{:,.2f}",
            'Dist_to_Stop': "{:.1%}",
            'Target_Weight': "{:.1%}",
            'Drift %': "{:.2%}"
        })
        .apply(style_rows, axis=1)
        .applymap(lambda x: 'color: green; font-weight: bold' if x > 0.005 else 'color: red; font-weight: bold' if x < -0.005 else '', subset=['Drift %'])
    )

    # --- 戰略行動建議 ---
    st.markdown("### ⚡ 總司令行動建議 (Action Plan)")
    
    # 找出 Drift < -0.5% 的項目 (需要買進)
    buy_list = df_updated[(df_updated['Drift %'] < -0.005) & (df_updated['Target_Weight'] > 0)]
    
    if not buy_list.empty:
        for _, row in buy_list.iterrows():
            shortfall = abs(row['Drift %']) * total_net_worth
            st.info(f"🟢 **買進訊號 ({row['Ticker']})**: 低於目標 {abs(row['Drift %']):.1%}。建議加碼約 **${shortfall:,.0f} AUD**。")
    else:
        st.success("✅ 目前投資組合平衡完美，無須重大操作。")
else:

    st.info("⏳ 等待數據中... 請確認 Google Sheet 連結正確。")

