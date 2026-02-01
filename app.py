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
                latest_prices = close_data.ffill().iloc[-1]
            else:
                latest_prices = data.iloc[-1]
                
    except Exception as e:
        st.error(f"Yahoo Finance 下載失敗: {e}")
        latest_prices = pd.Series()

    fx_rate = latest_prices.get('AUDUSD=X', 0.70)
    if pd.isna(fx_rate) or fx_rate == 0: fx_rate = 0.70

    # 計算欄位
    current_prices = []
    market_values_aud = []
    total_costs_aud = [] 
    pnl_aud = []        
    dist_to_stop = []

    for _, row in df.iterrows():
        ticker = row['Ticker'].strip()
        currency = row['Currency']
        shares = row['Shares']
        cost = row['Avg_Cost']
        
        # 1. 價格處理
        if ticker == 'Cash':
            price = 1.0
            # 現金成本 = 現金本身 (換算回 AUD)
            cost_aud_total = shares / fx_rate if currency == 'USD' else shares
            mv = cost_aud_total
        else:
            try:
                price = latest_prices.get(ticker)
                if pd.isna(price): price = cost
            except:
                price = cost
            
            # 市值換算
            mv = (price * shares) / fx_rate if currency == 'USD' else price * shares
            
            # 成本換算 (計算總成本 AUD)
            cost_aud_total = (cost * shares) / fx_rate if currency == 'USD' else (cost * shares)

        # 2. 損益計算
        unrealized = mv - cost_aud_total

        # 3. 停損距離
        stop_price = row.get('Stop_Loss_Price', 0)
        if ticker != 'Cash' and stop_price > 0:
            dist = (price - stop_price) / price
        else:
            dist = 1.0

        current_prices.append(price)
        market_values_aud.append(mv)
        total_costs_aud.append(cost_aud_total)
        pnl_aud.append(unrealized)
        dist_to_stop.append(dist)

    df['Current_Price'] = current_prices
    df['Total_Cost_AUD'] = total_costs_aud
    df['Market_Value_AUD'] = market_values_aud
    df['Unrealized_PnL'] = pnl_aud
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
    
    # ==========================================
    # 🔴 請在這裡修改您的真實總本金
    # ==========================================
    CAPITAL_INJECTED = 743564  # <--- 修改這個數字
    
    unrealized_pnl = total_net_worth - CAPITAL_INJECTED
    pnl_pct = (unrealized_pnl / CAPITAL_INJECTED) * 100

    # KPI 顯示
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總資產 (AUD)", f"${total_net_worth:,.0f}")
    col2.metric("總投入本金", f"${CAPITAL_INJECTED:,.0f}")
    col3.metric("總未實現損益", f"${unrealized_pnl:,.0f}", f"{pnl_pct:.2f}%", 
                delta_color="normal" if unrealized_pnl > 0 else "inverse")
    col4.metric("即時匯率", f"{fx_rate:.4f}")

    st.markdown("---")

    # 跨平台合併運算
    ticker_stats = df_updated.groupby('Ticker')[['Market_Value_AUD', 'Target_Weight']].sum().reset_index()
    ticker_stats.rename(columns={'Market_Value_AUD': 'Total_Ticker_Value', 'Target_Weight': 'Total_Ticker_Target'}, inplace=True)
    ticker_stats['Ticker_Allocation_%'] = ticker_stats['Total_Ticker_Value'] / total_net_worth
    ticker_stats['Global_Drift_%'] = ticker_stats['Ticker_Allocation_%'] - ticker_stats['Total_Ticker_Target']

    # 合併回原始資料
    df_final = pd.merge(df_updated, ticker_stats[['Ticker', 'Total_Ticker_Target', 'Global_Drift_%']], on='Ticker', how='left')
    df_final['Actual_%'] = df_final['Market_Value_AUD'] / total_net_worth

    # --- 🔘 檢視模式切換開關 ---
    view_mode = st.radio("顯示模式 (View Mode)", ["合併檢視 (Summary)", "詳細檢視 (Detailed)"], horizontal=True)

    if view_mode == "合併檢視 (Summary)":
        # 製作合併表
        summary_df = df_final.groupby('Ticker').agg({
            'Shares': 'sum',
            'Total_Cost_AUD': 'sum',
            'Market_Value_AUD': 'sum',
            'Unrealized_PnL': 'sum',
            'Total_Ticker_Target': 'first', # 目標是一樣的，取第一個
            'Global_Drift_%': 'first',      # Drift 是一樣的
            'Current_Price': 'mean'         # 價格取平均 (其實都一樣)
        }).reset_index()
        
        # 計算合併後的權重
        summary_df['Actual_%'] = summary_df['Market_Value_AUD'] / total_net_worth
        
        # 選擇顯示欄位
        display_cols = ['Ticker', 'Shares', 'Current_Price', 'Total_Cost_AUD', 'Market_Value_AUD', 'Unrealized_PnL', 'Actual_%', 'Total_Ticker_Target', 'Global_Drift_%']
        display_df = summary_df[display_cols].copy()
        
    else:
        # 詳細檢視 (保留 Platform 等欄位)
        display_cols = ['Ticker', 'Platform', 'Shares', 'Avg_Cost', 'Current_Price', 'Total_Cost_AUD', 'Market_Value_AUD', 'Unrealized_PnL', 'Actual_%', 'Total_Ticker_Target', 'Global_Drift_%', 'Stop_Loss_Price', 'Dist_to_Stop']
        display_df = df_final[display_cols].copy()

    # --- 製作 TOTAL Row (總計行) ---
    total_row = pd.DataFrame(columns=display_cols)
    # 建立一個全空的 row
    t_row = {col: '' for col in display_cols}
    
    # 填入加總數值
    t_row['Ticker'] = 'TOTAL'
    t_row['Total_Cost_AUD'] = display_df['Total_Cost_AUD'].sum()
    t_row['Market_Value_AUD'] = display_df['Market_Value_AUD'].sum()
    t_row['Unrealized_PnL'] = display_df['Unrealized_PnL'].sum()
    t_row['Actual_%'] = display_df['Actual_%'].sum()
    t_row['Total_Ticker_Target'] = display_df['Total_Ticker_Target'].sum() if 'Total_Ticker_Target' in display_df.columns else 0
    
    # 轉成 DataFrame 並合併
    total_df = pd.DataFrame([t_row])
    display_df = pd.concat([display_df, total_df], ignore_index=True)

    # --- 樣式設定 ---
    def style_dataframe(row):
        styles = [''] * len(row)
        
        # Total 行加粗
        if row['Ticker'] == 'TOTAL':
            return ['font-weight: bold; background-color: #f0f2f6'] * len(row)
        
        # 停損紅色警報 (只在詳細模式顯示，且不是 Cash)
        if 'Stop_Loss_Price' in row and row['Ticker'] != 'Cash' and row['Ticker'] != 'TOTAL':
            try:
                stop = float(row['Stop_Loss_Price'])
                curr = float(row['Current_Price'])
                if stop > 0 and curr < stop:
                    return ['background-color: #ffcccc; color: black'] * len(row)
            except:
                pass
            
        return styles

    st.subheader(f"📊 {view_mode}")
    
    st.dataframe(
        display_df.style
        .format({
            'Avg_Cost': "{:,.2f}",
            'Current_Price': "{:,.2f}",
            'Total_Cost_AUD': "${:,.0f}",
            'Market_Value_AUD': "${:,.0f}",
            'Unrealized_PnL': "${:,.0f}",
            'Actual_%': "{:.1%}",
            'Total_Ticker_Target': "{:.1%}",
            'Global_Drift_%': "{:.2%}",
            'Stop_Loss_Price': "{:,.2f}",
            'Dist_to_Stop': "{:.1%}"
        }, na_rep="-")
        .apply(style_dataframe, axis=1)
        .applymap(lambda x: 'color: green' if x > 0 else 'color: red', subset=['Unrealized_PnL'])
        .applymap(lambda x: 'color: green; font-weight: bold' if x > 0.005 else 'color: red; font-weight: bold' if x < -0.005 else '', subset=['Global_Drift_%'])
    )

    # --- 戰略建議 (永遠基於合併後的 Drift) ---
    st.markdown("### ⚡ 總司令行動建議")
    action_tickers = ticker_stats[ticker_stats['Global_Drift_%'] < -0.005]
    
    if not action_tickers.empty:
        for _, row in action_tickers.iterrows():
            shortfall = abs(row['Global_Drift_%']) * total_net_worth
            st.info(f"🟢 **加碼訊號 ({row['Ticker']})**: 需補足 **${shortfall:,.0f} AUD**。")
    else:
        st.success("✅ 投資組合平衡完美。")

else:
    st.info("⏳ 等待數據中...")
