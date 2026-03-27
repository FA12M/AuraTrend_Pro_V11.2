import streamlit as st
import pandas as pd
import sqlalchemy
from sqlalchemy import text
import plotly.express as px
import datetime
import uuid

# ==========================================
# ⚙️ 1. ตั้งค่าหน้าเพจ & ฐานข้อมูล
# ==========================================
st.set_page_config(page_title="AuraTrend Pro - Enterprise", page_icon="📈", layout="wide")

# 🌟 เอา URL ของ Railway มาวางตรงนี้ (อย่าลืมเปลี่ยน postgres:// เป็น postgresql://)
DATABASE_URL = "postgresql://postgres:gbGqTyncabrflINNTIEnQlriaKRTzeYo@postgres.railway.internal:5432/railway" 
engine = sqlalchemy.create_engine(DATABASE_URL)

# ==========================================
# 🔐 2. ระบบ Session & Login
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""

def check_login(username, password):
    query = text("SELECT * FROM users WHERE username = :u AND password = :p")
    with engine.connect() as conn:
        result = conn.execute(query, {"u": username, "p": password}).fetchone()
        if result:
            st.session_state.logged_in = True
            st.session_state.username = result[1] # username
            st.session_state.role = result[3]     # role
            st.rerun()
        else:
            st.error("❌ Username หรือ Password ไม่ถูกต้อง!")

def logout():
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.session_state.role = ""
    st.rerun()

# ==========================================
# 🖥️ 3. หน้าจอ Login
# ==========================================
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center;'>🔐 ระบบจัดการกองทุน AuraTrend Pro</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            st.write("ลงชื่อเข้าใช้งาน (Login)")
            user_input = st.text_input("Username")
            pass_input = st.text_input("Password", type="password")
            submitted = st.form_submit_button("เข้าสู่ระบบ 🚀", use_container_width=True)
            if submitted:
                check_login(user_input, pass_input)
    st.stop() # หยุดการรันโค้ดด้านล่างถ้ายังไม่ Login

# --- แถบเมนูด้านข้าง (Sidebar) ---
st.sidebar.title(f"👤 ยินดีต้อนรับ, {st.session_state.username}")
st.sidebar.write(f"สถานะ: **{st.session_state.role}**")
st.sidebar.button("🚪 ออกจากระบบ (Logout)", on_click=logout)

# ==========================================
# 👑 4. หน้าจอของ ADMIN (ผู้ดูแลระบบ)
# ==========================================
if st.session_state.role == "ADMIN":
    st.title("👑 Admin Command Center")
    tab1, tab2, tab3 = st.tabs(["📊 ภาพรวมทั้งหมด", "👥 จัดการ User", "🔑 จัดการ Token"])

    with tab1:
        st.subheader("ผลงานบอทของลูกค้าทุกคน")
        df_reports = pd.read_sql_query("SELECT * FROM reports", engine)
        if not df_reports.empty:
            df_reports['closed_at'] = pd.to_datetime(df_reports['closed_at'])
            st.dataframe(df_reports.sort_values(by='closed_at', ascending=False), use_container_width=True)
        else:
            st.info("ยังไม่มีข้อมูลการเทรดในระบบ")

    with tab2:
        st.subheader("สร้าง User ใหม่ให้ลูกค้า")
        with st.form("create_user"):
            new_user = st.text_input("Username ใหม่")
            new_pass = st.text_input("Password", type="password")
            if st.form_submit_button("สร้าง User"):
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO users (username, password, role) VALUES (:u, :p, 'USER')"), 
                                 {"u": new_user, "p": new_pass})
                st.success(f"สร้าง User: {new_user} สำเร็จ!")
                st.rerun()
                
        st.write("---")
        st.write("รายชื่อ User ในระบบ:")
        df_users = pd.read_sql_query("SELECT id, username, role FROM users", engine)
        st.dataframe(df_users, use_container_width=True)

    with tab3:
        st.subheader("สร้าง Token ให้ลูกค้า")
        df_users_list = pd.read_sql_query("SELECT username FROM users WHERE role='USER'", engine)
        
        with st.form("create_token"):
            user_select = st.selectbox("เลือก User ที่ต้องการมอบ Token ให้", df_users_list['username'].tolist() if not df_users_list.empty else ["ไม่มี User"])
            valid_days = st.number_input("อายุการใช้งาน (วัน)", min_value=1, value=30)
            if st.form_submit_button("เสก Token ✨"):
                new_token_str = f"AURA-{str(uuid.uuid4())[:8].upper()}"
                with engine.begin() as conn:
                    conn.execute(text("INSERT INTO tokens (token_string, owner_username, valid_days, is_active) VALUES (:t, :u, :v, 1)"), 
                                 {"t": new_token_str, "u": user_select, "v": valid_days})
                st.success(f"สร้าง Token สำเร็จ! ส่งรหัสนี้ให้ลูกค้า: {new_token_str}")
                st.rerun()
                
        st.write("---")
        st.write("สถานะ Token ทั้งหมด:")
        df_tokens = pd.read_sql_query("SELECT token_string, owner_username, mt5_account, valid_days, activated_at, is_active FROM tokens", engine)
        st.dataframe(df_tokens, use_container_width=True)

