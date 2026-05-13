"""
DuckDB 连接管理 - 带连接池版本
添加连接池管理功能，close()方法改为归还连接到池中
"""

import duckdb
import contextlib
import threading
import queue
import atexit
from typing import Dict, Optional, Any, List, Tuple
from .config import config
from .exceptions import ConnectionError
import logging

logger = logging.getLogger(__name__)


class DuckDBConnectionPool:
    """DuckDB连接池管理类"""
    
    def __init__(self, reg: str, pool_size: int = 5, max_overflow: int = 10, read_only: bool = False):
        """
        初始化连接池
        
        Args:
            reg: 市场区域标识
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
            read_only: 是否只读连接
        """
        self.reg = reg
        self.read_only = read_only
        self.db_path = config.get_db_path(reg)
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
        atexit.register(self._cleanup_silent)
        
    def _initialize_pool(self):
        """初始化连接池中的连接"""
        for _ in range(self.pool_size):
            conn = self._create_connection()
            self._pool.put(conn)
            
    def _create_connection(self):
        """创建新的数据库连接"""
        try:
            # 使用内存数据库的特殊处理
            if self.db_path == ':memory:' or ':memory:' in str(self.db_path):
                # 为每个连接创建独立的内存数据库
                unique_path = f":memory:{id(self)}_{self._connections_created}"
                conn = duckdb.connect(unique_path, read_only=self.read_only)
            else:
                conn = duckdb.connect(database=str(self.db_path), read_only=self.read_only)
            
            # 设置性能参数
            conn.execute(f"PRAGMA threads=2")
            self._connections_created += 1
            return conn
                
        except Exception as e:
            raise ConnectionError(f"Failed to create connection to DuckDB at {self.db_path}: {e}")
    
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
        这个方法不记录日志，防止在程序退出时与logging模块冲突
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
                "reg": self.reg,
                "db_path": str(self.db_path),
                "pool_size": self.pool_size,
                "pool_available": self._pool.qsize(),
                "max_overflow": self.max_overflow,
                "overflow": self._overflow,
                "active_connections": self._active_connections,
                "connections_created": self._connections_created
            }


