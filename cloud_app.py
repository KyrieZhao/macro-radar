import streamlit as st
import pandas as pd
import pandas_datareader.data as web
import yfinance as yf # 👈 云端神器，免代理
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ==========================================
# 🔧 网页配置 (云端版)
# ==========================================
st.set_page_config(
    page_title="Macro Radar (Global)",
    page_icon="📡",
    layout="wide"
)

# ⚠️ 严禁在这里写 os.environ 代理设置，否则会导致云端服务器死机

# ==========================================
# 📥 数据获取
# ==========================================

def get_realtime_btc_price():
    """获取实时 BTC 价格（不缓存）"""
    try:
        # 使用 yf.download 获取最近 5 天数据，更可靠
        end = datetime.datetime.now()
        start = end - datetime.timedelta(days=5)
        data = yf.download('BTC-USD', start=start, end=end, progress=False)

        # 处理 MultiIndex 列名
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)

        if len(data) >= 2:
            current_price = float(data['Close'].iloc[-1])
            prev_price = float(data['Close'].iloc[-2])
            change_24h = ((current_price - prev_price) / prev_price) * 100
            return current_price, change_24h
        elif len(data) == 1:
            return float(data['Close'].iloc[-1]), 0.0
        return None, None
    except Exception:
        return None, None

@st.cache_data(ttl=3600)
def get_market_data(start_date, end_date):
    # 1. 美联储数据 (FRED)
    # 云端服务器可以直接连接 FRED
    
    try:
        fred_data = web.DataReader(['WALCL', 'WTREGEN', 'RRPONTSYD'], 'fred', start_date, end_date)
        fred_data = fred_data.ffill().dropna()
        fred_data['Net_Liquidity'] = (fred_data['WALCL'] - fred_data['WTREGEN'] - fred_data['RRPONTSYD']) / 1000
    except Exception as e:
        st.error(f"美联储数据获取失败: {e}")
        return None
    
    # 2. 比特币数据 (Yahoo Finance)
    # yfinance 在云端最稳定
    try:
        btc_data = yf.download('BTC-USD', start=start_date, end=end_date, progress=False)
        btc_data.index = btc_data.index.tz_localize(None)

        # 修复 yfinance 新版本 MultiIndex 列名问题
        if isinstance(btc_data.columns, pd.MultiIndex):
            btc_data.columns = btc_data.columns.get_level_values(0)

        btc_df = btc_data[['Close']].copy()
    except Exception as e:
        st.error(f"比特币数据获取失败: {e}")
        return None
    
    # 3. 合并
    df = pd.merge(fred_data[['Net_Liquidity']], btc_df, left_index=True, right_index=True, how='inner')
    df.rename(columns={'Close': 'BTC_Price'}, inplace=True)
    
    return df

# ==========================================
# 🧮 信号计算 (保持原逻辑)
# ==========================================
def calculate_signal(df):
    df['Liq_SMA_20'] = df['Net_Liquidity'].rolling(window=20).mean()
    df['BTC_SMA_20'] = df['BTC_Price'].rolling(window=20).mean()
    df['Correlation'] = df['Net_Liquidity'].rolling(window=30).corr(df['BTC_Price'])

    def get_status(row):
        liq_trend_up = row['Net_Liquidity'] > row['Liq_SMA_20']
        btc_trend_up = row['BTC_Price'] > row['BTC_SMA_20']
        high_corr = row['Correlation'] > 0.5
        
        if liq_trend_up and btc_trend_up and high_corr: return "🟢 STRONG LONG"
        elif not liq_trend_up and btc_trend_up: return "🔴 DIVERGENCE (Risk)"
        elif liq_trend_up and not btc_trend_up: return "🟡 BUY OPPORTUNITY"
        else: return "⚪ NEUTRAL"

    df['Signal'] = df.apply(get_status, axis=1)
    return df

# ==========================================
# 🖥️ 界面渲染
# ==========================================
st.title("📡 Macro Radar (Cloud Edition)")
st.markdown("全球流动性雷达 | 实时云端部署版")

# ==========================================
# 🎛️ 侧边栏配置
# ==========================================
with st.sidebar:
    st.header("⚙️ Settings")

    # 日期范围选择器 - 默认显示2018年以来的数据
    default_start = datetime.datetime(2018, 1, 1)
    default_end = datetime.datetime.now()

    start_date = st.date_input(
        "Start Date",
        value=default_start,
        max_value=default_end
    )

    end_date = st.date_input(
        "End Date",
        value=default_end,
        min_value=start_date,
        max_value=datetime.datetime.now()
    )

    # 刷新按钮
    if st.button("🔄 Refresh Data"):
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")
    st.markdown("### 📊 Data Export")

