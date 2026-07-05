"""
trading/api/jwt_utils.py — JWT 驗證與多人管理

核心職責：
1. 生成與驗證 JWT Token
2. 將 user_id 注入到 Flask 全域 Context (g)
3. 提供 @jwt_required 裝飾器供 API 端點使用
"""
import os
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "fallback-secret-change-me")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", 24))


def generate_token(user_id: str) -> str:
    """
    生成 JWT Token
    
    Args:
        user_id: 用戶唯一識別碼（可用 UUID 或自訂用戶名）
    
    Returns:
        JWT Token 字串
    """
    payload = {
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRY_HOURS),
        'iat': datetime.utcnow(),
        'user_id': user_id
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')


def verify_token(token: str) -> dict:
    """
    驗證並解碼 JWT Token
    
    Args:
        token: JWT Token 字串
    
    Returns:
        payload 字典，包含 user_id 與時間戳
    
    Raises:
        jwt.ExpiredSignatureError: Token 已過期
        jwt.InvalidTokenError: Token 無效
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token 已過期，請重新登入")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"無效的 Token: {str(e)}")


def jwt_required(f):
    """
    API 驗證裝飾器
    
    使用方式：
    @api.route('/protected')
    @jwt_required
    def protected_endpoint():
        user_id = g.current_user_id  # 💡 核心：鎖定目前的用戶 ID Context
        ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        
        # 檢查 Authorization Header
        if not auth_header.startswith('Bearer '):
            return jsonify({"ok": False, "error": "未提供憑證，請先登入"}), 401
        
        token = auth_header.split(" ")[1]
        
        try:
            payload = verify_token(token)
            # 💡 核心：將 user_id 注入到 Flask 全域變數 g，後續使用 g.current_user_id 存取
            g.current_user_id = payload['user_id']
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 401
        except Exception as e:
            return jsonify({"ok": False, "error": "憑證驗證失敗"}), 401
        
        return f(*args, **kwargs)
    
    return decorated
