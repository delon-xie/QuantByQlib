from __future__ import annotations
"""
持仓数据库（DuckDB 版）
schema: 与 SQLite 版本保持一致
添加连接池支持
"""
"""
                CREATE TABLE IF NOT EXISTS positions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT NOT NULL UNIQUE,
                    shares          DOUBLE NOT NULL CHECK(shares > 0),
                    avg_cost        DOUBLE NOT NULL CHECK(avg_cost > 0),
                    first_buy_date  TEXT NOT NULL,
                    sector          TEXT,
                    notes           TEXT,
                    updated_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT NOT NULL,
                    trans_type      TEXT NOT NULL CHECK(trans_type IN ('BUY','SELL','DIVIDEND','SPLIT')),
                    shares          DOUBLE NOT NULL CHECK(shares > 0),
                    price           DOUBLE NOT NULL CHECK(price > 0),
                    amount          DOUBLE NOT NULL,
                    commission      DOUBLE NOT NULL DEFAULT 0,
                    trans_date      TEXT NOT NULL,
                    notes           TEXT,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS corporate_actions (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol          TEXT NOT NULL,
                    action_type     TEXT NOT NULL CHECK(action_type IN ('SPLIT','REVERSE_SPLIT','DIVIDEND')),
                    ratio           DOUBLE,
                    amount          DOUBLE,
                    ex_date         TEXT NOT NULL,
                    applied         INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS goals (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    name            TEXT NOT NULL,
                    period_type     TEXT NOT NULL CHECK(period_type IN ('MONTHLY','QUARTERLY','YEARLY')),
                    target_return_pct DOUBLE NOT NULL,
                    start_date      TEXT NOT NULL,
                    end_date        TEXT NOT NULL,
                    initial_capital DOUBLE NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','COMPLETED','CANCELLED')),
                    created_at      TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_transactions_symbol ON transactions(symbol);
                CREATE INDEX IF NOT EXISTS idx_transactions_date   ON transactions(trans_date);
                CREATE INDEX IF NOT EXISTS idx_goals_status        ON goals(status);
            """


import duckdb
import threading
import queue
import atexit
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from contextlib import contextmanager
from loguru import logger
import uuid
import os

DEFAULT_DB_PATH = Path.home() / ".quantbyqlib" / "portfolio.duckdb"


