import streamlit as st
import pandas as pd
import sqlalchemy
import plotly.express as px

# ==========================================
# ⚙️ 1. ตั้งค่าหน้าเพจ
# ==========================================
st.set_page_config(page_title="AuraTrend Pro Dashboard", page_icon="📈", layout="wide")
st.title("📊 AuraTrend Pro - Command Dashboard")
st.markdown("ศูนย์บัญชาการติดตามผลการเทรดของระบบ AI อัตโนมัติ")

# ==========================================
# 🗄️ 2. ดึงข้อมูลจากฐานข้อมูล Cloud (PostgreSQL)
# ==========================================
def load_data():
    # 🌟 สำคัญ: เอา URL ของ Railway มาวางแทนตรงนี้นะครับ! 🌟
    # (อย่าลืมแก้คำว่า postgres:// เป็น postgresql://)
    DB_URL = "postgresql://postgres:รหัสผ่านของคุณ@ที่อยู่.railway.app:5432/railway"
    
    engine = sqlalchemy.create_engine(DB_URL)
    
    try:
        df = pd.read_sql_query("SELECT * FROM reports", engine)
        if not df.empty:
            df['closed_at'] = pd.to_datetime(df['closed_at'])
        return df
    except Exception as e:
        # ถ้าตารางยังไม่มีข้อมูล ให้ไม่ Error แต่โชว์ตารางว่างแทน
        return pd.DataFrame()

df = load_data()

# ==========================================
# 🖥️ 3. แสดงผลบนเว็บ (UI)
# ==========================================
if df.empty:
    st.warning("⚠️ ยังไม่มีข้อมูลการเทรดส่งเข้ามาในระบบครับท่านนายพล!")
else:
    # --- ส่วนที่ 1: สรุปภาพรวม (Metrics) ---
    st.subheader("🏆 สรุปผลงานรวม (Overview)")
    
    total_profit = df['profit'].sum()
    max_dd_overall = df['max_dd'].min() # หาค่าที่ติดลบเยอะที่สุด
    total_baskets = len(df)
    win_rate = (len(df[df['profit'] > 0]) / total_baskets) * 100 if total_baskets > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Total Profit ($)", f"{total_profit:.2f}")
    col2.metric("📉 Max Drawdown ($)", f"{max_dd_overall:.2f}")
    col3.metric("🧺 Baskets Closed", f"{total_baskets}")
    col4.metric("🎯 Win Rate (%)", f"{win_rate:.1f}%")

    st.markdown("---")

    # --- ส่วนที่ 2: กราฟ (Charts) ---
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        st.subheader("📈 กราฟการเติบโตของพอร์ต (Equity Curve)")
        df['cumulative_profit'] = df['profit'].cumsum()
        fig_equity = px.line(df, x='closed_at', y='cumulative_profit', markers=True, 
                             labels={'closed_at': 'เวลาที่ปิดออเดอร์', 'cumulative_profit': 'กำไรสะสม ($)'})
        st.plotly_chart(fig_equity, use_container_width=True)

    with col_chart2:
        st.subheader("📊 สถิติเหตุผลการปิดออเดอร์")
        reason_counts = df['close_reason'].value_counts().reset_index()
        reason_counts.columns = ['close_reason', 'count']
        fig_pie = px.pie(reason_counts, values='count', names='close_reason', hole=0.4,
                         color='close_reason', color_discrete_map={'AUTO_CLOSE':'#00CC96', 'MANUAL_CLOSE':'#EF553B'})
        st.plotly_chart(fig_pie, use_container_width=True)

    st.markdown("---")

    # --- ส่วนที่ 3: ตารางข้อมูลแบบเจาะลึก (Data Table) ---
    st.subheader("📋 ประวัติการเทรดล่าสุด (Trade Logs)")
    
    display_df = df[['closed_at', 'mt5_account', 'profit', 'max_dd', 'total_orders', 'close_reason']].copy()
    display_df = display_df.sort_values(by='closed_at', ascending=False)
    display_df.columns = ['เวลา (UTC)', 'เลขพอร์ต', 'กำไร ($)', 'Max DD ($)', 'จำนวนไม้ที่ใช้', 'สาเหตุการปิด']
    
    st.dataframe(display_df, use_container_width=True)
    
    if st.button("🔄 อัปเดตข้อมูลล่าสุด"):
        st.rerun()
