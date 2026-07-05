"""
trading/api/prediction.py — 即時預測 API 端點

核心 API：
1. GET /api/prediction/calculate — 單次預測計算
2. GET /api/prediction/stream — SSE 即時串流推送
3. POST /api/prediction/save — 儲存預測紀錄

功能：
- JWT 安全認證
- 動態策略組裝
- 多通道資料取得
- 即時 SSE 推送
"""
import json
import time
from flask import Blueprint, Response, request, jsonify, g
from trading.api.utils import jwt_required
from trading.services.database_container import container
from trading.services.strategy_compositor import StrategyCompositor
import logging

logger = logging.getLogger(__name__)

# 建立 API Blueprint
api_prediction = Blueprint('api_prediction', __name__, url_prefix='/api/prediction')


@api_prediction.route('/calculate', methods=['GET'])
@jwt_required
def calculate_prediction():
    """
    單次預測計算端點
    
    Query Parameters:
        ticker: 股票代號（如 '2330'）
    
    Returns:
        {
            'ticker': '2330',
            'prediction_score': 85.5,
            'bull_confidence': 67.3,
            'bear_confidence': 32.7,
            'strategy_details': [...],
            'calculated_at': '09:30:15',
            'data_sources': ['TWSE_Official', 'FinMind_API']
        }
    """
    try:
        ticker = request.args.get('ticker', '2330').strip()
        
        if not ticker:
            return jsonify({"error": "ticker 參數不能為空"}), 400
        
        # 獲取當前用戶的資料庫連線
        user_db = container.get_user_db()
        
        # 初始化策略組裝器
        compositor = StrategyCompositor(user_db)
        
        # 執行預測計算
        prediction_data = compositor.calculate_prediction(ticker)
        
        return jsonify(prediction_data), 200
        
    except Exception as e:
        logger.error(f"❌ 預測計算失敗: {e}")
        return jsonify({"error": str(e)}), 500


@api_prediction.route('/stream', methods=['GET'])
@jwt_required
def stream_prediction():
    """
    即時預測串流端點（Server-Sent Events）
    
    Query Parameters:
        ticker: 股票代號（如 '2330'）
        interval: 更新間隔（秒，預設 5）
    
    Returns:
        event-stream: 每 5 秒推送一次最新預測
    """
    try:
        ticker = request.args.get('ticker', '2330').strip()
        interval = int(request.args.get('interval', 5))
        
        if not ticker:
            return jsonify({"error": "ticker 參數不能為空"}), 400
        
        # 獲取用戶資料庫連線
        user_db = container.get_user_db()
        
        def event_stream():
            """SSE 事件生成器"""
            compositor = StrategyCompositor(user_db)
            
            while True:
                try:
                    # 即時動態計算最新的綜合評分
                    prediction_data = compositor.calculate_prediction(ticker)
                    
                    # 以 SSE 格式發送給前端網頁
                    yield f"data: {json.dumps(prediction_data)}\n\n"
                    
                    # 等待指定間隔後再次計算
                    time.sleep(interval)
                    
                except Exception as e:
                    logger.error(f"❌ 串流推送異常: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    time.sleep(interval)
        
        return Response(event_stream(), mimetype="text/event-stream")
        
    except Exception as e:
        logger.error(f"❌ 串流初始化失敗: {e}")
        return jsonify({"error": str(e)}), 500


@api_prediction.route('/save', methods=['POST'])
@jwt_required
def save_prediction():
    """
    儲存預測紀錄至用戶資料庫
    
    Request Body:
        {
            'ticker': '2330',
            'prediction_score': 85.5,
            'bull_confidence': 67.3,
            'bear_confidence': 32.7,
            'estimated_open': 272.00,
            'previous_close': 269.00,
            'note': '選填備註'
        }
    
    Returns:
        {
            'success': True,
            'record_id': 123,
            'message': '預測紀錄已儲存'
        }
    """
    try:
        data = request.get_json() or {}
        
        ticker = data.get('ticker', '').strip()
        if not ticker:
            return jsonify({"error": "ticker 不能為空"}), 400
        
        prediction_score = float(data.get('prediction_score', 50))
        bull_conf = float(data.get('bull_confidence', 50))
        bear_conf = float(data.get('bear_confidence', 50))
        est_open = float(data.get('estimated_open', 0))
        prev_close = float(data.get('previous_close', 0))
        note = data.get('note', '')
        
        # 獲取用戶資料庫
        user_db = container.get_user_db()
        cursor = user_db.cursor()
        
        # 建立預測紀錄表（如不存在）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prediction_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                prediction_date TEXT DEFAULT CURRENT_TIMESTAMP,
                prediction_score REAL,
                bull_confidence REAL,
                bear_confidence REAL,
                estimated_open REAL,
                previous_close REAL,
                actual_open REAL,
                is_settled INTEGER DEFAULT 0,
                settlement_date TEXT,
                note TEXT
            );
        """)
        
        # 插入預測紀錄
        cursor.execute("""
            INSERT INTO prediction_records 
            (ticker, prediction_score, bull_confidence, bear_confidence, 
             estimated_open, previous_close, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (ticker, prediction_score, bull_conf, bear_conf, est_open, prev_close, note))
        
        user_db.commit()
        record_id = cursor.lastrowid
        
        logger.info(f"✅ [Prediction] 用戶 {g.current_user_id} 新增預測紀錄 ID: {record_id}")
        
        return jsonify({
            'success': True,
            'record_id': record_id,
            'message': '預測紀錄已儲存',
            'ticker': ticker
        }), 201
        
    except Exception as e:
        logger.error(f"❌ 預測紀錄儲存失敗: {e}")
        return jsonify({"error": str(e)}), 500