# ==========================================
# 👤 5. หน้าจอของ USER (ลูกค้า / ผู้ใช้งาน)
# ==========================================
elif st.session_state.role == "USER":
    st.title("📊 My Trading Dashboard")
    
    # --- เช็คสถานะ Token ของตัวเอง ---
    st.subheader("🔑 สถานะ License (Token)")
    query_token = f"SELECT token_string, mt5_account, valid_days, activated_at FROM tokens WHERE owner_username='{st.session_state.username}'"
    df_my_tokens = pd.read_sql_query(query_token, engine)
    
    if df_my_tokens.empty:
        st.warning("คุณยังไม่มี Token กรุณาติดต่อ Admin ครับ!")
    else:
        for index, row in df_my_tokens.iterrows():
            if pd.notna(row['activated_at']):
                activated_date = pd.to_datetime(row['activated_at'])
                expiry_date = activated_date + datetime.timedelta(days=row['valid_days'])
                days_left = (expiry_date - datetime.datetime.utcnow()).days
                
                # ระบบเตือนภัย Token ใกล้หมดอายุ
                if days_left <= 1:
                    st.error(f"⚠️ Token ของพอร์ต {row['mt5_account']} จะหมดอายุในอีก {days_left} วัน! (บอทจะหยุดเปิดออเดอร์ใหม่)")
                else:
                    st.success(f"✅ พอร์ต {row['mt5_account']} | เหลือเวลาใช้งาน: {days_left} วัน (หมดอายุ: {expiry_date.strftime('%Y-%m-%d')})")
            else:
                st.info(f"Token: {row['token_string']} (ยังไม่ได้นำไปผูกกับพอร์ต MT5)")

    st.markdown("---")

    # --- ดึงข้อมูลการเทรดเฉพาะของ User นี้ ---
    query_reports = f"SELECT * FROM reports WHERE token_string IN (SELECT token_string FROM tokens WHERE owner_username='{st.session_state.username}')"
    df = pd.read_sql_query(query_reports, engine)
    
    if not df.empty:
        df['closed_at'] = pd.to_datetime(df['closed_at'])
        
        # 🌟 ระบบ Filter แยกโบรกเกอร์ และ จอเทรด (Symbol/Magic)
        st.subheader("🔍 ตัวกรองข้อมูล (Filters)")
        col_f1, col_f2, col_f3 = st.columns(3)
        
        # จัดการค่าว่าง (NaN) ให้เป็นคำว่า "Unknown" เพื่อไม่ให้โค้ดพัง
        df['broker_name'] = df['broker_name'].fillna("Unknown Broker")
        df['symbol'] = df['symbol'].fillna("Unknown Symbol")
        df['magic_number'] = df['magic_number'].fillna("Unknown Magic")
        
        brokers = ["ทั้งหมด"] + df['broker_name'].unique().tolist()
        symbols = ["ทั้งหมด"] + df['symbol'].unique().tolist()
        magics = ["ทั้งหมด"] + df['magic_number'].astype(str).unique().tolist()
        
        filter_broker = col_f1.selectbox("โบรกเกอร์ (Broker)", brokers)
        filter_symbol = col_f2.selectbox("คู่เงิน (Symbol)", symbols)
        filter_magic = col_f3.selectbox("จอเทรด (Magic Number)", magics)
        
        # กรองข้อมูลตามที่เลือก
        filtered_df = df.copy()
        if filter_broker != "ทั้งหมด": filtered_df = filtered_df[filtered_df['broker_name'] == filter_broker]
        if filter_symbol != "ทั้งหมด": filtered_df = filtered_df[filtered_df['symbol'] == filter_symbol]
        if filter_magic != "ทั้งหมด": filtered_df = filtered_df[filtered_df['magic_number'].astype(str) == filter_magic]
        
        st.markdown("---")
        
        # --- แสดงผลสรุปจากข้อมูลที่ถูกกรอง ---
        total_profit = filtered_df['profit'].sum()
        total_baskets = len(filtered_df)
        
        col1, col2 = st.columns(2)
        col1.metric("💰 กำไรรวม (Filtered Profit)", f"${total_profit:.2f}")
        col2.metric("🧺 จำนวนตะกร้าที่ปิด", f"{total_baskets} รอบ")
        
        # กราฟ
        st.subheader("📈 กราฟการเติบโตของพอร์ต")
        filtered_df = filtered_df.sort_values(by='closed_at')
        filtered_df['cumulative_profit'] = filtered_df['profit'].cumsum()
        fig_equity = px.line(filtered_df, x='closed_at', y='cumulative_profit', markers=True)
        st.plotly_chart(fig_equity, use_container_width=True)
        
        st.dataframe(filtered_df[['closed_at', 'broker_name', 'symbol', 'magic_number', 'profit', 'max_dd', 'close_reason']].sort_values(by='closed_at', ascending=False), use_container_width=True)

    else:
        st.info("ยังไม่มีประวัติการเทรดสำหรับบัญชีของคุณครับ")
