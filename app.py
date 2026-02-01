import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px

# --- 1. 頁面設定 (必須放在第一行) ---
st.set_page_config(page_title="James' Commander Dashboard", layout="wide")

# ==========================================
# 🔐 密碼保護功能
# ==========================================
def check_password():
    """Returns `True` if the user had the correct password."""

    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "請輸入通關密碼 (Password):", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "密碼錯誤，請重試:", type="password", on_change=password_entered, key="password"
        )
        return False
    else:
        return True

if not check_password():
    st.stop()

# ==========================================
# 🚀 主程式開始
# ==========================================

SHEET_URL = "https://docs.google.com/spreadsheets/d/14IGIMj9iR5qOtmYT1e6FgN8t2tdQ5M1R_-hS6rw1RQs/export?format=csv"

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
        
        if ticker == 'Cash':
            price = 1.0
            cost_aud_total = shares / fx_rate if currency == 'USD' else shares
            mv = cost_aud_total
        else:
            try:
                price = latest_prices.get(ticker)
                if pd.isna(price): price = cost
            except:
                price = cost
            
            mv = (price * shares) / fx_rate if currency == 'USD' else price * shares
            cost_aud_total = (cost * shares) / fx_rate if currency == 'USD' else (cost * shares)

        unrealized = mv - cost_aud_total

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

# --- 🛠️ 圓餅圖優化函數 ---
def group_small_holdings(df, value_col='Market_Value_AUD', name_col='Ticker', threshold=0.80):
    df = df.sort_values(value_col, ascending=False)
    total_val = df[value_col].sum()
    
    if total_val == 0:
        return df

    main_rows = []
    other_rows = []
    current_val = 0
    
    for _, row in df.iterrows():
        if current_val / total_val < threshold:
            main_rows.append(row)
            current_val += row[value_col]
        else:
            other_rows.append(row)
            
    df_main = pd.DataFrame(main_rows)
    
    if other_rows:
        others_val = sum(r[value_col] for r in other_rows)
        others_names = [r[name_col] for r in other_rows]
        if len(others_names) > 3:
            names_str = ", ".join(others_names[:3]) + " etc"
        else:
            names_str = ", ".join(others_names)
        label = f"Others ({names_str})"
        new_row = {name_col: label, value_col: others_val}
        df_others = pd.DataFrame([new_row])
        df_final = pd.concat([df_main, df_others], ignore_index=True)
        return df_final
    else:
        return df_main

# --- 主介面 ---
st.title("🚀 James' Commander Dashboard")

if st.button('🔄 Refresh Data'):
    st.cache_data.clear()

df_raw = load_and_clean_data()

