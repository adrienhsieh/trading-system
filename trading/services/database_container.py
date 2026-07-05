"""
trading/services/database_container.py — 多租戶資料庫容器

核心職責：
1. 依據 g.current_user_id 動態切換用戶私有資料庫（物理隔離）
2. 管理全域共享資料庫（ohlcv_cache.db、intelligence.db）
3. 確保首次登入時自動初始化用戶表結構

設計理念：
- 原有 Schema 100% 複用，不添加 user_id 欄位
- WAL 模式確保高併發性能
- 用戶資料完全隔離在 db/user_{id}/ 資料夾
"""
import os
import sqlite3
from flask import g
from pathlib import Path


class DatabaseContainer:
    """多租戶資料庫管理器"""
    
    def __init__(self, base_dir: str = "db"):
        self.base_dir = base_dir
        # 全域公用資料庫路徑（所有用戶共用，唯讀）
        self.ohlcv_db_path = os.path.join(base_dir, "ohlcv_cache.db")
        self.intelligence_db_path = os.path.join(base_dir, "intelligence.db")
        
        # 確保基礎目錄存在
        os.makedirs(base_dir, exist_ok=True)
    
    def get_user_db(self) -> sqlite3.Connection:
        """
        動態依據目前 Request 的 JWT 用戶 ID 獲取其專屬資料庫連線
        
        Returns:
            sqlite3.Connection: 用戶專屬資料庫連線
        
        Raises:
            PermissionError: 沒有合法的用戶 Context
        """
        user_id = getattr(g, 'current_user_id', None)
        if not user_id:
            raise PermissionError("❌ 沒有合法的用戶 Context，拒絕建立私有連線")
        
        # 物理隔離目錄：db/user_{id}/
        user_folder = os.path.join(self.base_dir, f"user_{user_id}")
        os.makedirs(user_folder, exist_ok=True)
        
        db_path = os.path.join(user_folder, "userdata.db")
        is_new = not os.path.exists(db_path)
        
        # 開啟連線並啟用 WAL 模式
        conn = sqlite3.connect(db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")  # 💡 關鍵：啟用 WAL 模式確保效能
        conn.row_factory = sqlite3.Row
        
        # 首次登入時自動初始化表結構
        if is_new:
            self._init_user_schema(conn)
            print(f"✅ [DB] 為用戶 {user_id} 初始化新的資料庫表結構")
        
        return conn
    
    def get_global_cache_db(self) -> sqlite3.Connection:
        """
        獲取全域快取資料庫連線（多通道即時數據儲存區）
        
        Returns:
            sqlite3.Connection: 全域快取資料庫連線
        """
        os.makedirs(self.base_dir, exist_ok=True)
        conn = sqlite3.connect(self.ohlcv_db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_intelligence_db(self) -> sqlite3.Connection:
        """
        獲取 AI 情報資料庫連線（共享）
        
        Returns:
            sqlite3.Connection: 情報資料庫連線
        """
        os.makedirs(self.base_dir, exist_ok=True)
        conn = sqlite3.connect(self.intelligence_db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.row_factory = sqlite3.Row
        return conn
    
    @staticmethod
    def _init_user_schema(conn: sqlite3.Connection):
        """
        建立該用戶專屬的個人表
        
        完全複用原單機版的 Schema，免加 user_id 欄位
        每個用戶獲得獨立的表副本，資料完全隔離
        """
        cursor = conn.cursor()
        
        # 持倉表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                name TEXT,
                entry_date TEXT,
                entry_price REAL,
                shares INTEGER,
                stop_loss REAL,
                target_price REAL,
                status TEXT DEFAULT 'active',
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 觀察名單表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # 用戶策略配置表（新增）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_strategy_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT NOT NULL,
                is_enabled INTEGER DEFAULT 1,
                weight REAL DEFAULT 1.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        conn.commit()


# 全域容器實例
container = DatabaseContainer()
