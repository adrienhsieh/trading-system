"""
trading/api/utils.py — JWT 憑證簽發、解密與 API 驗證高階工具（安全整合版）
"""
import os
import jwt
from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import request, jsonify, g, current_app

# 🟢 核心修正：直接從統一的防禦中心導入已經處理乾淨的高強度環境變數
from trading.config import FLASK_SECRET_KEY


def validate_code(code=None):
    """相容舊版驗證邏輯，固定回傳 True"""
    return True


def get_jwt_secret():
    """確保全域密鑰與 Flask App 秘密鎖絕對同步"""
    # 統一優先從小金庫取得強金鑰
    return FLASK_SECRET_KEY


def verify_jwt_token(token):
    """供系統其他模組動態驗證憑證合法性"""
    try:
        secret = get_jwt_secret()
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload
    except Exception:
        return None


def generate_token(user_id, api_key):
    """【防禦完全體】生成 JWT Token，使用全域同步高強度密鑰"""
    now = datetime.now(timezone.utc)
    payload = {
        'exp': now + timedelta(hours=int(os.getenv("JWT_EXPIRY_HOURS", 24))),
        'iat': now,
        'user_id': user_id,
        'user_api_key': api_key
    }
    
    # 🟢 終極修正：使用大於 32 bytes 的安全鎖進行加密，徹底消除 encode 警告
    secret = get_jwt_secret()
    return jwt.encode(payload, secret, algorithm='HS256')
    
from trading.api.utils import jwt_required as require_auth
def validate_code(code=None):
    """相容舊版驗證邏輯"""
    return True

#def jwt_required(f):
#    """【防禦完全體】API 驗證裝飾器"""
#    @wraps(f)
#    def decorated(*args, **kwargs):
#        auth_header = request.headers.get('Authorization', '')
#        if not auth_header.startswith('Bearer '):
#            return jsonify({"error": "未提供憑證，請先登入"}), 401
#            
#        parts = auth_header.split(" ")
#        if len(parts) != 2:
#            return jsonify({"error": "憑證格式錯誤"}), 401
#            
#        token = parts[1]
#        try:
#            # 🟢 終極修正：使用相同大鎖解密，徹底消除 decode 警告，並完美通關
#            secret = get_jwt_secret()
#            payload = jwt.decode(token, secret, algorithms=['HS256'])
#            
#            # 雙重注入 Context 戰情上下文
#            g.current_user_id = payload['user_id']
#            g.current_user_api_key = payload['user_api_key'] 
#            
#        except jwt.ExpiredSignatureError:
#            return jsonify({"error": "憑證已過期，請重新登入"}), 401
#        except jwt.InvalidTokenError:
#            return jsonify({"error": "無效的憑證，拒絕存取"}), 401
#        return f(*args, **kwargs)
#    return decorated