if not df_raw.empty:

    capital_row = df_raw[df_raw['Ticker'] == 'CAPITAL']
    if not capital_row.empty:
        CAPITAL_INJECTED = capital_row['Shares'].sum()
        df_raw = df_raw[df_raw['Ticker'] != 'CAPITAL']
    else:
        CAPITAL_INJECTED = 743564 

    with st.spinner('連線報價伺服器中...'):
        df_updated, fx_rate = fetch_live_data(df_raw)

    total_net_worth = df_updated['Market_Value_AUD'].sum()
    unrealized_pnl = total_net_worth - CAPITAL_INJECTED
    pnl_pct = (unrealized_pnl / CAPITAL_INJECTED) * 100 if CAPITAL_INJECTED > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("總資產 (AUD)", f"${total_net_worth:,.0f}")
    col2.metric("總投入本金", f"${CAPITAL_INJECTED:,.0f}")
    col3.metric("總未實現損益", f"${unrealized_pnl:,.0f}", f"{pnl_pct:.2f}%", 
                delta_color="normal" if unrealized_pnl > 0 else "inverse")
    col4.metric("即時匯率", f"{fx_rate:.4f}")

    st.markdown("---")

    # ==========================================
    # 📊 第一排圖表：資金分佈
    # ==========================================
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("💰 資產配置 (含現金)")
        df_incl_cash = df_updated.groupby('Ticker')['Market_Value_AUD'].sum().reset_index()
        df_incl_cash_optimized = group_small_holdings(df_incl_cash, threshold=0.80)
        fig1 = px.pie(df_incl_cash_optimized, values='Market_Value_AUD', names='Ticker', hole=0.4,
                      title=f"Total: ${total_net_worth:,.0f}")
        fig1.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig1, use_container_width=True)

    with col_chart2:
        st.subheader("📈 持股分佈 (不含現金)")
        df_excl_cash = df_updated[df_updated['Ticker'] != 'Cash'].groupby('Ticker')['Market_Value_AUD'].sum().reset_index()
        df_excl_cash_optimized = group_small_holdings(df_excl_cash, threshold=0.80)
        equity_total = df_excl_cash['Market_Value_AUD'].sum()
        fig2 = px.pie(df_excl_cash_optimized, values='Market_Value_AUD', names='Ticker', hole=0.4,
                      title=f"Equity: ${equity_total:,.0f}")
        fig2.update_traces(textposition='inside', textinfo='percent+label')
        st.plotly_chart(fig2, use_container_width=True)

    # ==========================================
    # 📊 第二排圖表：戰略配置
    # ==========================================
    col_chart3, col_chart4 = st.columns(2)
    df_equity = df_updated[df_updated['Ticker'] != 'Cash'] 
    
    with col_chart3:
        st.subheader("🍰 板塊配置 (Sector)")
        if 'Sector' in df_equity.columns:
            df_sector = df_equity.groupby('Sector')['Market_Value_AUD'].sum().reset_index().sort_values('Market_Value_AUD', ascending=False)
            fig3 = px.pie(df_sector, values='Market_Value_AUD', names='Sector', hole=0.4)
            fig3.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig3, use_container_width=True)

    with col_chart4:
        st.subheader("⚔️ 戰略角色 (Strategy)")
        if 'Strategy Role' in df_equity.columns:
            df_strategy = df_equity.groupby('Strategy Role')['Market_Value_AUD'].sum().reset_index().sort_values('Market_Value_AUD', ascending=False)
            fig4 = px.pie(df_strategy, values='Market_Value_AUD', names='Strategy Role', hole=0.4,
                         color_discrete_map={'Core':'#00cc96', 'Satellite':'#636efa', 'Speculative':'#EF553B'})
            fig4.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig4, use_container_width=True)

    # 跨平台運算
    ticker_values = df_updated.groupby('Ticker')['Market_Value_AUD'].sum().reset_index()
    ticker_values.rename(columns={'Market_Value_AUD': 'Total_Ticker_Value'}, inplace=True)
    
    ticker_targets = df_updated.groupby('Ticker')['Target_Weight'].max().reset_index()
    ticker_targets.rename(columns={'Target_Weight': 'Total_Ticker_Target'}, inplace=True)

    ticker_stats = pd.merge(ticker_values, ticker_targets, on='Ticker')
    ticker_stats['Ticker_Allocation_%'] = ticker_stats['Total_Ticker_Value'] / total_net_worth
    ticker_stats['Global_Drift_%'] = ticker_stats['Ticker_Allocation_%'] - ticker_stats['Total_Ticker_Target']

    df_final = pd.merge(df_updated, ticker_stats[['Ticker', 'Total_Ticker_Target', 'Global_Drift_%']], on='Ticker', how='left')
    df_final['Actual_%'] = df_final['Market_Value_AUD'] / total_net_worth

    # 切換檢視
    view_mode = st.radio("顯示模式 (View Mode)", ["合併檢視 (Summary)", "詳細檢視 (Detailed)"], horizontal=True)

    if view_mode == "合併檢視 (Summary)":
        # 1. 計算原幣別總成本 (Shares * Avg_Cost)
        df_final['Native_Cost_Value'] = df_final['Shares'] * df_final['Avg_Cost']
        
        summary_df = df_final.groupby('Ticker').agg({
            'Shares': 'sum',
            'Native_Cost_Value': 'sum', # 用來算加權平均
            'Total_Cost_AUD': 'sum',
            'Market_Value_AUD': 'sum',
            'Unrealized_PnL': 'sum',
            'Total_Ticker_Target': 'max',
            'Global_Drift_%': 'first',
            'Current_Price': 'mean'
        }).reset_index()
        
        # 2. 計算加權平均成本 = 總原幣成本 / 總股數
        summary_df['Avg_Cost'] = summary_df['Native_Cost_Value'] / summary_df['Shares']
        
        summary_df['Actual_%'] = summary_df['Market_Value_AUD'] / total_net_worth
        
        # 3. 把 Avg_Cost 加入顯示欄位
        display_cols = ['Ticker', 'Shares', 'Avg_Cost', 'Current_Price', 'Total_Cost_AUD', 'Market_Value_AUD', 'Unrealized_PnL', 'Actual_%', 'Total_Ticker_Target', 'Global_Drift_%']
        display_df = summary_df[display_cols].copy()
    else:
        display_cols = ['Ticker', 'Platform', 'Shares', 'Avg_Cost', 'Current_Price', 'Total_Cost_AUD', 'Market_Value_AUD', 'Unrealized_PnL', 'Actual_%', 'Total_Ticker_Target', 'Global_Drift_%', 'Stop_Loss_Price', 'Dist_to_Stop']
        display_df = df_final[display_cols].copy()

    # 索引優化 (從1開始)
    display_df = display_df.reset_index(drop=True)
    display_df.index = display_df.index + 1

    # Total Row
    t_row = {col: None for col in display_cols} 
    t_row['Ticker'] = 'TOTAL'
    t_row['Total_Cost_AUD'] = display_df['Total_Cost_AUD'].sum()
    t_row['Market_Value_AUD'] = display_df['Market_Value_AUD'].sum()
    t_row['Unrealized_PnL'] = display_df['Unrealized_PnL'].sum()
    t_row['Actual_%'] = display_df['Actual_%'].sum()
    unique_targets_sum = ticker_targets['Total_Ticker_Target'].sum()
    t_row['Total_Ticker_Target'] = unique_targets_sum
    
    total_df = pd.DataFrame([t_row])
    total_df.index = [''] 
    
    display_df = pd.concat([display_df, total_df])

    # 樣式設定
    def style_dataframe(row):
        styles = [''] * len(row)
        if row['Ticker'] == 'TOTAL':
            return ['font-weight: bold; background-color: #f0f2f6'] * len(row)
        
        if 'Stop_Loss_Price' in row and row['Ticker'] != 'Cash' and row['Ticker'] != 'TOTAL':
            try:
                stop = float(row['Stop_Loss_Price'])
                curr = float(row['Current_Price'])
                if stop > 0 and curr < stop:
                    return ['background-color: #ffcccc; color: black'] * len(row)
            except:
                pass
        return styles

    def color_drift(val):
        if isinstance(val, (int, float)):
            if val > 0.005: return 'color: green; font-weight: bold'
            if val < -0.005: return 'color: red; font-weight: bold'
        return ''

    def color_pnl(val):
        if isinstance(val, (int, float)):
            return 'color: green' if val > 0 else 'color: red'
        return ''
    
    def color_dist(val):
        if isinstance(val, (int, float)):
            if 0 < val < 0.05: return 'color: orange; font-weight: bold'
        return ''

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
        .applymap(color_pnl, subset=['Unrealized_PnL'])
        .applymap(color_drift, subset=['Global_Drift_%'])
        .applymap(color_dist, subset=['Dist_to_Stop'] if 'Dist_to_Stop' in display_df.columns else None)
    )

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
