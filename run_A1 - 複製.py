import sys
# 🛠️ 核心修正：將當前執行路徑加入 sys.path，防範 ModuleNotFoundError
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# 這裡才開始導入你原來的模組
from trading.scanner import StockScanner
from trading.logger import get_logger

logger = get_logger("main")

def main():
    logger.info("🚀 啟動台股 AI 自適應技術面掃描系統...")
    
    try:
        # 1. 初始化掃描器
        scanner = StockScanner()
        
        # ── 🛠️ 核心修正：自動攔截並修復 scanner.py 裡面寫壞的錯誤網址 ──
        if "https://://" in scanner.TWSE_API_URL:
            logger.warning("⚠️ 偵測到 scanner.py 中的 TWSE 網址格式不正確 (https://://)，已自動修正為官方 OpenAPI 節點。")
            scanner.TWSE_API_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
            scanner.TWSE_INDUSTRY_URL = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"
        
        if scanner.TPEX_API_URL == "https://tpex.org.tw":
            logger.warning("⚠️ 偵測到 TPEX 網址缺少 OpenAPI 節點路徑，已自動修正。")
            scanner.TPEX_API_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"

        # 2. 取得全台股候選清單
        logger.info("🔍 正在下載 TWSE/TPEX 全市場股票清單...")
        candidates = scanner.get_all_tw_stocks()
        total_count = len(candidates)
        
        if total_count == 0:
            logger.error("❌ 無法取得股票清單，請檢查網路連線或 API 狀態。")
            return
            
        logger.info("📊 成功載入市場清單，共計 %d 檔個股", total_count)
        
        # 3. 設定掃描參數
        capital = 1000000.0  # 模擬本金 100 萬
        risk_pct = 2.0       # 每筆交易承擔 2% 風險
        strategy = "trend"   # 執行趨勢策略 (trend / ict / fundamental)
        
        logger.info("⚙️ 掃描配置: 策略=%s, 本金=%s, 風險=%s%%", strategy, capital, risk_pct)
        logger.info("⏳ 正在執行多執行緒指標計算與 AI 自適應權重篩選，請稍候...")
        
        # 4. 執行批次掃描（內部已自帶 60 秒 Timeout 保護）
        results = scanner.run_scan(
            candidates=candidates,
            capital=capital,
            risk_pct=risk_pct,
            strategy=strategy
        )
        
        # 5. 格式化輸出
        api_output = scanner.format_for_api(results, strategy=strategy)
        logger.info("✅ 掃描完成！符合篩選條件的強勢股共計 %d 檔", len(api_output))
        
        # 6. 美化列印前 10 名強勢股成果（包含最新的開盤動能與 AI 預測數據）
        print("\n" + "="*75)
        print(f" 🏆 台股強勢股 AI 自適應綜合排行 TOP 10 (策略: {strategy.upper()})")
        print("="*75)
        
        for i, item in enumerate(api_output[:10], 1):
            analysis = item.get("adaptive_analysis", {})
            pred = item.get("open_prediction", {})
            
            print(f"[{i:02d}] {item['code']} {item['name']} | 昨收: {item['close']} | 🎯 AI 綜合評分: {analysis.get('composite_score', 'N/A')} 分")
            print(f"     📊 AI 操作建議: 【{analysis.get('recommendation', '未知')}】 (量化權重: {analysis.get('quant_weight_pct')}% / AI權重: {analysis.get('ai_weight_pct')}%)")
            
            if pred:
                print(f"     🔮 明日開盤預測: {pred.get('type')} (信心度 {pred.get('probability')})")
                print(f"         期望開盤價: {pred.get('predicted_open')} | 合理震盪區間: {pred.get('range_low')} ~ {pred.get('range_high')}")
            
            print(f"     👉 風控參數 -> 進場: {item['entry']} | 停損: {item['stop']} | 目標: {item['target']} | 推薦股數: {item['shares']} 股")
            print("-" * 75)
            
    except KeyboardInterrupt:
        logger.warning("\n🛑 使用者中止執行。")
        sys.exit(0)
    except Exception as e:
        logger.critical("💥 系統執行時發生嚴重錯誤: %s", e, exc_info=True)

if __name__ == "__main__":
    main()