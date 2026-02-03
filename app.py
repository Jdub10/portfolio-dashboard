import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go

# --- 1. 頁面設定 (必須放在第一行) ---
st.set_page_config(page_title="James' Portfolio", layout="wide", page_icon="💎")

# ==========================================
# 🎨 CSS 高級視覺優化 (High Class Styling)
# ==========================================
st.markdown("""
<style>
    /* 全局字體設定 */
    html, body, [class*="css"] {
        font-family: 'Helvetica Neue', 'Arial', sans-serif;
        font-weight: 300;
    }
    
    /* 頂部留白調整 */
    .block-container {
        padding-top: 3rem;
        padding-bottom: 5rem;
    }

    /* KPI 卡片樣式 */
    div[data-testid="stMetric"] {
        background-color: #f8f9fa; /* 淺灰背景 */
        padding: 15px 20px;
        border-radius: 12px;
        border: 1px solid #e9ecef;
        box-shadow: 0 4px 6px rgba(0,0,0,0.02); /* 極淡的陰影 */
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px); /* 滑鼠懸停微浮效果 */
        box-shadow: 0 6px 12px rgba(0,0,0,0.05);
    }
    
    /* 標題樣式 */
    h1 {
        font-weight: 600 !important;
        color: #1a1a1a;
        letter-spacing: -1px;
    }
    h3 {
        font-weight: 500 !important;
        color: #4a4a4a;
        margin-top: 20px !important;
    }

    /* 表格樣式優化 */
    .dataframe {
        font-size: 14px !important;
        font-family: 'Roboto Mono', monospace;
    }
    
    /* 去除一些雜訊 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🔐 密碼保護功能
# ==========================================
def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        if st.session_state["password"] == st.secrets["PASSWORD"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("PASSWORD", type="password", on_change=password_entered, key="password", placeholder="Enter access code")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("ACCESS DENIED", type="password", on_change=password_entered, key="password", placeholder="Try again")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ==========================================
# 🚀 主程式開始
# ==========================================

SHEET_URL = "https://docs.google.com/spreadsheets/d/14IGIMj9iR5qOtmYT1e6FgN8t2tdQ5M1R_-hS6rw1RQs/export?format=csv"

# 定義高級配色盤 (High Class Palette)
# 深藍、 slate、 灰藍、 金色點綴
LUXURY_COLORS = ['#2E4053', '#5D6D7E', '#85929E', '#AED6F1', '#F5B041', '#EC7063', '#48C9B0', '#AF7AC5']

@st.cache_data(ttl=60)
def load_and_clean_data():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = df.columns.str.strip()
        
        required_cols = ['Shares', 'Avg_Cost', 'Target_Weight']
        for col in required_cols:
            if col not in df.columns:
                st.error(f"❌ Missing Column: {col}")
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
        st.error(f"Data Error: {e}")
        return pd.DataFrame()

def fetch_live_data(df):
    tickers_list = df[df['Ticker'] != 'Cash']['Ticker'].unique().tolist()
    tickers_list = [t.strip() for t in tickers_list]
    
    if "AUDUSD=X" not in tickers_list:
        tickers_list.append("AUDUSD=X")
    
    try:
        data = yf.download(tickers_list, period="5d", progress=False)
        
        if data.empty:
            st.error("Connection Error: No data received.")
            latest_prices = pd.Series()
        else:
            if 'Close' in data.columns:
                close_data = data['Close']
                latest_prices = close_data.ffill().iloc[-1]
            else:
                latest_prices = data.iloc[-1]
                
    except Exception as e:
        st.error(f"API Error: {e}")
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
            names_str = ", ".join(others_names[:3]) + "..."
        else:
            names_str = ", ".join(others_names)
        label = f"Others ({names_str})"
        new_row = {name_col: label, value_col: others_val}
        df_others = pd.DataFrame([new_row])
        df_final = pd.concat([df_main, df_others], ignore_index=True)
        return df_final
    else:
        return df_main

# --- 🎨 高級圖表繪製函數 ---
def plot_luxury_pie(df, values, names, title):
    fig = px.pie(df, values=values, names=names, hole=0.6, # 甜甜圈洞大一點比較時尚
                 color_discrete_sequence=LUXURY_COLORS) 
    
    fig.update_layout(
        title=dict(text=title, font=dict(size=18, color="#333"), x=0.5, xanchor='center'),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5), # 圖例放下
        margin=dict(t=50, b=50, l=20, r=20),
        paper_bgcolor='rgba(0,0,0,0)', # 透明背景
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(family="Helvetica Neue", size=13)
    )
    fig.update_traces(
        textposition='outside', 
        textinfo='percent+label',
        marker=dict(line=dict(color='#FFFFFF', width=2)) # 白色邊框讓切片分離
    )
    return fig

# --- 主介面 ---
st.title("Portfolio Overview") # 簡潔標題

if st.button('Refresh Data', type="primary"): # 使用 Primary 樣式按鈕
    st.cache_data.clear()

df_raw = load_and_clean_data()

if not df_raw.empty:

    capital_row = df_raw[df_raw['Ticker'] == 'CAPITAL']
    if not capital_row.empty:
        CAPITAL_INJECTED = capital_row['Shares'].sum()
        df_raw = df_raw[df_raw['Ticker'] != 'CAPITAL']
    else:
        CAPITAL_INJECTED = 743564 

    with st.spinner('Updating Market Data...'):
        df_updated, fx_rate = fetch_live_data(df_raw)

    total_net_worth = df_updated['Market_Value_AUD'].sum()
    unrealized_pnl = total_net_worth - CAPITAL_INJECTED
    pnl_pct = (unrealized_pnl / CAPITAL_INJECTED) * 100 if CAPITAL_INJECTED > 0 else 0

    # KPI 區塊
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Net Worth (AUD)", f"${total_net_worth:,.0f}")
    col2.metric("Capital Injected", f"${CAPITAL_INJECTED:,.0f}")
    col3.metric("Unrealized PnL", f"${unrealized_pnl:,.0f}", f"{pnl_pct:.2f}%")
    col4.metric("FX Rate (AUD/USD)", f"{fx_rate:.4f}")

    st.markdown("---")

    # ==========================================
    # 📊 第一排圖表：資金分佈 (Luxury)
    # ==========================================
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("Asset Allocation (Incl. Cash)")
        df_incl_cash = df_updated.groupby('Ticker')['Market_Value_AUD'].sum().reset_index()
        df_incl_cash_opt = group_small_holdings(df_incl_cash, threshold=0.80)
        
        fig1 = plot_luxury_pie(df_incl_cash_opt, 'Market_Value_AUD', 'Ticker', f"Total: ${total_net_worth:,.0f}")
        st.plotly_chart(fig1, use_container_width=True, height=550)

    with col_chart2:
        st.subheader("Equity Allocation (Excl. Cash)")
        df_excl_cash = df_updated[df_updated['Ticker'] != 'Cash'].groupby('Ticker')['Market_Value_AUD'].sum().reset_index()
        df_excl_cash_opt = group_small_holdings(df_excl_cash, threshold=0.80)
        equity_total = df_excl_cash['Market_Value_AUD'].sum()
        
        fig2 = plot_luxury_pie(df_excl_cash_opt, 'Market_Value_AUD', 'Ticker', f"Equity: ${equity_total:,.0f}")
        st.plotly_chart(fig2, use_container_width=True, height=550)

    # ==========================================
    # 📊 第二排圖表：戰略配置 (Luxury)
    # ==========================================
    col_chart3, col_chart4 = st.columns(2)
    df_equity = df_updated[df_updated['Ticker'] != 'Cash'] 
    
    with col_chart3:
        st.subheader("Sector Exposure")
        if 'Sector' in df_equity.columns:
            df_sector = df_equity.groupby('Sector')['Market_Value_AUD'].sum().reset_index().sort_values('Market_Value_AUD', ascending=False)
            fig3 = plot_luxury_pie(df_sector, 'Market_Value_AUD', 'Sector', "By Sector")
            st.plotly_chart(fig3, use_container_width=True, height=550)

    with col_chart4:
        st.subheader("Strategy Roles")
        if 'Strategy Role' in df_equity.columns:
            df_strategy = df_equity.groupby('Strategy Role')['Market_Value_AUD'].sum().reset_index().sort_values('Market_Value_AUD', ascending=False)
            # 戰略角色可以用特定的顏色，讓它更直觀
            fig4 = px.pie(df_strategy, values='Market_Value_AUD', names='Strategy Role', hole=0.6,
                         color_discrete_map={'Core':'#2E4053', 'Satellite':'#5D6D7E', 'Speculative':'#EC7063'})
            fig4.update_layout(
                title=dict(text="By Role", font=dict(size=18), x=0.5, xanchor='center'),
                showlegend=True,
                legend=dict(orientation="h", y=-0.2, x=0.5, xanchor='center'),
                margin=dict(t=50, b=50, l=20, r=20),
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(family="Helvetica Neue", size=13)
            )
            fig4.update_traces(textposition='outside', textinfo='percent+label', marker=dict(line=dict(color='#FFFFFF', width=2)))
            st.plotly_chart(fig4, use_container_width=True, height=550)

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
    st.subheader("Holdings Detail")
    view_mode = st.radio("", ["Summary View", "Detailed View"], horizontal=True, label_visibility="collapsed") # 隱藏標籤，更簡潔

    if view_mode == "Summary View":
        df_final['Native_Cost_Value'] = df_final['Shares'] * df_final['Avg_Cost']
        
        summary_df = df_final.groupby('Ticker').agg({
            'Shares': 'sum',
            'Native_Cost_Value': 'sum', 
            'Total_Cost_AUD': 'sum',
            'Market_Value_AUD': 'sum',
            'Unrealized_PnL': 'sum',
            'Total_Ticker_Target': 'max',
            'Global_Drift_%': 'first',
            'Current_Price': 'mean'
        }).reset_index()
        
        summary_df['Avg_Cost'] = summary_df['Native_Cost_Value'] / summary_df['Shares']
        summary_df['Actual_%'] = summary_df['Market_Value_AUD'] / total_net_worth
        
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

    # 樣式設定 (極簡風)
    def style_dataframe(row):
        styles = [''] * len(row)
        if row['Ticker'] == 'TOTAL':
            return ['font-weight: bold; background-color: #f0f2f6; border-top: 2px solid #ccc'] * len(row)
        
        if 'Stop_Loss_Price' in row and row['Ticker'] != 'Cash' and row['Ticker'] != 'TOTAL':
            try:
                stop = float(row['Stop_Loss_Price'])
                curr = float(row['Current_Price'])
                if stop > 0 and curr < stop:
                    # 改用更優雅的淡紅色背景
                    return ['background-color: #fff5f5; color: #c0392b; font-weight: 500'] * len(row)
            except:
                pass
        return styles

    def color_drift(val):
        if isinstance(val, (int, float)):
            if val > 0.005: return 'color: #27ae60; font-weight: bold' # 翡翠綠
            if val < -0.005: return 'color: #c0392b; font-weight: bold' # 寶石紅
        return ''

    def color_pnl(val):
        if isinstance(val, (int, float)):
            return 'color: #27ae60' if val > 0 else 'color: #c0392b'
        return ''
    
    def color_dist(val):
        if isinstance(val, (int, float)):
            if 0 < val < 0.05: return 'color: #d35400; font-weight: bold' # 焦糖橘
        return ''

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

    # 行動建議 (使用簡潔的卡片)
    st.markdown("### Action Plan")
    action_tickers = ticker_stats[ticker_stats['Global_Drift_%'] < -0.005]
    if not action_tickers.empty:
        for _, row in action_tickers.iterrows():
            shortfall = abs(row['Global_Drift_%']) * total_net_worth
            st.info(f"🔹 **Buy {row['Ticker']}**: Add approx. **${shortfall:,.0f} AUD** to reach target.")
    else:
        st.success("✨ Portfolio is perfectly balanced.")

else:
    st.info("⏳ Waiting for data connection...")
