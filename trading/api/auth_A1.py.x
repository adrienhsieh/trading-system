"""
trading/api/auth.py — API 認證、註冊與多租戶身分驗證核心（修正版）
"""
import sqlite3
import os
import secrets
from flask import Blueprint, request, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from trading.api.utils import generate_token

api_auth = Blueprint('api_auth', __name__)

def get_db_connection():
    # 確保 db 資料夾存在
    os.makedirs("db", exist_ok=True)
    conn = sqlite3.connect("db/trading_system.db")
    conn.row_factory = sqlite3.Row
    return conn

# =====================================================================
# 🟢 註冊端點
# =====================================================================
@api_auth.route('/register', methods=['POST'])
def register():
    """使用者註冊端點，自動核發隨機的系統 API Key"""
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({"error": "請提供完整的帳號與密碼"}), 400
        
    username = data.get('username').strip()
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "帳號密碼不得為空"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 檢查帳號是否重複
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            return jsonify({"error": "該帳號已被註冊"}), 400
            
        # 密碼加密，並自動生成一組隨機的 system_api_key 給該用戶
        pwd_hash = generate_password_hash(password)
        random_api_key = f"tkey_{secrets.token_hex(16)}"
        
        cursor.execute(
            "INSERT INTO users (username, password_hash, system_api_key) VALUES (?, ?, ?)",
            (username, pwd_hash, random_api_key)
        )
        conn.commit()
        return jsonify({"status": "success", "message": "註冊成功！請返回登入。"}), 201
        
    except sqlite3.Error as e:
        return jsonify({"error": f"資料庫寫入失敗: {str(e)}"}), 500
    finally:
        conn.close()

