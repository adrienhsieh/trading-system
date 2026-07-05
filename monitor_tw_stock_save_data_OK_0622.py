import os
import json
import time
import sqlite3
from datetime import datetime
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# ==================== 系統全域內嵌設定區 ====================
STOCK_TARGETS = ["2330", "2317"]  
FETCH_INTERVAL = 5  

FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiYWRyaWVuIiwiZW1haWwiOiJhZHJpZW5oc2llaEBnbWFpbC5jb20iLCJ0b2tlbl92ZXJzaW9uIjoxfQ.BMrXqaq-yrlwwS7h-qpUQuKPeqqc26fhOA6ly_lf7ZA"

LOCAL_DB_FILE = "stock_monitor.db"
EXCEL_FILE = "stock_records.xlsx"

TWSE_TICK_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
FINMIND_TICK_URL = "https://api.finmindtrade.com/api/v4/data"

TWSE_FAILURE_THRESHOLD = 3
FINMIND_FAILURE_THRESHOLD = 3

sqlite_engine = create_engine(f"sqlite:///{LOCAL_DB_FILE}")
SqliteSession = sessionmaker(bind=sqlite_engine)

Base = declarative_base()

twse_failure_count = 0      
finmind_failure_count = 0   
current_channel = "TWSE"     
excel_buffer = []           

def create_session_with_retry():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

class StockLog(Base):
    __tablename__ = 'stock_logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), default="success")
    data_source = Column(String(50))
    query_date = Column(String(20))
    query_time = Column(String(20))
    stock_code = Column(String(20), index=True)
    stock_name = Column(String(50))
    price = Column(Float, default=0.0)
    volume = Column(Integer, default=0)
    type = Column(String(20), default="整股")
    created_at = Column(DateTime, default=datetime.now)

print("正在初始化本地資料庫...")
Base.metadata.create_all(sqlite_engine)
print("💾 本地 SQLite 資料表初始化成功！\n")

