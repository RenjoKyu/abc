from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import yfinance as yf
import pandas as pd
from datetime import datetime
from typing import List, Optional

# สร้าง Instance ของ FastAPI
app = FastAPI(
    title="Stock Hunter API",
    description="API สำหรับค้นหาแนวรับเชิงกลยุทธ์ (Price Action & Fractal)",
    version="1.0.0"
)

# กำหนดรูปแบบข้อมูล Input
class StockRequest(BaseModel):
    symbol: str

# กำหนดรูปแบบข้อมูล Output (Response Model)
class BuyLevel(BaseModel):
    order: int
    price: float
    weight_percent: int
    discount_from_high_pct: float
    gap_from_current_pct: float

class StockAnalysisResponse(BaseModel):
    symbol: str
    company_name: str
    analysis_date: str
    current_price: float
    year_high: float
    year_low: float
    status: str
    strategic_plan: List[BuyLevel]

@app.get("/")
def read_root():
    return {"message": "Welcome to Stock Hunter API. Go to /docs to test."}

@app.post("/analyze", response_model=StockAnalysisResponse)
def analyze_stock(request: StockRequest):
    symbol = request.symbol.upper()
    search_date = datetime.now().strftime("%d/%m/%Y")
    
    ticker = yf.Ticker(symbol)
    
    # ดึงชื่อบริษัท (Optional: อาจจะช้าในบางครั้ง ใส่ Try/Except ไว้)
    try:
        # info อาจจะดึงช้า เราอาจจะข้ามไปหากต้องการความเร็วสูงสุด
        full_name = ticker.info.get('longName', symbol)
    except:
        full_name = symbol

    # ดึงข้อมูลย้อนหลัง 5 ปี รายสัปดาห์
    df = ticker.history(period="5y", interval="1wk")
    
    if df.empty:
        raise HTTPException(status_code=404, detail=f"ไม่พบข้อมูลหุ้น '{symbol}'")

    current_price = df['Close'].iloc[-1]
    
    # คำนวณ High/Low 52 สัปดาห์
    one_year_df = df.tail(52)
    one_year_high = one_year_df['High'].max()
    one_year_low = one_year_df['Low'].min()

    # --- Logic หาแนวรับ (Fractal) จากโค้ดเดิม ---
    levels = []
    # ต้องเช็คว่าข้อมูลมีเพียงพอหรือไม่
    if len(df) > 5:
        for i in range(2, len(df)-2):
            low_val = df['Low'].iloc[i]
            # Fractal Low Logic
            if (low_val < df['Low'].iloc[i-1] and 
                low_val < df['Low'].iloc[i-2] and 
                low_val < df['Low'].iloc[i+1] and 
                low_val < df['Low'].iloc[i+2]):
                levels.append(low_val)
    
    # Grouping (Consolidated)
    consolidated = []
    if levels:
        levels.sort()
        while levels:
            base = levels.pop(0)
            group = [base]
            keep = []
            for x in levels:
                if x <= base * 1.05: # รวมถ้าราคาต่างกันไม่เกิน 5%
                    group.append(x)
                else:
                    keep.append(x)
            levels = keep
            # เก็บค่าเฉลี่ย และ จำนวนครั้งที่สัมผัส (Strength)
            consolidated.append((sum(group)/len(group), len(group)))
            
    # Filter เฉพาะราคาที่ต่ำกว่าปัจจุบัน
    waiting = [l for l in consolidated if l[0] < current_price]
    waiting.sort(key=lambda x: x[0], reverse=True) # เรียงจากมากไปน้อย (ใกล้ราคาปัจจุบันสุดก่อน)
    top_3 = waiting[:3]

    strategic_plan = []
    
    if not top_3:
        status_msg = "ราคาปัจจุบันต่ำที่สุดในรอบ 5 ปี หรือไม่พบแนวรับ"
    else:
        status_msg = "Found Strategic Levels"
        total_strength = sum(l[1] for l in top_3)

        for i, (price, count) in enumerate(top_3):
            weight = round((count / total_strength) * 100)
            
            # คำนวณ Percent ต่างๆ
            discount_pct = ((one_year_high - price) / one_year_high) * 100
            gap = ((current_price - price) / current_price) * 100
            
            strategic_plan.append(BuyLevel(
                order=i+1,
                price=round(price, 2),
                weight_percent=weight,
                discount_from_high_pct=round(discount_pct, 2),
                gap_from_current_pct=round(gap, 2)
            ))

    return StockAnalysisResponse(
        symbol=symbol,
        company_name=full_name,
        analysis_date=search_date,
        current_price=round(current_price, 2),
        year_high=round(one_year_high, 2),
        year_low=round(one_year_low, 2),
        status=status_msg,
        strategic_plan=strategic_plan
    )