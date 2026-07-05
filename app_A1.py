"""
app.py — Flask 應用程式進入點 (多租戶升級相容防錯版)
優化 CORS 動態適應架構，確保 8080 與 8787 埠之前端網頁均能完美連線登入。
啟動方式：python run.py 或 python app.py
"""
import logging
import os
import threading
from pathlib import Path
from flask import Flask, send_from_directory, jsonify
from flask_cors import CORS

# 1. 儘量延遲導入重型模組
from trading.api import register_blueprints
from trading.api.extensions import limiter
from trading.exceptions import TradingSystemError
from trading.services.config_db import init_db
from trading.api.admin_ui import init_admin_web_ui

BASE_DIR = Path(__file__).parent
_logger  = logging.getLogger("trading.app")

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "trading_system_opus_secure_key_2026")

# 🟢 修正：擴大 CORS 允許範圍，動態相容開發環境中前端常用的 8080, 8787 與本地端點
CORS(app, resources={r"/api/*": {
    "origins": [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8787",
        "http://127.0.0.1:8787"
    ],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization", "X-API-Key"]
}})

limiter.init_app(app)

# ── 🟢 背景預熱任務 ──
def warmup_system():
    """在背景載入資源，避免阻擋 Flask 啟動"""
    try:
        from trading.services.container import container
        _logger.info("背景預熱中：載入 scanner 與 market_svc...")
        _ = container.scanner  # 觸發 lazy-init
        _ = container.market_svc
        _logger.info("系統資源預熱完成。")
    except Exception as e:
        _logger.warning("系統預熱發生非致命錯誤: %s", e)

# 啟動時立即開啟執行緒進行預熱
threading.Thread(target=warmup_system, daemon=True).start()

# ── 藍圖註冊 (使用延遲導入以加快啟動速度) ──
from trading.api.auth import api_auth
app.register_blueprint(api_auth)
register_blueprints(app)
init_admin_web_ui(app)

# 初始化資料庫
try:
    init_db()
except Exception as e:
    _logger.error("SQLite 初始化失敗: %s", e)


# ── 靜態頁面 ───────────────────────────────────────────────────
@app.route("/")
def index():
    real_path = os.path.abspath(os.path.join(str(BASE_DIR), "index.html"))
    print(f"\n📢 [重要情報] 戰情中心目前真正在背景讀取的 index.html 絕對路徑為:\n👉 {real_path}\n")
    
    response = send_from_directory(str(BASE_DIR), "index.html")
    response.headers["Location"] = "" 
    response.status_code = 200        
    return response


@app.route("/mockup")
def mockup():
    return send_from_directory(str(BASE_DIR / "docs"), "mockup-recorder.html")


# ── Security headers ──────────────────────────────────────────
@app.after_request
def set_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    return response


# ── 全域 error handler ────────────────────────────────────────
@app.errorhandler(TradingSystemError)
def handle_trading_error(e: TradingSystemError):
    _logger.error("TradingSystemError: %s", e, exc_info=True)
    return jsonify({"ok": False, "error": "系統發生錯誤，請稍後再試"}), 500


@app.errorhandler(500)
def handle_500(e):
    _logger.error("Unhandled 500: %s", e, exc_info=True)
    return jsonify({"ok": False, "error": "內部伺服器錯誤"}), 500
    
@app.route("/api/health")
def health_check():
    from trading.services.container import container
    is_ready = container._scanner is not None
    return jsonify({
        "status": "ready" if is_ready else "warming_up",
        "ready": is_ready
    })


# ── 直接執行 ─────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"\n⚔️  戰情指揮中心（已解除跨域連線限制・安全防禦架構啟動）")
    print(f"   👉 交易系統登入首頁: http://localhost:{port}/login.html")
    print(f"   👉 交易系統主功能頁: http://localhost:{port}/")
    print(f"   👉 獨立資料庫管理後台: http://localhost:{port}/admin\n")
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