class DuckDBConnectionPool:
    """DuckDB连接池"""
    
    def __init__(self, db_path: Path, pool_size: int = 5, max_overflow: int = 10):
        """
        初始化连接池
        
        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
        """
        self.db_path = str(db_path)
        self.pool_size = pool_size
        self.max_overflow = max_overflow
        self._pool = queue.Queue(maxsize=pool_size)
        self._overflow = 0
        self._lock = threading.Lock()
        self._active_connections = 0
        self._connections_created = 0
        
        # 初始化连接池
        self._initialize_pool()
        
        # 注册清理函数
        atexit.register(self._cleanup_silent)  # 修改这里
        
    def _initialize_pool(self):
        """初始化连接池中的连接"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
            
    def _create_connection(self):
        """创建新的数据库连接"""
        conn = duckdb.connect(database=self.db_path, read_only=False)
        # 设置连接参数
        conn.execute("PRAGMA threads=2")
        self._connections_created += 1
        return conn
    
    def get_connection(self):
        """
        从连接池获取连接
        
        Returns:
            duckdb.Connection: 数据库连接
        """
        try:
            # 首先尝试从池中获取
            conn = self._pool.get_nowait()
            return conn
        except queue.Empty:
            with self._lock:
                # 检查是否可以创建溢出连接
                if self._active_connections < self.pool_size + self.max_overflow:
                    self._overflow += 1
                    self._active_connections += 1
                    return self._create_connection()
                else:
                    # 等待池中有可用连接
                    return self._pool.get()
    
    def return_connection(self, conn):
        """
        归还连接到连接池
        
        Args:
            conn: 要归还的数据库连接
        """
        if conn is None:
            return
            
        # 检查连接是否有效
        try:
            conn.execute("SELECT 1")
        except:
            # 连接无效，创建新的代替
            conn.close()
            conn = self._create_connection()
        
        with self._lock:
            if self._overflow > 0:
                # 归还溢出连接，直接关闭
                self._overflow -= 1
                self._active_connections -= 1
                conn.close()
            else:
                # 归还到连接池
                try:
                    self._pool.put_nowait(conn)
                except queue.Full:
                    # 连接池已满，关闭连接
                    conn.close()
    
    def _cleanup_silent(self):
        """
        静默清理连接池，避免日志错误
        这个方法不记录日志，防止在程序退出时与loguru冲突
        """
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                try:
                    conn.close()
                except:
                    pass
            except queue.Empty:
                break
    
    def _cleanup(self):
        """
        正常的清理方法（非atexit场景下使用）
        这个方法会记录日志，只能在程序运行时调用
        """
        logger.info("清理连接池...")
        count = 0
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
                count += 1
            except queue.Empty:
                break
        
        with self._lock:
            self._active_connections = 0
            self._overflow = 0
        
        logger.info(f"连接池已清理，共关闭了 {count} 个连接")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        with self._lock:
            return {
                "pool_size": self.pool_size,
                "pool_available": self._pool.qsize(),
                "max_overflow": self.max_overflow,
                "overflow": self._overflow,
                "active_connections": self._active_connections,
                "connections_created": self._connections_created
            }

class PortfolioDatabase:
    """DuckDB 持仓数据库封装（带连接池）"""

    def __init__(self, db_path: Optional[Path] = None, pool_size: int = 5, max_overflow: int = 10):
        """
        初始化数据库
        
        Args:
            db_path: 数据库文件路径
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
        """
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化连接池
        self.connection_pool = DuckDBConnectionPool(
            db_path=self.db_path,
            pool_size=pool_size,
            max_overflow=max_overflow
        )
        
        self._init_schema()
        logger.info(f"DuckDB 数据库初始化完成，路径：{self.db_path}")

    # ── 连接管理 ─────────────────────────────────────────────
    # 保持原有接口完全兼容
    @contextmanager
    def _conn(self):
        """
        获取数据库连接的上下文管理器
        保持与原有代码完全相同的接口
        """
        conn = None
        try:
            conn = self.connection_pool.get_connection()
            yield conn
        except Exception as e:
            logger.error(f"数据库连接错误: {e}")
            raise
        finally:
            if conn:
                self.connection_pool.return_connection(conn)

    # ── Schema 初始化 ────────────────────────────────────────
    # 以下所有方法保持与原有代码完全相同
    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    id              INTEGER,
                    symbol          TEXT,
                    shares          DOUBLE,
                    avg_cost        DOUBLE,
                    first_buy_date  TEXT,
                    sector          TEXT,
                    notes           TEXT,
                    updated_at      TEXT
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    id              INTEGER,
                    symbol          TEXT,
                    trans_type      TEXT,
                    shares          DOUBLE,
                    price           DOUBLE,
                    amount          DOUBLE,
                    commission      DOUBLE,
                    trans_date      TEXT,
                    notes           TEXT,
                    created_at      TEXT
                );

                CREATE TABLE IF NOT EXISTS corporate_actions (
                    id              INTEGER,
                    symbol          TEXT,
                    action_type     TEXT,
                    ratio           DOUBLE,
                    amount          DOUBLE,
                    ex_date         TEXT,
                    applied         INTEGER
                );

                CREATE TABLE IF NOT EXISTS goals (
                    id              INTEGER,
                    name            TEXT,
                    period_type     TEXT,
                    target_return_pct DOUBLE,
                    start_date      TEXT,
                    end_date        TEXT,
                    initial_capital DOUBLE,
                    status          TEXT,
                    created_at      TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_transactions_symbol ON transactions(symbol);
                CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(trans_date);
                CREATE INDEX IF NOT EXISTS idx_goals_status ON goals(status);
            """)
        logger.debug(f"DuckDB schema 初始化完成：{self.db_path}")

    def _ensure_table_constraints(self) -> None:
        """确保表的完整性约束在应用层实现"""
        with self._conn() as conn:
            tables = ["positions", "transactions", "corporate_actions", "goals"]
            for table in tables:
                try:
                    conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_id ON {table}(id)")
                except:
                    pass
    
    def _row_to_dict(self, row: Tuple, columns: List[str]) -> Dict:
        """将行元组转换为字典"""
        return {col: row[i] for i, col in enumerate(columns)}
    
    def _generate_id(self) -> int:
        """生成唯一ID"""
        return uuid.uuid4().int & (1 << 31) - 1
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """
        获取连接池统计信息
        
        Returns:
            Dict[str, Any]: 连接池统计信息
        """
        return self.connection_pool.get_stats()

    # ── 持仓操作 ─────────────────────────────────────────────
    # 以下所有业务方法保持与原有代码完全相同
    
    def buy(self, symbol: str, shares: float, price: float, commission: float = 0.0, 
            trans_date: str = None, notes: str = "") -> int:
        """买入股票"""
        symbol = symbol.upper().strip()
        if not symbol or not isinstance(symbol, str):
            raise ValueError("Symbol must be a non-empty string")
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")
        if commission < 0:
            raise ValueError("Commission must be non-negative")
        
        total_cost = (shares * price) + commission
        date = trans_date or datetime.now().strftime("%Y-%m-%d")
        
        with self._conn() as conn:
            trans_id = self._generate_id()
            created_at = datetime.now().isoformat()
            
            conn.execute("""
                INSERT INTO transactions (id, symbol, trans_type, shares, price, amount, commission, trans_date, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (trans_id, symbol, "BUY", shares, price, shares * price, commission, trans_date, notes, created_at))
            
            existing = self.get_position(symbol)
            if existing:
                existing_total_cost = existing["shares"] * existing["avg_cost"]
                new_total_shares = existing["shares"] + shares
                new_total_cost = existing_total_cost + total_cost
                new_avg_cost = new_total_cost / new_total_shares
                
                first_buy_date = existing["first_buy_date"]
                if not first_buy_date or first_buy_date > trans_date:
                    first_buy_date = trans_date
                
                conn.execute("""
                    UPDATE positions 
                    SET shares = ?, avg_cost = ?, first_buy_date = ?, updated_at = ?
                    WHERE symbol = ?
                """, (new_total_shares, new_avg_cost, first_buy_date, created_at, symbol))
            else:
                avg_cost_with_commission = total_cost / shares
                conn.execute("""
                    INSERT INTO positions (id, symbol, shares, avg_cost, first_buy_date, sector, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (self._generate_id(), symbol, shares, avg_cost_with_commission, trans_date, "", notes, created_at))
            
            logger.info(f"Buy order: {symbol} {shares} shares @ ${price:.2f} (commission ${commission:.2f})")
            return trans_id

    def sell(self, symbol: str, shares: float, price: float,
             commission: float = 0.0, trans_date: Optional[str] = None,
             notes: Optional[str] = None) -> float:
        """
        记录卖出
        """
        from core.exceptions import InsufficientSharesError
         
        if not symbol or not isinstance(symbol, str):
            raise ValueError("Symbol must be a non-empty string")
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")
        if commission < 0:
            raise ValueError("Commission must be non-negative")
        
        symbol = symbol.upper().strip()
        now = datetime.now().isoformat()
        date = trans_date or datetime.now().strftime("%Y-%m-%d")
        
        with self._conn() as conn:
            result = conn.execute(
                "SELECT shares, avg_cost FROM positions WHERE symbol = ?", (symbol,)
            ).fetchone()
            
            if not result:
                raise InsufficientSharesError(symbol, 0, shares)
            
            current_shares, avg_cost = result[0], result[1]
            
            logger.info(f"当前持仓：{current_shares}, 卖出仓位：{shares}")
            if current_shares < shares - 1e-6:
                raise InsufficientSharesError(symbol, current_shares, shares)
            
            realized_pnl = (price - avg_cost) * shares - commission
            remaining = current_shares - shares
            
            if remaining < 1e-6:
                conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            else:
                conn.execute(
                    "UPDATE positions SET shares = ?, updated_at = ? WHERE symbol = ?",
                    (remaining, now, symbol)
                )
            
            trans_id = self._generate_id()
            amount = shares * price
            
            conn.execute(
                """INSERT INTO transactions
                   (id, symbol, trans_type, shares, price, amount, commission, trans_date, notes, created_at)
                   VALUES (?, ?, 'SELL', ?, ?, ?, ?, ?, ?, ?)""",
                (trans_id, symbol, shares, price, amount, commission, date, notes or "", now)
            )
        
        logger.info(f"卖出记录：{symbol} {shares}股 @ ${price:.2f}，实现盈亏 ${realized_pnl:.2f}")
        return realized_pnl

    def get_all_positions(self) -> List[Dict]:
        """获取所有持仓"""
        with self._conn() as conn:
            result = conn.execute("""
                SELECT id, symbol, shares, avg_cost, first_buy_date, sector, notes, updated_at 
                FROM positions 
                ORDER BY symbol
            """).fetchall()
            
            if not result or len(result) == 0:
                return []
            
            columns = ["id", "symbol", "shares", "avg_cost", "first_buy_date", 
                      "sector", "notes", "updated_at"]
            return [self._row_to_dict(row, columns) for row in result]
    
    def get_position(self, symbol: str) -> Optional[Dict]:
        """获取特定股票的持仓"""
        with self._conn() as conn:
            result = conn.execute("""
                SELECT id, symbol, shares, avg_cost, first_buy_date, sector, notes, updated_at 
                FROM positions WHERE symbol = ?
            """, (symbol,)).fetchone()
            
            if not result or len(result) == 0:
                return []
            
            columns = ["id", "symbol", "shares", "avg_cost", "first_buy_date", 
                        "sector", "notes", "updated_at"]
            return self._row_to_dict(result, columns)

    def update_sector(self, symbol: str, sector: str) -> None:
        """更新持仓的行业分类"""
        symbol = symbol.upper().strip()
        with self._conn() as conn:
            conn.execute(
                "UPDATE positions SET sector=?, updated_at=? WHERE symbol=?",
                (sector, datetime.now().isoformat(), symbol)
            )

    def insert_transaction(self, symbol: str, trans_type: str, shares: float, 
                          price: float, commission: float = 0.0,
                          trans_date: str = None, notes: str = "") -> int:
        """插入新的交易记录"""
        if not symbol or not isinstance(symbol, str):
            raise ValueError("Symbol must be a non-empty string")
        if trans_type.upper() not in ['BUY', 'SELL', 'DIVIDEND', 'SPLIT']:
            raise ValueError("Transaction type must be BUY, SELL, DIVIDEND, or SPLIT")
        if shares <= 0:
            raise ValueError("Shares must be positive")
        if price <= 0:
            raise ValueError("Price must be positive")
        if commission < 0:
            raise ValueError("Commission must be non-negative")
        
        amount = shares * price
        if trans_date is None:
            trans_date = datetime.now().strftime("%Y-%m-%d")
        
        with self._conn() as conn:
            created_at = datetime.now().isoformat()
            trans_id = self._generate_id()
            
            conn.execute("""
                INSERT INTO transactions (id, symbol, trans_type, shares, price, amount, commission, trans_date, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (trans_id, symbol, trans_type.upper(), shares, price, amount, commission, trans_date, notes, created_at))
            
            return trans_id

    def get_transactions(self, symbol: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """获取交易记录"""
        with self._conn() as conn:
            if symbol:
                result = conn.execute("""
                    SELECT id, symbol, trans_type, shares, price, amount, commission, trans_date, notes, created_at
                    FROM transactions 
                    WHERE symbol = ? 
                    ORDER BY trans_date DESC, created_at DESC 
                    LIMIT ?
                """, (symbol, limit)).fetchall()
            else:
                result = conn.execute("""
                    SELECT id, symbol, trans_type, shares, price, amount, commission, trans_date, notes, created_at
                    FROM transactions 
                    ORDER BY trans_date DESC, created_at DESC 
                    LIMIT ?
                """, (limit,)).fetchall()
            
            if not result or len(result) == 0:
                return []
            
            columns = ["id", "symbol", "trans_type", "shares", "price", "amount", 
                      "commission", "trans_date", "notes", "created_at"]
            return [self._row_to_dict(row, columns) for row in result]
    
    def delete_transaction(self, transaction_id: int) -> bool:
        """删除交易记录"""
        with self._conn() as conn:
            result = conn.execute("""
                SELECT symbol, trans_type, shares, price, commission
                FROM transactions WHERE id = ?
            """, (transaction_id,)).fetchone()
            
            if not result:
                logger.warning(f"Transaction not found: id={transaction_id}")
                return False
            
            symbol = result[0]
            trans_type = result[1]
            shares = result[2]
            price = result[3]
            commission = result[4]
            
            conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            
            if trans_type == "BUY":
                position = self.get_position(symbol)
                if position:
                    new_shares = position["shares"] - shares
                    if new_shares > 0:
                        old_total = position["shares"] * position["avg_cost"]
                        new_total = old_total - (shares * price)
                        new_avg_cost = new_total / new_shares
                        
                        conn.execute("""
                            UPDATE positions 
                            SET shares = ?, avg_cost = ?, updated_at = ?
                            WHERE symbol = ?
                        """, (new_shares, new_avg_cost, datetime.now().isoformat(), symbol))
                    else:
                        conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            
            logger.warning(f"Transaction deleted: id={transaction_id} (corrective action)")
            return True

    def update_position(self, symbol: str, shares: float, avg_cost: float, 
                       first_buy_date: str, sector: str = "", notes: str = "") -> None:
        """插入或更新持仓"""
        if not symbol or not isinstance(symbol, str):
            raise ValueError("Symbol must be a non-empty string")
        if shares < 0:
            raise ValueError("Shares must be non-negative")
        if avg_cost <= 0:
            raise ValueError("Average cost must be positive")
        
        with self._conn() as conn:
            updated_at = datetime.now().isoformat()
            pos_id = self._generate_id()
            
            existing = conn.execute("SELECT id FROM positions WHERE symbol = ?", (symbol,)).fetchone()
            
            if existing:
                conn.execute("""
                    UPDATE positions 
                    SET shares = ?, avg_cost = ?, sector = ?, notes = ?, updated_at = ?
                    WHERE symbol = ?
                """, (shares, avg_cost, sector, notes, updated_at, symbol))
            else:
                conn.execute("""
                    INSERT INTO positions (id, symbol, shares, avg_cost, first_buy_date, sector, notes, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (pos_id, symbol, shares, avg_cost, first_buy_date, sector, notes, updated_at))
    
    def get_positions(self) -> List[Dict]:
        """获取所有持仓"""
        with self._conn() as conn:
            result = conn.execute("""
                SELECT id, symbol, shares, avg_cost, first_buy_date, sector, notes, updated_at 
                FROM positions 
                ORDER BY symbol
            """).fetchall()
            
            if not result or len(result) == 0:
                return []
            
            columns = ['id', 'symbol', 'shares', 'avg_cost', 'first_buy_date', 
                      'sector', 'notes', 'updated_at']
            return [dict(zip(columns, row)) for row in result]
    
    def delete_position(self, symbol: str) -> bool:
        """删除持仓"""
        with self._conn() as conn:
            result = conn.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
            return result.rowcount > 0
    
    def insert_corporate_action(self, symbol: str, action_type: str, ratio: float = None, 
                               amount: float = None, ex_date: str = None) -> int:
        """插入公司行为记录"""
        if ex_date is None:
            ex_date = datetime.now().strftime("%Y-%m-%d")
        
        with self._conn() as conn:
            action_id = self._generate_id()
            conn.execute("""
                INSERT INTO corporate_actions (id, symbol, action_type, ratio, amount, ex_date, applied)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (action_id, symbol, action_type, ratio, amount, ex_date, 0))
            
            return action_id
    
    def get_realized_pnl(self, symbol: Optional[str] = None) -> float:
        """计算已实现盈亏"""
        with self._conn() as conn:
            if symbol:
                result = conn.execute("""
                    SELECT symbol, shares, price, commission
                    FROM transactions 
                    WHERE symbol = ? AND trans_type = 'SELL'
                """, (symbol.upper(),)).fetchall()
            else:
                result = conn.execute("""
                    SELECT symbol, shares, price, commission
                    FROM transactions 
                    WHERE trans_type = 'SELL'
                """).fetchall()
            
            total_pnl = 0.0
            for row in result:
                sym, shares, price, commission = row
                
                buy_result = conn.execute("""
                    SELECT AVG(price) as avg_buy_price
                    FROM transactions 
                    WHERE symbol = ? AND trans_type = 'BUY'
                """, (sym,)).fetchone()
                
                avg_buy_price = buy_result[0] if buy_result[0] is not None else 0.0
                pnl = (shares * price) - (shares * avg_buy_price) - commission
                total_pnl += pnl
            
            return total_pnl

    def create_goal(self, name: str, period_type: str, target_return_pct: float,
                    start_date: str, end_date: str, initial_capital: float) -> int:
        """创建盈利目标，返回新目标ID"""
        with self._conn() as conn:
            goal_id = self._generate_id()
            created_at = datetime.now().isoformat()
            
            conn.execute("""
                INSERT INTO goals (id, name, period_type, target_return_pct, start_date, end_date, initial_capital, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (goal_id, name, period_type, target_return_pct, start_date, end_date, initial_capital, "ACTIVE", created_at))
            
            return goal_id
    
    def update_goal_status(self, goal_id: int, status: str) -> bool:
        """更新目标状态"""
        valid_statuses = ["ACTIVE", "COMPLETED", "CANCELLED"]
        if status not in valid_statuses:
            raise ValueError(f"Status must be one of: {valid_statuses}")
        
        with self._conn() as conn:
            result = conn.execute("""
                UPDATE goals SET status = ? WHERE id = ?
            """, (status, goal_id))
            
            return result.rowcount > 0
    
    def get_goals(self, status: Optional[str] = None) -> List[Dict]:
        """获取盈利目标"""
        with self._conn() as conn:
            if status:
                result = conn.execute("""
                    SELECT id, name, period_type, target_return_pct, start_date, end_date, initial_capital, status, created_at
                    FROM goals WHERE status = ? ORDER BY created_at DESC
                """, (status,)).fetchall()
            else:
                result = conn.execute("""
                    SELECT id, name, period_type, target_return_pct, start_date, end_date, initial_capital, status, created_at
                    FROM goals ORDER BY created_at DESC
                """).fetchall()
            
            if not result or len(result) == 0:
                return []
            
            columns = ["id", "name", "period_type", "target_return_pct", "start_date", 
                      "end_date", "initial_capital", "status", "created_at"]
            return [self._row_to_dict(row, columns) for row in result]

    def get_active_goals(self) -> list[dict]:
        """获取所有激活中的盈利目标"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM goals WHERE status='ACTIVE' ORDER BY created_at DESC"
            ).fetchall()
            
            if not rows or len(rows) == 0:
                return []
            columns = ["id", "name", "period_type", "target_return_pct", "start_date", 
                      "end_date", "initial_capital", "status", "created_at"]
            return [self._row_to_dict(row, columns) for row in rows]

    def get_all_goals(self) -> list[dict]:
        """获取所有目标"""
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM goals ORDER BY created_at DESC"
            ).fetchall()
            
            if not rows or len(rows) == 0:
                return []
            
            columns = ["id", "name", "period_type", "target_return_pct", "start_date", 
                      "end_date", "initial_capital", "status", "created_at"]
            return [self._row_to_dict(r, columns) for r in rows]

    def update_goal_status(self, goal_id: int, status: str) -> None:
        """更新目标状态"""
        with self._conn() as conn:
            conn.execute(
                "UPDATE goals SET status=? WHERE id=?", (status, goal_id)
            )

    def get_portfolio_summary(self, current_prices: Optional[dict] = None) -> dict:
        """计算持仓汇总指标"""
        positions = self.get_all_positions()
        if not positions:
            return {
                "total_invested": 0.0,
                "total_market_value": 0.0,
                "total_unrealized_pnl": 0.0,
                "total_unrealized_pct": 0.0,
                "total_realized_pnl": self.get_realized_pnl(),
                "position_count": 0,
            }

        total_invested = sum(p["shares"] * p["avg_cost"] for p in positions)
        total_market_value = 0.0
        prices = current_prices or {}

        for p in positions:
            price = prices.get(p["symbol"])
            if price is not None:
                total_market_value += p["shares"] * price
            else:
                total_market_value += p["shares"] * p["avg_cost"]

        unrealized_pnl = total_market_value - total_invested
        unrealized_pct = (unrealized_pnl / total_invested) if total_invested > 0 else 0.0

        return {
            "total_invested":       total_invested,
            "total_market_value":   total_market_value,
            "total_unrealized_pnl": unrealized_pnl,
            "total_unrealized_pct": unrealized_pct,
            "total_realized_pnl":   self.get_realized_pnl(),
            "position_count":       len(positions),
        }
    
    def close(self):
        """关闭数据库连接池"""
        try:
            # 在程序退出前调用正常的清理方法
            if hasattr(self, 'connection_pool'):
                self.connection_pool._cleanup()
        except Exception as e:
            # 如果已经发生错误，就静默退出
            pass
    
    def __del__(self):
        """析构函数，确保连接池被清理"""
        try:
            self.close()
        except:
            pass


# ── 模块级单例 ────────────────────────────────────────────────

_db: Optional[PortfolioDatabase] = None


def get_db(pool_size: int = 5, max_overflow: int = 10) -> PortfolioDatabase:
    """
    获取数据库单例（支持连接池配置）
    
    Args:
        pool_size: 连接池大小
        max_overflow: 最大溢出连接数
        
    Returns:
        PortfolioDatabase: 数据库实例
    """
    global _db
    if _db is None:
        _db = PortfolioDatabase(pool_size=pool_size, max_overflow=max_overflow)
    return _db
