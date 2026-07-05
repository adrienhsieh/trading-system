# test_server.py (網頁+API 整合託管版)
import os
import sys
from flask import Flask, render_template # 💡 引入 render_template
from flask_cors import CORS

# 動態校正 Python 搜尋路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from trading.api.auth import api_auth

# 設定測試環境變數
os.environ["JWT_SECRET_KEY"] = "trading_system_super_secret_key_2026_xyz"
os.environ["JWT_EXPIRY_HOURS"] = "24"

# 💡 初始化 Flask，並顯式指定範本目錄為當前目錄下的 templates 資料夾
app = Flask(__name__, template_folder=os.path.join(current_dir, "templates"))
CORS(app)

# 💡 【新增：首頁路由】讓 Flask 託管前端網頁
@app.route('/')
def home():
    """造訪首頁時，直接吐回多租戶前端通訊測試面板"""
    return render_template('index.html')

# 註冊您的登入驗證藍圖
app.register_blueprint(api_auth)

if __name__ == "__main__":
    print("🔥 多租戶交易系統整合伺服器已啟動！")
    print("👉 請直接在瀏覽器輸入網址存取：http://127.0.0.1:5000")
    app.run(port=5000, debug=True)

## test_server_cros.py (升級版)
#import os
#import sys
#from flask import Flask
#from flask_cors import CORS # 💡 新增這行
#
#current_dir = os.path.dirname(os.path.abspath(__file__))
#if current_dir not in sys.path: sys.path.insert(0, current_dir)
#
#from trading.api.auth import api_auth
#
#os.environ["JWT_SECRET_KEY"] = "trading_system_super_secret_key_2026_xyz"
#os.environ["JWT_EXPIRY_HOURS"] = "24"
#
#app = Flask(__name__)
#CORS(app) # 💡 允許跨域測試
#
#app.register_blueprint(api_auth)
#
#if __name__ == "__main__":
#    app.run(port=5000, debug=True)