from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import datetime
import uuid
import uvicorn

# ==========================================
# ⚙️ 1. ตั้งค่าฐานข้อมูล (SQLite) และ Admin Key
# ==========================================
ADMIN_SECRET_KEY = "SuperSecretAura2026" 
DATABASE_URL = "sqlite:///./aura_database.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==========================================
# 🗄️ 2. ออกแบบตารางในฐานข้อมูล (Database Models)
# ==========================================
class DBToken(Base):
    __tablename__ = "tokens"
    id = Column(Integer, primary_key=True, index=True)
    token_string = Column(String, unique=True, index=True) 
    mt5_account = Column(String, nullable=True)            
    valid_days = Column(Integer)                           
    activated_at = Column(DateTime, nullable=True)         
    is_active = Column(Boolean, default=True)              

class DBReport(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    mt5_account = Column(String, index=True)
    token_string = Column(String)
    profit = Column(Float)            
    max_dd = Column(Float)            
    total_orders = Column(Integer)    
    close_reason = Column(String, default="AUTO_CLOSE") # 🌟 เพิ่มคอลัมน์นี้แล้ว
    closed_at = Column(DateTime, default=datetime.datetime.utcnow)

# 🌟 สั่งสร้างตารางใหม่ (ถ้ายังไม่มี)
Base.metadata.create_all(bind=engine)

# ==========================================
# 📦 3. รูปแบบการรับส่งข้อมูล (Pydantic Schemas)
# ==========================================
class TokenCreate(BaseModel):
    valid_days: int = 30  

class BotVerify(BaseModel):
    token_string: str
    mt5_account: str

class BotReport(BaseModel):
    token_string: str
    mt5_account: str
    profit: float
    max_dd: float
    total_orders: int
    close_reason: str  # 🌟 รับค่าสาเหตุการปิดจาก MT5

# ==========================================
# 🚀 4. สร้าง API Server (FastAPI)
# ==========================================
app = FastAPI(title="AuraTrend Pro - Command Center")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def verify_admin(x_admin_key: str = Header(...)):
    if x_admin_key != ADMIN_SECRET_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized: รหัส Admin ไม่ถูกต้อง!")

# ------------------------------------------
# 👑 โซนของ ADMIN (ต้องใช้ ADMIN_SECRET_KEY)
# ------------------------------------------
@app.post("/admin/create_token", tags=["Admin"])
def create_token(data: TokenCreate, db: Session = Depends(get_db), admin: str = Depends(verify_admin)):
    """[Admin] สร้าง Token ใหม่แบบสุ่ม"""
    new_token_str = f"AURA-{str(uuid.uuid4())[:8].upper()}" 
    new_token = DBToken(token_string=new_token_str, valid_days=data.valid_days)
    db.add(new_token)
    db.commit()
    db.refresh(new_token)
    return {"message": "สร้าง Token สำเร็จ!", "token": new_token_str, "valid_days": data.valid_days}

# ------------------------------------------
# 🤖 โซนของ USER / บอท MT5 (ไม่ต้องใช้รหัส Admin)
# ------------------------------------------
@app.post("/bot/verify", tags=["MT5 Bot"])
def verify_bot(data: BotVerify, db: Session = Depends(get_db)):
    """[MT5] ตรวจสอบ Token และผูกเข้ากับเลขพอร์ต (ใช้ครั้งแรก)"""
    db_token = db.query(DBToken).filter(DBToken.token_string == data.token_string).first()
    
    if not db_token:
        raise HTTPException(status_code=404, detail="ไม่พบ Token นี้ในระบบ!")
    if not db_token.is_active:
        raise HTTPException(status_code=403, detail="Token นี้ถูกระงับการใช้งาน!")

    if db_token.mt5_account is None:
        db_token.mt5_account = data.mt5_account
        db_token.activated_at = datetime.datetime.utcnow()
        db.commit()
    elif db_token.mt5_account != data.mt5_account:
        raise HTTPException(status_code=403, detail=f"Token นี้ถูกผูกกับพอร์ตอื่นไปแล้ว!")

    if db_token.activated_at:
        expiry_date = db_token.activated_at + datetime.timedelta(days=db_token.valid_days)
        if datetime.datetime.utcnow() > expiry_date:
            raise HTTPException(status_code=403, detail="Token นี้หมดอายุแล้ว!")

    return {"status": "success", "message": "ยืนยันตัวตนผ่าน บอทสามารถทำงานได้!"}

@app.post("/bot/report", tags=["MT5 Bot"])
def report_trade(data: BotReport, db: Session = Depends(get_db)):
    """[MT5] ส่งรายงานสรุปผลเมื่อปิดตะกร้า (Basket Close)"""
    db_token = db.query(DBToken).filter(DBToken.token_string == data.token_string, DBToken.mt5_account == data.mt5_account).first()
    if not db_token:
        raise HTTPException(status_code=403, detail="Token หรือ เลขพอร์ต ไม่ถูกต้อง ไม่สามารถส่งรายงานได้")

    new_report = DBReport(
        mt5_account=data.mt5_account,
        token_string=data.token_string,
        profit=data.profit,
        max_dd=data.max_dd,
        total_orders=data.total_orders,
        close_reason=data.close_reason # 🌟 บันทึกสาเหตุลง Database
    )
    db.add(new_report)
    db.commit()
    return {"status": "success", "message": f"บันทึกรายงาน ({data.close_reason}) สำเร็จ!"}

# ==========================================
# สั่ง Run Server: python server.py
# ==========================================
if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)