# =====================================================================
# 🟢 修正：使用者登入端點
# =====================================================================
@api_auth.route('/login', methods=['POST'])
def login():
    """使用者登入端點，驗證通過發放 JWT Token"""
    try:
        data = request.get_json()
        if not data or 'username' not in data or 'password' not in data:
            return jsonify({"error": "請提供完整的帳號與密碼"}), 400
            
        username = data.get('username').strip()
        password = data.get('password')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 確保資料表存在（防錯機制）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE,
                password_hash TEXT,
                system_api_key TEXT
            )
        """)
        conn.commit()

        cursor.execute("SELECT id, password_hash, system_api_key FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()
        
        if not user or not check_password_hash(user['password_hash'], password):
            return jsonify({"error": "帳號或密碼錯誤，拒絕登入"}), 401
            
        user_id = user['id']
        user_api_key = user['system_api_key'] 
        
        # 發放憑證
        token = generate_token(user_id=user_id, api_key=user_api_key)
        
        return jsonify({
            "status": "success",
            "message": "身分驗證通過，已成功發放安全憑證！",
            "user_id": user_id,
            "token": token
        }), 200
    except Exception as e:
        return jsonify({"error": f"登入伺服器內部錯誤: {str(e)}"}), 500

# 向下相容墊片
# =====================================================================
# 🔄 終極相容墊片（徹底解除 Circular Import 循環導入）
# =====================================================================
def require_auth(f):
    """
    區域安全墊片：確保正確提取 Bearer Token 欄位
    """
    from functools import wraps
    from flask import request, jsonify, g
    import jwt
    
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "未提供憑證，請先登入"}), 401
            
        parts = auth_header.split(" ")
        if len(parts) != 2:
            return jsonify({"error": "憑證格式錯誤"}), 401
            
        token = parts[1]  # 🟢 修正：明確鎖定 Token 密鑰字串，防止變數型態錯誤
        try:
            import os
            secret = os.getenv("JWT_SECRET_KEY", "fallback-secret")
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            g.current_user_id = payload['user_id']
            g.current_user_api_key = payload['user_api_key'] 
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "憑證已過期，請重新登入"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "無效的憑證，拒絕存取"}), 401
        return f(*args, **kwargs)
    return decorated

def validate_code(code=None):
    """相容舊版驗證邏輯"""
    return True
#"""
#trading/api/auth.py — API 認證、註冊與多租戶身分驗證核心
#"""
#import sqlite3
#import os
#import secrets
#from flask import Blueprint, request, jsonify, g
#from werkzeug.security import generate_password_hash, check_password_hash
#from trading.api.utils import generate_token, jwt_required
#
#api_auth = Blueprint('api_auth', __name__)
#
#def get_db_connection():
#    # 確保 db 資料夾存在
#    os.makedirs("db", exist_ok=True)
#    conn = sqlite3.connect("db/trading_system.db")
#    conn.row_factory = sqlite3.Row
#    return conn
#
## =====================================================================
## 🟢 補齊：多租戶註冊端點（解決 405 Method Not Allowed）
## =====================================================================
#@api_auth.route('/register', methods=['POST'])
#def register():
#    """使用者註冊端點，自動核發隨機的系統 API Key"""
#    data = request.get_json()
#    if not data or 'username' not in data or 'password' not in data:
#        return jsonify({"error": "請提供完整的帳號與密碼"}), 400
#        
#    username = data.get('username').strip()
#    password = data.get('password')
#    
#    if not username or not password:
#        return jsonify({"error": "帳號密碼不得為空"}), 400
#
#    conn = get_db_connection()
#    cursor = conn.cursor()
#    
#    try:
#        # 檢查帳號是否重複
#        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
#        if cursor.fetchone():
#            return jsonify({"error": "該帳號已被註冊"}), 400
#            
#        # 密碼加密，並自動生成一組隨機的 system_api_key 給該用戶
#        pwd_hash = generate_password_hash(password)
#        random_api_key = f"tkey_{secrets.token_hex(16)}"
#        
#        cursor.execute(
#            "INSERT INTO users (username, password_hash, system_api_key) VALUES (?, ?, ?)",
#            (username, pwd_hash, random_api_key)
#        )
#        conn.commit()
#        return jsonify({"status": "success", "message": "註冊成功！請返回登入。"}), 201
#        
#    except sqlite3.Error as e:
#        return jsonify({"error": f"資料庫寫入失敗: {str(e)}"}), 500
#    finally:
#        conn.close()
#
## =====================================================================
## 🟢 優化：使用者登入端點
## =====================================================================
#@api_auth.route('/login', methods=['POST'])
#def login():
#    """使用者登入端點，驗證通過發放 JWT Token"""
#    data = request.get_json()
#    if not data or 'username' not in data or 'password' not in data:
#        return jsonify({"error": "請提供完整的帳號與密碼"}), 400
#        
#    username = data.get('username').strip()
#    password = data.get('password')
#    
#    conn = get_db_connection()
#    cursor = conn.cursor()
#    cursor.execute("SELECT id, password_hash, system_api_key FROM users WHERE username = ?", (username,))
#    user = cursor.fetchone()
#    conn.close()
#    
#    if not user or not check_password_hash(user['password_hash'], password):
#        return jsonify({"error": "帳號或密碼錯誤，拒絕登入"}), 401
#        
#    user_id = user['id']
#    user_api_key = user['system_api_key'] 
#    
#    token = generate_token(user_id=user_id, api_key=user_api_key)
#    
#    return jsonify({
#        "status": "success",
#        "message": "身分驗證通過，已成功發放安全憑證！",
#        "user_id": user_id,
#        "token": token
#    }), 200
#
## =====================================================================
## 💡 高頻身分驗證與金鑰自動補齊測試端點
## =====================================================================
#@api_auth.route('/api/get_strategy_config', methods=['GET'])
#@jwt_required  
#def get_strategy_config():
#    config_response = {
#        "total_capital": 200000,
#        "consecutive_losses": 2,
#        "risk_mode": "normal",
#        "scan_candidates": ["2330", "2454", "2317"],
#        "api_key": g.current_user_api_key,  
#        "strategy_params": {
#            "trend": { "ema_arrangement": { "enabled": True } },
#            "ict": { "bullish_ob": { "enabled": True } }
#        }
#    }
#    return jsonify(config_response), 200
#
## 向下相容墊片
#from trading.api.utils import jwt_required as require_auth
#def validate_code(code=None):
#    return True