@api_prediction.route('/history', methods=['GET'])
@jwt_required
def get_prediction_history():
    """
    取得用戶的預測歷史紀錄
    
    Query Parameters:
        ticker: 股票代號（可選，不指定則回傳全部）
        limit: 最多回傳筆數（預設 50）
    
    Returns:
        [
            {
                'id': 123,
                'ticker': '2330',
                'prediction_date': '2026-07-05T09:30:00',
                'prediction_score': 85.5,
                'bull_confidence': 67.3,
                'bear_confidence': 32.7,
                'estimated_open': 272.00,
                'previous_close': 269.00,
                'actual_open': 271.50,
                'is_settled': 1,
                'settlement_date': '2026-07-05T09:31:00'
            },
            ...
        ]
    """
    try:
        ticker_filter = request.args.get('ticker', '').strip()
        limit = int(request.args.get('limit', 50))
        
        user_db = container.get_user_db()
        cursor = user_db.cursor()
        
        if ticker_filter:
            cursor.execute("""
                SELECT * FROM prediction_records 
                WHERE ticker = ? 
                ORDER BY prediction_date DESC 
                LIMIT ?
            """, (ticker_filter, limit))
        else:
            cursor.execute("""
                SELECT * FROM prediction_records 
                ORDER BY prediction_date DESC 
                LIMIT ?
            """, (limit,))
        
        rows = cursor.fetchall()
        records = [dict(row) for row in rows] if rows else []
        
        return jsonify({
            'success': True,
            'total': len(records),
            'records': records
        }), 200
        
    except Exception as e:
        logger.error(f"❌ 預測歷史查詢失敗: {e}")
        return jsonify({"error": str(e)}), 500


@api_prediction.route('/config', methods=['GET', 'POST'])
@jwt_required
def manage_strategy_config():
    """
    管理用戶的策略配置（開關、權重等）
    
    GET：取得當前策略配置
    POST：更新策略配置
        {
            'strategy_id': 'opening_volume_pulse',
            'is_enabled': 1,
            'weight': 1.5
        }
    """
    try:
        user_db = container.get_user_db()
        cursor = user_db.cursor()
        
        if request.method == 'GET':
            # 取得所有策略配置
            cursor.execute("SELECT * FROM user_strategy_configs ORDER BY strategy_id")
            rows = cursor.fetchall()
            configs = [dict(row) for row in rows] if rows else []
            
            return jsonify({
                'success': True,
                'configs': configs
            }), 200
        
        elif request.method == 'POST':
            # 更新策略配置
            data = request.get_json() or {}
            strategy_id = data.get('strategy_id', '').strip()
            is_enabled = int(data.get('is_enabled', 1))
            weight = float(data.get('weight', 1.0))
            
            if not strategy_id:
                return jsonify({"error": "strategy_id 不能為空"}), 400
            
            # 先檢查是否存在
            cursor.execute(
                "SELECT id FROM user_strategy_configs WHERE strategy_id = ?",
                (strategy_id,)
            )
            existing = cursor.fetchone()
            
            if existing:
                # 更新現有配置
                cursor.execute("""
                    UPDATE user_strategy_configs 
                    SET is_enabled = ?, weight = ?
                    WHERE strategy_id = ?
                """, (is_enabled, weight, strategy_id))
            else:
                # 插入新配置
                cursor.execute("""
                    INSERT INTO user_strategy_configs (strategy_id, is_enabled, weight)
                    VALUES (?, ?, ?)
                """, (strategy_id, is_enabled, weight))
            
            user_db.commit()
            
            logger.info(f"✅ [Config] 用戶 {g.current_user_id} 更新策略 {strategy_id}: enabled={is_enabled}, weight={weight}")
            
            return jsonify({
                'success': True,
                'message': f'策略配置 {strategy_id} 已更新',
                'strategy_id': strategy_id
            }), 200
        
    except Exception as e:
        logger.error(f"❌ 策略配置管理失敗: {e}")
        return jsonify({"error": str(e)}), 500
