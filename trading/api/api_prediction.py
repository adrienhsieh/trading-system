# -*- coding: utf-8 -*-
import time
import json
from flask import Blueprint, Response, request, jsonify
from trading.api.utils import jwt_required
from trading.services.container import container, StrategyCompositor

# 建立 Blueprint
api_prediction = Blueprint("api_prediction", __name__)

# 即時預測串流 (SSE)
@api_prediction.route("/api/prediction/stream", methods=["GET"])
@jwt_required
def stream_prediction():
    ticker = request.args.get("ticker", "2330")
    user_db = container.db.get_user_db()
    compositor = StrategyCompositor(user_db)

    def event_stream():
        while True:
            prediction_data = compositor.calculate_prediction(ticker)
            yield f"data: {json.dumps(prediction_data, ensure_ascii=False)}\n\n"
            time.sleep(5)  # 每 5 秒更新一次，與 Worker 的 FETCH_INTERVAL 對齊

    return Response(event_stream(), mimetype="text/event-stream")

# 測試用 API：直接回傳一次預測結果 (JSON)
@api_prediction.route("/api/prediction/test", methods=["GET"])
@jwt_required
def prediction_test():
    ticker = request.args.get("ticker", "2330")
    user_db = container.db.get_user_db()
    compositor = StrategyCompositor(user_db)
    result = compositor.calculate_prediction(ticker)
    return jsonify(result)
