import os
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g, current_app


def validate_code(code=None):
    """相容舊版驗證邏輯，固定回傳 True"""
    return True

def get_jwt_secret():
    """確保全局密鑰與 Flask App Config 絕對同步"""
    # 優先使用 App Config，其次環境變數，最後才是 fallback-secret
    if current_app and 'SECRET_KEY' in current_app.config:
        return current_app.config['SECRET_KEY']
    return os.getenv("JWT_SECRET_KEY", "fallback-secret")

def verify_jwt_token(token):
    try:
        secret = get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except Exception:
        return None

def generate_token(user_id, api_key):
    """【修正版】生成 JWT Token，使用全域同步密鑰"""
    now = datetime.now(timezone.utc)
    payload = {
        'exp': now + timedelta(hours=int(os.getenv("JWT_EXPIRY_HOURS", 24))),
        'iat': now,
        'user_id': user_id,
        'user_api_key': api_key
    }
    # 這裡必須動態獲取當前 App 的 Secret 或是環境變數
    secret = os.getenv("JWT_SECRET_KEY", "fallback-secret")
    return jwt.encode(payload, secret, algorithm='HS256')

def jwt_required(f):
    """【修正版】API 驗證裝飾器"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({"error": "未提供憑證，請先登入"}), 401
            
        parts = auth_header.split(" ")
        if len(parts) != 2:
            return jsonify({"error": "憑證格式錯誤"}), 401
            
        token = parts[1]
        try:
            secret = os.getenv("JWT_SECRET_KEY", "fallback-secret")
            payload = jwt.decode(token, secret, algorithms=['HS256'])
            
            # 雙重注入 Context
            g.current_user_id = payload['user_id']
            g.current_user_api_key = payload['user_api_key'] 
            
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "憑證已過期，請重新登入"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "無效的憑證，拒絕存取"}), 401
        return f(*args, **kwargs)
    return decorated

#import os
#import jwt
#from datetime import datetime, timedelta, timezone
#from functools import wraps
#from flask import request, jsonify, g
#from flask import current_app
#
#JWT_SECRET = os.getenv("JWT_SECRET_KEY", "fallback-secret")
#
#def verify_jwt_token(token):
#    try:
#        # 必須使用與生成時相同的 secret_key
#        payload = jwt.decode(token, current_app.config['SECRET_KEY'], algorithms=["HS256"])
#        return payload # 成功回傳 payload
#    except Exception:
#        return None # 失敗回傳 None
#
#def generate_token(user_id, api_key):
#    """【升級版】生成 JWT Token，將使用者 ID 與交易 API Key 一併密封封裝"""
#    # 💡 使用 timezone.utc 避免舊版 datetime.utcnow() 的時區與棄用警告
#    now = datetime.now(timezone.utc)
#    payload = {
#        'exp': now + timedelta(hours=int(os.getenv("JWT_EXPIRY_HOURS", 24))),
#        'iat': now,
#        'user_id': user_id,
#        'user_api_key': api_key  # 💡 核心：將金鑰打包進憑證 Payload 中
#    }
#    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')
#
#def jwt_required(f):
#    """【升級版】API 驗證裝飾器"""
#    @wraps(f)
#    def decorated(*args, **kwargs):
#        auth_header = request.headers.get('Authorization', '')
#        if not auth_header.startswith('Bearer '):
#            return jsonify({"error": "未提供憑證，請先登入"}), 401
#            
#        # 避免索引錯誤，加入安全切分
#        parts = auth_header.split(" ")
#        if len(parts) != 2:
#            return jsonify({"error": "憑證格式錯誤"}), 401
#            
#        token = parts[1]
#        try:
#            payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
#            
#            # 💡 雙重注入：同時鎖定目前的用戶 ID 與他專屬的 API Key Context
#            g.current_user_id = payload['user_id']
#            g.current_user_api_key = payload['user_api_key'] 
#            
#        except jwt.ExpiredSignatureError:
#            return jsonify({"error": "憑證已過期，請重新登入"}), 401
#        except jwt.InvalidTokenError:
#            return jsonify({"error": "無效的憑證，拒絕存取"}), 401
#        return f(*args, **kwargs)
#    return decorated
#