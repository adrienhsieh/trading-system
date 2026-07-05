# test_server.py (測試用主程式)
import os
from flask import Flask
from trading.api.auth import api_auth

# 設定測試環境變數
os.environ["JWT_SECRET_KEY"] = "trading_system_super_secret_key_2026_xyz"
os.environ["JWT_EXPIRY_HOURS"] = "24"

app = Flask(__name__)
app.register_blueprint(api_auth)

if __name__ == "__main__":
    print("🔥 測試伺服器已啟動，監聽 http://127.0.0.1:5000")
    app.run(port=5000, debug=True)