# ==========================================
# 📊 数据加载和处理
# ==========================================
with st.spinner('正在连接全球服务器...'):
    start_str = start_date.strftime('%Y-%m-%d')
    end_str = end_date.strftime('%Y-%m-%d')

    raw_df = get_market_data(start_str, end_str)
    if raw_df is not None:
        df = calculate_signal(raw_df)
        latest = df.iloc[-1]

        # 获取实时 BTC 价格
        realtime_price, change_24h = get_realtime_btc_price()

        # 指标卡
        c1, c2, c3, c4 = st.columns(4)

        # 实时 BTC 价格显示
        if realtime_price is not None:
            c1.metric(
                "BTC Price (Live)",
                f"${realtime_price:,.0f}",
                delta=f"{change_24h:+.2f}%" if change_24h is not None else None
            )
        else:
            c1.metric("BTC Price", f"${latest['BTC_Price']:,.0f}")

        c2.metric("Net Liquidity", f"${latest['Net_Liquidity']:,.2f} B")
        c3.metric("Correlation", f"{latest['Correlation']:.2f}")
        c4.info(f"Signal: {latest['Signal']}")

        # ==========================================
        # 📊 流动性对比图表 (自适应屏幕)
        # ==========================================
        st.subheader("📊 Liquidity vs BTC Correlation")

        # 图表 - 自适应高度，添加范围选择器
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Scatter(x=df.index, y=df['Net_Liquidity'], name="Liquidity", fill='tozeroy', line=dict(color='rgba(0, 180, 255, 0.5)')), secondary_y=False)
        fig.add_trace(go.Scatter(x=df.index, y=df['BTC_Price'], name="BTC", line=dict(color='#F7931A', width=2)), secondary_y=True)

        fig.update_layout(
            template="plotly_dark",
            height=700,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            margin=dict(l=60, r=60, t=40, b=60),
            xaxis=dict(
                rangeslider=dict(visible=True, thickness=0.05),
                rangeselector=dict(
                    buttons=list([
                        dict(count=1, label="1M", step="month", stepmode="backward"),
                        dict(count=3, label="3M", step="month", stepmode="backward"),
                        dict(count=6, label="6M", step="month", stepmode="backward"),
                        dict(count=1, label="1Y", step="year", stepmode="backward"),
                        dict(count=2, label="2Y", step="year", stepmode="backward"),
                        dict(count=3, label="3Y", step="year", stepmode="backward"),
                        dict(count=5, label="5Y", step="year", stepmode="backward"),
                        dict(step="all", label="ALL")
                    ]),
                    bgcolor="rgba(50,50,50,0.8)",
                    activecolor="#F7931A",
                    font=dict(color="white")
                )
            )
        )

        fig.update_yaxes(title_text="Net Liquidity ($B)", secondary_y=False)
        fig.update_yaxes(title_text="BTC Price ($)", secondary_y=True)

        st.plotly_chart(fig, use_container_width=True)

        # ==========================================
        # 📋 历史信号表
        # ==========================================
        st.subheader("📋 Recent Signal History")

        # 显示最近30天的信号
        recent_signals = df[['BTC_Price', 'Net_Liquidity', 'Correlation', 'Signal']].tail(30).copy()
        recent_signals.index = recent_signals.index.strftime('%Y-%m-%d')
        recent_signals['BTC_Price'] = recent_signals['BTC_Price'].apply(lambda x: f"${x:,.0f}")
        recent_signals['Net_Liquidity'] = recent_signals['Net_Liquidity'].apply(lambda x: f"${x:,.2f}B")
        recent_signals['Correlation'] = recent_signals['Correlation'].apply(lambda x: f"{x:.2f}")

        st.dataframe(
            recent_signals.iloc[::-1],  # 倒序显示，最新的在上面
            use_container_width=True,
            height=400
        )

        # ==========================================
        # 💾 数据导出
        # ==========================================
        with st.sidebar:
            # CSV导出
            csv = df.to_csv().encode('utf-8')
            st.download_button(
                label="📥 Download Full Data (CSV)",
                data=csv,
                file_name=f"macro_radar_{start_str}_to_{end_str}.csv",
                mime="text/csv",
            )