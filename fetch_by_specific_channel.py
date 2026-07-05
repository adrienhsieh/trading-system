import os
import json
import time
import sqlite3
from datetime import datetime, time as datetime_time
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# ==================== 系統全域內嵌設定區 ====================
STOCK_TARGETS = ["2330", "2317"]  
FETCH_INTERVAL = 5  
HEARTBEAT_INTERVAL = 3600  # 非開盤時間，每一小時打印一次心跳，降低 CPU 與網路消耗

FINMIND_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiYWRyaWVuIiwiZW1haWwiOiJhZHJpZW5oc2llaEBnbWFpbC5jb20iLCJ0b2tlbl92ZXJzaW9uIjoxfQ.BMrXqaq-yrlwwS7h-qpUQuKPeqqc26fhOA6ly_lf7ZA"

LOCAL_DB_FILE = "stock_monitor.db"
EXCEL_FILE = "stock_records.xlsx"

TWSE_TICK_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
FINMIND_TICK_URL = "https://api.finmindtrade.com/api/v4/data"

TWSE_FAILURE_THRESHOLD = 3
FINMIND_FAILURE_THRESHOLD = 3

# pool_pre_ping=True 確保 SQLite 在 Non-Stop 長期斷線後能自動重連
sqlite_engine = create_engine(f"sqlite:///{LOCAL_DB_FILE}", pool_pre_ping=True)
SqliteSession = sessionmaker(bind=sqlite_engine)

Base = declarative_base()

twse_failure_count = 0      
finmind_failure_count = 0   
current_channel = "TWSE"     
excel_buffer = []           

# ==================== 時間與狀態檢查 (Non-Stop 核心邏輯) ====================
def get_market_status():
    """
    判斷台股當前的時間狀態，決定爬蟲策略
    """
    now = datetime.now()
    # 判斷週末 (星期六 5, 星期日 6)
    if now.weekday() >= 5:
        return "WEEKEND"
    
    current_time = now.time()
    # 台股開盤前置與盤中時間 (08:30 ~ 13:35 給予前後緩衝)
    if datetime_time(8, 30) <= current_time <= datetime_time(13, 35):
        return "TRADING_HOURS"
    # 盤後資料整理與定價交易時間 (13:35 ~ 15:00)
    elif datetime_time(13, 35) < current_time <= datetime_time(15, 0):
        return "POST_MARKET"
    else:
        return "OFF_HOURS"

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
# 核心擷取邏輯（保持您原本的通道邏輯穩定運作）
# ====================================================
def fetch_by_specific_channel(channel_name, targets) -> list:
    now = datetime.now()
    sys_date = now.strftime("%Y-%m-%d")
    sys_time = now.strftime("%H:%M:%S")
    output_list = []
    session = create_session_with_retry()

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

    elif channel_name == "FinMind":
        try:
            headers = {"Authorization": f"Bearer {FINMIND_TOKEN}"} if FINMIND_TOKEN else {}
            for stock_code in targets:
                params = {"dataset": "TaiwanStockPrice", "data_id": stock_code, "start_date": sys_date}
                response = session.get(FINMIND_TICK_URL, headers=headers, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    records = data.get("data", [])
                    if not records: 
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

def fetch_market_data_batch(targets) -> list:
    global twse_failure_count, finmind_failure_count, current_channel
    output_list = fetch_by_specific_channel(current_channel, targets)
    
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
            print(f"      ❌ [Excel] 寫入失敗 (檔案可能被開啟中): {e}")

# ====================================================
# 不間斷 (Non-Stop) 智慧主流程
# ====================================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print(" ⚡ 進入 Non-Stop 交易守護監控模式")
    print("="*60 + "\n")
    
    iteration = 0
    
    try:
        while True:
            market_status = get_market_status()
            
            # --- 狀態 1: 盤中高頻監控 ---
            if market_status == "TRADING_HOURS":
                iteration += 1
                print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
                print(f"📍 監控模式 - 第 {iteration} 次循環 (當前通道: {current_channel})")
                
                try:
                    batch_results = fetch_market_data_batch(STOCK_TARGETS)
                    if batch_results:
                        for stock_record_dict in batch_results:
                            print(f"   [{stock_record_dict['query_time']}] {stock_record_dict['stock_code']} | 價: {stock_record_dict['price']} | 來源: {stock_record_dict['data_source']}")
                            DataStorageManager.save_via_orm(stock_record_dict)
                    else:
                        print("   ⚠️ 本次無任何通道回傳資料")
                except Exception as loop_err:
                    print(f"   🚨 盤中監控發生未知異常: {loop_err}，服務不中斷，下個週期重試。")
                
                time.sleep(FETCH_INTERVAL)
            
            # --- 狀態 2: 盤後清算與資料落盤 ---
            elif market_status == "POST_MARKET":
                print(f"⏰ [{datetime.now().strftime('%H:%M:%S')}] 進入盤後階段。強制清理快取至 Excel...")
                DataStorageManager.flush_buffer_to_excel()
                
                # 💡 互相配合改進點：此處可以呼叫你的 trading-system 去做日K線、三大法人籌碼的下載更新
                print("   ℹ️ 暫停即時 Tick 追蹤。等待盤後定價與籌碼資料生成...")
                time.sleep(600)  # 盤後每 10 分鐘檢查一次即可
                
            # --- 狀態 3: 非交易時間 / 夜間 / 週末 (心跳守護) ---
            else:
                # 確保睡前快取完全被寫入硬碟
                if excel_buffer:
                    DataStorageManager.flush_buffer_to_excel()
                
                # 跨日自動復原：確保隔天開盤用回最精準的 TWSE 官方通道
                if current_channel != "TWSE":
                    current_channel = "TWSE"
                    twse_failure_count = 0
                    print("   🔄 檢測到處於非交易時段，已自動將預設通道重置為 [TWSE Official]。")
                
                print(f"😴 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 非交易時間 ({market_status})。系統進入低耗心跳休眠...")
                time.sleep(HEARTBEAT_INTERVAL)
                
    except KeyboardInterrupt:
        print("\n👋 收到終止訊號，正在安全導出剩餘快取資料...")
        DataStorageManager.flush_buffer_to_excel()
        print("系統已安全關閉。")