class DuckDBConnection:
    """DuckDB 连接管理类 - 带连接池版本"""
    
    def __init__(self, reg: str, read_only: bool = False, pool_size: int = 5, max_overflow: int = 10):
        """初始化连接
        
        Args:
            reg: 市场区域标识
            read_only: 是否只读连接
            pool_size: 连接池大小
            max_overflow: 最大溢出连接数
        """
        self.reg = reg
        self.read_only = read_only
        self.db_path = config.get_db_path(reg)
        self._connection_pool = None
        self._conn = None
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._init_connection_pool()
    
    def _init_connection_pool(self):
        """初始化连接池"""
        try:
            if self._connection_pool is None:
                self._connection_pool = DuckDBConnectionPool(
                    reg=self.reg,
                    pool_size=self._pool_size,
                    max_overflow=self._max_overflow,
                    read_only=self.read_only
                )
                logger.info(f"Initialized connection pool for DuckDB: {self.db_path} "
                          f"(pool_size={self._pool_size}, max_overflow={self._max_overflow}, read_only={self.read_only})")
                
        except Exception as e:
            raise ConnectionError(f"Failed to initialize connection pool for DuckDB at {self.db_path}: {e}")
    
    def _get_connection_from_pool(self):
        """从连接池获取连接"""
        if self._connection_pool is None:
            self._init_connection_pool()
        return self._connection_pool.get_connection()
    
    def _return_connection_to_pool(self, conn):
        """归还连接到连接池"""
        if self._connection_pool and conn:
            self._connection_pool.return_connection(conn)
    
    @property
    def connection(self):
        """获取底层的 DuckDB 连接"""
        if self._conn is None:
            self._conn = self._get_connection_from_pool()
        return self._conn
    
    def execute(self, sql: str, params: tuple = None, fetch: bool = True) -> Any:
        """执行 SQL 语句
        
        Args:
            sql: SQL 语句
            params: 参数元组
            fetch: 是否获取结果
            
        Returns:
            SELECT 查询返回结果列表，INSERT/UPDATE/DELETE 返回影响行数
        """
        try:
            cursor = self.connection.cursor()
            
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            
            if fetch:
                sql_upper = sql.strip().upper()
                if sql_upper.startswith(("SELECT", "SHOW", "PRAGMA", "EXPLAIN", "DESCRIBE")):
                    return cursor.fetchall()
                elif sql_upper.startswith("INSERT"):
                    # 返回插入的行数
                    result = cursor.fetchone()
                    return result[0] if result else 0
                elif sql_upper.startswith(("UPDATE", "DELETE")):
                    # 返回影响的行数
                    return cursor.rowcount
                elif sql_upper.startswith("CREATE"):
                    # 创建表操作，返回受影响的行数（通常是0）
                    return 0
            return None
                
        except Exception as e:
            logger.error(f"SQL execution failed: {sql[:100]}... Error: {e}")
            raise
    
    def executemany(self, sql: str, params_list: List[tuple]) -> int:
        """执行批量 SQL 语句
        
        Args:
            sql: SQL 语句
            params_list: 参数列表
            
        Returns:
            总共影响的行数
        """
        try:
            cursor = self.connection.cursor()
            cursor.executemany(sql, params_list)
            return cursor.rowcount
                
        except Exception as e:
            logger.error(f"SQL batch execution failed: {sql[:100]}... Error: {e}")
            raise
    
    def fetchone(self, sql: str, params: tuple = None) -> Optional[Tuple]:
        """执行查询并返回单行结果"""
        try:
            cursor = self.connection.cursor()
            
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            
            return cursor.fetchone()
                
        except Exception as e:
            logger.error(f"SQL fetchone failed: {sql[:100]}... Error: {e}")
            raise
    
    def fetchall(self, sql: str, params: tuple = None) -> List[Tuple]:
        """执行查询并返回所有结果"""
        try:
            cursor = self.connection.cursor()
            
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            
            return cursor.fetchall()
                
        except Exception as e:
            logger.error(f"SQL fetchall failed: {sql[:100]}... Error: {e}")
            raise
    
    def close(self):
        """关闭连接 - 修改为归还到连接池而不实际关闭"""
        if self._conn:
            try:
                # 检查连接是否有效
                try:
                    self._conn.execute("SELECT 1")
                except:
                    # 连接无效，创建新的代替
                    self._conn.close()
                    self._conn = None
                    return
                
                # 归还连接到连接池
                self._return_connection_to_pool(self._conn)
                logger.debug(f"Connection returned to pool: {self.db_path}")
            except Exception as e:
                logger.warning(f"Error while returning connection to pool: {e}")
            finally:
                self._conn = None
    
    def __enter__(self):
        """上下文管理器入口"""
        if self._conn is None:
            self._conn = self._get_connection_from_pool()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出 - 修改为归还连接到池中"""
        self.close()
    
    def __del__(self):
        """析构函数 - 修改为不自动关闭，由连接池管理"""
        pass
    
    def is_closed(self) -> bool:
        """检查连接是否已关闭"""
        if self._conn is None:
            return True
        
        try:
            # 尝试执行一个简单查询
            self._conn.execute("SELECT 1")
            return False
        except Exception:
            return True
    
    def ping(self) -> bool:
        """检查连接是否可用"""
        try:
            result = self.execute("SELECT 1", fetch=True)
            return result is not None and len(result) > 0
        except Exception:
            return False
        
    def register(self, view_name: str, python_object: object) -> bool:
        """注册 Python 对象为临时视图
        
        Args:
            view_name: 视图名称
            python_object: 要注册的 Python 对象
            
        Returns:
            bool: 注册是否成功
        """
        if self._conn is None:
            raise ConnectionError(f"Connection is not initialized for register: {view_name}")
        
        if python_object is None:
            raise ValueError(f"Cannot register None object as {view_name}")
        
        try:
            import pandas as pd
            import numpy as np
            
            # 检查支持的对象类型
            if isinstance(python_object, pd.DataFrame):
                self._conn.register(view_name, python_object)
                logger.info(f"Registered DataFrame as {view_name}, shape: {python_object.shape}")
                return True
                
            elif isinstance(python_object, np.ndarray):
                # 转换 numpy array 为 DataFrame
                df = pd.DataFrame(python_object)
                self._conn.register(view_name, df)
                logger.info(f"Registered numpy array as {view_name}, shape: {python_object.shape}")
                return True
                
            else:
                # 尝试其他类型
                self._conn.register(view_name, python_object)
                logger.info(f"Registered object as {view_name}, type: {type(python_object)}")
                return True
                
        except Exception as e:
            logger.error(f"Register failed for {view_name}: {e}")
            return False
    
    def get_pool_stats(self) -> Dict[str, Any]:
        """获取连接池统计信息"""
        if self._connection_pool:
            return self._connection_pool.get_stats()
        return {}


# 连接池管理
_connection_pools: Dict[str, DuckDBConnectionPool] = {}
_connection_pools_lock = threading.Lock()


def get_connection_pool(reg: str, read_only: bool = False, pool_size: int = 5, max_overflow: int = 10) -> DuckDBConnectionPool:
    """获取或创建连接池
    
    Args:
        reg: 市场区域标识
        read_only: 是否只读连接
        pool_size: 连接池大小
        max_overflow: 最大溢出连接数
        
    Returns:
        DuckDBConnectionPool 实例
    """
    pool_key = f"{reg}_{read_only}"
    
    with _connection_pools_lock:
        if pool_key not in _connection_pools:
            _connection_pools[pool_key] = DuckDBConnectionPool(
                reg=reg,
                pool_size=pool_size,
                max_overflow=max_overflow,
                read_only=read_only
            )
            logger.info(f"Created connection pool: {pool_key}")
        
        return _connection_pools[pool_key]


# 便捷函数
def get_connection(reg: str = None, read_only: bool = False, pool_size: int = 5, max_overflow: int = 10) -> DuckDBConnection:
    """获取数据库连接（带连接池）
    
    Args:
        reg: 市场区域标识
        read_only: 是否只读连接
        pool_size: 连接池大小
        max_overflow: 最大溢出连接数
        
    Returns:
        DuckDBConnection 实例
    """
    if reg is None:
        reg = config.default_reg
    
    return DuckDBConnection(reg, read_only, pool_size, max_overflow)


@contextlib.contextmanager
def connection_context(reg: str = None, read_only: bool = False, pool_size: int = 5, max_overflow: int = 10):
    """连接上下文管理器（带连接池）
    
    Args:
        reg: 市场区域标识
        read_only: 是否只读连接
        pool_size: 连接池大小
        max_overflow: 最大溢出连接数
        
    Yields:
        DuckDBConnection 实例
    """
    conn = get_connection(reg, read_only, pool_size, max_overflow)
    try:
        yield conn
    finally:
        conn.close()


def cleanup_all_pools():
    """清理所有连接池"""
    with _connection_pools_lock:
        for pool_key, pool in _connection_pools.items():
            try:
                pool._cleanup()
                logger.info(f"Cleaned up connection pool: {pool_key}")
            except Exception as e:
                logger.error(f"Error cleaning up pool {pool_key}: {e}")
        _connection_pools.clear()


# 注册清理函数
atexit.register(cleanup_all_pools)