# ====================================================
# 核心擷取邏輯（依據指定通道強制抓取，用於獨立測試）
# ====================================================
def fetch_by_specific_channel(channel_name, targets) -> list:
    now = datetime.now()
    sys_date = now.strftime("%Y-%m-%d")
    sys_time = now.strftime("%H:%M:%S")
    output_list = []
    session = create_session_with_retry()

    # ---- 測試通道 1 ----
    if channel_name == "TWSE":
        try:
            ex_ch_list = [f"tse_{code}.tw" for code in targets]
            params = {"ex_ch": "|".join(ex_ch_list), "_": int(time.time() * 1000)}
            response = session.get(TWSE_TICK_URL, params=params, timeout=8)
            if response.status_code == 200:
                data = response.json()
                if "msgArray" in data and data["msgArray"]:
                    for msg in data["msgArray"]:
                        stock_code = msg.get("c")
                        price_str = msg.get("z")
                        if not price_str or price_str == "-":
                            b_list = msg.get("b", "").split("_")
                            price_str = b_list[0] if b_list and b_list[0] and b_list[0] != "-" else msg.get("y")
                        output_list.append({
                            "status": "success", "data_source": "TWSE_Official", "query_date": sys_date,
                            "query_time": sys_time, "stock_code": stock_code, "stock_name": msg.get("n", "").strip(),
                            "price": float(price_str) if price_str else 0.0, "volume": int(msg.get("v", 0)) if msg.get("v") else 0, "type": "整股(TWSE)"
                        })
        except Exception as e:
            print(f"      ❌ TWSE 測試異常: {e}")

    # ---- 測試通道 2 ----
    elif channel_name == "FinMind":
        try:
            headers = {"Authorization": f"Bearer {FINMIND_TOKEN}"} if FINMIND_TOKEN else {}
            for stock_code in targets:
                params = {"dataset": "TaiwanStockPrice", "data_id": stock_code, "start_date": sys_date}
                response = session.get(FINMIND_TICK_URL, headers=headers, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    records = data.get("data", [])
                    if not records: # 防非盤中無當日資料，往前多抓幾天
                        params["start_date"] = (pd.Timestamp(sys_date) - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
                        records = session.get(FINMIND_TICK_URL, headers=headers, params=params, timeout=10).json().get("data", [])
                    if records:
                        latest = records[-1]
                        output_list.append({
                            "status": "success", "data_source": "FinMind_API", "query_date": sys_date,
                            "query_time": sys_time, "stock_code": stock_code, "stock_name": f"個股_{stock_code}",
                            "price": float(latest.get("close", 0)), "volume": int(latest.get("volume", 0)), "type": "整股(API)"
                        })
        except Exception as e:
            print(f"      ❌ FinMind 測試異常: {e}")

    # ---- 測試通道 3 ----
    elif channel_name == "YFinance":
        try:
            import yfinance as yf
            for stock_code in targets:
                ticker = yf.Ticker(f"{stock_code}.TW")
                hist = ticker.history(period="1d")
                if hist.empty:
                    hist = ticker.history(period="5d")
                if not hist.empty:
                    latest = hist.iloc[-1]
                    output_list.append({
                        "status": "success", "data_source": "YFinance_Fallback", "query_date": sys_date,
                        "query_time": sys_time, "stock_code": stock_code, "stock_name": f"個股_{stock_code}",
                        "price": float(latest['Close']), "volume": int(latest['Volume']), "type": "整股(備用)"
                    })
        except Exception as e:
            print(f"      ❌ YFinance 測試異常: {e}")

    return output_list


# ====================================================
# 標準多通道運作機制 (原系統邏輯)
# ====================================================
def fetch_market_data_batch(targets) -> list:
    global twse_failure_count, finmind_failure_count, current_channel
    now = datetime.now()
    sys_date = now.strftime("%Y-%m-%d")
    sys_time = now.strftime("%H:%M:%S")
    output_list = []
    
    # 直接導向目前的有效通道進行單次請求
    output_list = fetch_by_specific_channel(current_channel, targets)
    
    # 動態變更通道狀態機制
    if current_channel == "TWSE":
        if output_list:
            twse_failure_count = 0
        else:
            twse_failure_count += 1
            if twse_failure_count >= TWSE_FAILURE_THRESHOLD:
                current_channel = "FinMind"
                print(f"   🚨 TWSE 連續失敗，自動切換至 [通道 2: FinMind]")
    elif current_channel == "FinMind":
        if output_list:
            finmind_failure_count = 0
        else:
            finmind_failure_count += 1
            if finmind_failure_count >= FINMIND_FAILURE_THRESHOLD:
                current_channel = "YFinance"
                print(f"   🚨 FinMind 連續失敗，自動切換至 [通道 3: YFinance]")
                
    return output_list

class DataStorageManager:
    @classmethod
    def save_via_orm(cls, clean_dict: dict):
        with SqliteSession() as db_sql:
            try:
                db_sql.add(StockLog(**clean_dict))
                db_sql.commit()
                print(f"      💾 [SQLite] {clean_dict['stock_code']} 寫入成功")
            except Exception as e:
                db_sql.rollback()
                print(f"      ❌ [SQLite] 寫入失敗: {e}")

        global excel_buffer
        excel_buffer.append(clean_dict)
        if len(excel_buffer) >= 20:
            cls.flush_buffer_to_excel()

    @classmethod
    def flush_buffer_to_excel(cls):
        global excel_buffer
        if not excel_buffer: return
        try:
            df_new = pd.DataFrame(excel_buffer)
            df_combined = pd.concat([pd.read_excel(EXCEL_FILE), df_new], ignore_index=True) if os.path.exists(EXCEL_FILE) else df_new
            df_combined.to_excel(EXCEL_FILE, index=False)
            print(f"      📊 [Excel] 成功同步 {len(excel_buffer)} 筆紀錄至硬碟。")
            excel_buffer.clear()
        except Exception as e:
            print(f"      ❌ [Excel] 寫入失敗: {e}")

# ====================================================
# 主執行流程
# ====================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print(" 🚀 啟動階段：全面檢測三種資料通道")
    print("="*60)
    
    channels_to_test = ["TWSE", "FinMind", "YFinance"]
    for ch in channels_to_test:
        print(f"\n🔍 [測試中] 正在測試通道：{ch} ...")
        res = fetch_by_specific_channel(ch, STOCK_TARGETS)
        if res:
            print(f"   ✅ 通道 {ch} 測試成功！成功獲取資料：")
            for item in res:
                print(f"      - {item['stock_code']} | 價: {item['price']} | 源: {item['data_source']}")
        else:
            print(f"   ❌ 通道 {ch} 本次測試未取得有效資料 (可能非盤中或 Token 限制)")
        time.sleep(1)
        
    print("\n" + "="*60)
    print(" 🎯 測試完畢！現在切回「原有自動化監控模式」...")
    print("="*60 + "\n")
    
    try:
        iteration = 0
        while True:
            iteration += 1
            print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f"📍 監控模式 - 第 {iteration} 次循環 (當前通道: {current_channel})")
            
            batch_results = fetch_market_data_batch(STOCK_TARGETS)
            if batch_results:
                for stock_record_dict in batch_results:
                    print(f"   [{stock_record_dict['query_time']}] {stock_record_dict['stock_code']} | 價: {stock_record_dict['price']} | 來源: {stock_record_dict['data_source']}")
                    DataStorageManager.save_via_orm(stock_record_dict)
            else:
                print("   ⚠️ 本次無任何通道回傳資料")
                
            time.sleep(FETCH_INTERVAL)
            
    except KeyboardInterrupt:
        print("\n👋 收到終止訊號，正在安全導出剩餘資料...")
        DataStorageManager.flush_buffer_to_excel()
        print("系統安全關閉。")