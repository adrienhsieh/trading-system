"""
trading/api/auth_login.py — 新版 JWT 登入端點

端點：
- POST /api/auth/login — 用戶登入，返回 JWT Token
"""
from flask import Blueprint, request, jsonify
from trading.api.jwt_utils import generate_token
import logging

logger = logging.getLogger(__name__)

api_auth = Blueprint('api_auth', __name__, url_prefix='/api/auth')


@api_auth.route('/login', methods=['POST'])
def login():
    """
    用戶登入端點
    
    Request Body:
    {
        "user_id": "user_001",  # 唯一用戶識別碼
        "password": ""           # 暫未使用（開發版）
    }
    
    Returns:
        JWT Token 與用戶資訊
    
    Response:
    {
        "ok": true,
        "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        "user_id": "user_001",
        "expires_in": 86400
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                "ok": False,
                "error": "Request body is empty"
            }), 400
        
        user_id = data.get('user_id', '').strip()
        
        if not user_id:
            return jsonify({
                "ok": False,
                "error": "user_id 為必填欄位"
            }), 400
        
        # 驗證 user_id 格式（簡易版本，生產環境應加強）
        if len(user_id) < 3 or len(user_id) > 50:
            return jsonify({
                "ok": False,
                "error": "user_id 長度應在 3-50 字元之間"
            }), 400
        
        # 生成 JWT Token
        token = generate_token(user_id)
        
        logger.info(f"✅ 用戶 {user_id} 登入成功")
        
        return jsonify({
            "ok": True,
            "token": token,
            "user_id": user_id,
            "expires_in": 86400  # 24 小時（秒）
        }), 200
    
    except Exception as e:
        logger.error(f"❌ 登入端點異常: {e}", exc_info=True)
        return jsonify({
            "ok": False,
            "error": "伺服器內部錯誤"
        }), 500
