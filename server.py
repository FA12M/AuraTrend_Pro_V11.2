from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import datetime
import uuid
import uvicorn

# ==========================================
# ⚙️ 1. ตั้งค่าฐานข้อมูล (รองรับทั้ง SQLite และ PostgreSQL)
# ==========================================
# 🌟 เปลี่ยนตรงนี้เป็น URL ของ Railway (postgresql://...) หรือใช้ sqlite ทดสอบในคอม
DATABASE_URL = "postgresql://postgres:gbGqTyncabrflINNTIEnQlriaKRTzeYo@shinkansen.proxy.rlwy.net:28443/railway"

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 🗄️ 2. ออกแบบตารางในฐานข้อมูล (Database Models)
# ==========================================
class DBUser(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String) 
    role = Column(String, default="USER") # สิทธิ์: ADMIN หรือ USER

class DBToken(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    token_string = Column(String, unique=True, index=True) 
    owner_username = Column(String)                        # 🌟 เจ้าของ Token (User)
    mt5_account = Column(String, nullable=True)            
    valid_days = Column(Integer)                           
    activated_at = Column(DateTime, nullable=True)         
    is_active = Column(Boolean, default=True)              

class DBReport(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    mt5_account = Column(String, index=True)
    token_string = Column(String)
    broker_name = Column(String)      # 🌟 ชื่อโบรกเกอร์
    symbol = Column(String)           # 🌟 คู่เงิน
    magic_number = Column(String)     # 🌟 เลข Magic Number (แยกจอ)
    profit = Column(Float)            
    max_dd = Column(Float)            
    total_orders = Column(Integer)    
    close_reason = Column(String) 
    closed_at = Column(DateTime, default=datetime.datetime.utcnow)

# 🌟 สั่งสร้างตารางใหม่ (และสร้าง Admin ตั้งต้นให้ระบบ)
Base.metadata.create_all(bind=engine)

def init_default_admin():
    db = SessionLocal()
    # ถ้ายังไม่มีใครในระบบเลย ให้สร้าง Admin รหัสผ่านเริ่มต้น (เอาไปล็อกอินใน Dashboard)
    if not db.query(DBUser).filter(DBUser.username == "admin").first():
        admin_user = DBUser(username="admin", password="password123", role="ADMIN")
        db.add(admin_user)
        db.commit()
    db.close()

init_default_admin()

# ==========================================
# 📦 3. รูปแบบการรับส่งข้อมูล (Pydantic Schemas)
# ==========================================
class BotVerify(BaseModel):
    token_string: str
    mt5_account: str

class BotReport(BaseModel):
    token_string: str
    mt5_account: str
    broker_name: str
    symbol: str
    magic_number: str
    profit: float
    max_dd: float
    total_orders: int
    close_reason: str

# ==========================================
# 🚀 4. สร้าง API Server (FastAPI)
# ==========================================
app = FastAPI(title="AuraTrend Pro - Enterprise API")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ------------------------------------------
# 🤖 โซนของ USER / บอท MT5
# ------------------------------------------
@app.post("/bot/verify", tags=["MT5 Bot"])
def verify_bot(data: BotVerify, db: Session = Depends(get_db)):
    """[MT5] ตรวจสอบ Token, ผูกพอร์ต และส่งเวลานับถอยหลังกลับไป"""
    db_token = db.query(DBToken).filter(DBToken.token_string == data.token_string).first()
    
    if not db_token:
        raise HTTPException(status_code=404, detail="ไม่พบ Token นี้ในระบบ!")
    if not db_token.is_active:
        raise HTTPException(status_code=403, detail="Token นี้ถูกระงับการใช้งาน!")

    # ผูกพอร์ตครั้งแรก
    if db_token.mt5_account is None:
        db_token.mt5_account = data.mt5_account
        db_token.activated_at = datetime.datetime.utcnow()
        db.commit()
    elif db_token.mt5_account != data.mt5_account:
        raise HTTPException(status_code=403, detail=f"Token นี้ถูกผูกกับพอร์ตอื่นไปแล้ว!")

    # 🌟 คำนวณเวลาคงเหลือ (Hours Left) เพื่อส่งให้ EA ใช้ทำ Safety Lock
    if db_token.activated_at:
        expiry_date = db_token.activated_at + datetime.timedelta(days=db_token.valid_days)
        hours_left = (expiry_date - datetime.datetime.utcnow()).total_seconds() / 3600.0
        
        if hours_left <= 0:
            raise HTTPException(status_code=403, detail="Token นี้หมดอายุแล้ว!")
            
        return {"status": "success", "message": "ยืนยันตัวตนผ่าน!", "hours_left": hours_left}

    return {"status": "success", "message": "ผูกพอร์ตสำเร็จ!", "hours_left": db_token.valid_days * 24.0}

@app.post("/bot/report", tags=["MT5 Bot"])
def report_trade(data: BotReport, db: Session = Depends(get_db)):
    """[MT5] ส่งรายงานสรุปผลพร้อมข้อมูล Broker และ Symbol"""
    db_token = db.query(DBToken).filter(DBToken.token_string == data.token_string, DBToken.mt5_account == data.mt5_account).first()
    if not db_token:
        raise HTTPException(status_code=403, detail="Token หรือ เลขพอร์ต ไม่ถูกต้อง")

    new_report = DBReport(
        mt5_account=data.mt5_account,
        token_string=data.token_string,
        broker_name=data.broker_name,     # 🌟 บันทึกชื่อโบรก
        symbol=data.symbol,               # 🌟 บันทึกคู่เงิน
        magic_number=data.magic_number,   # 🌟 บันทึกเลขจอ
        profit=data.profit,
        max_dd=data.max_dd,
        total_orders=data.total_orders,
        close_reason=data.close_reason
    )
    db.add(new_report)
    db.commit()
    return {"status": "success", "message": "บันทึกรายงานสำเร็จ!"}

if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
