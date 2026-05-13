import re
from abc import ABC
import duckdb
from qlib.data.storage import CalendarStorage, InstrumentStorage, FeatureStorage

class DuckDBBaseStorage(ABC):
    """DuckDB 存储基类"""
    # 显式定义，避免依赖 __class__.__name__ 的正则解析
    storage_name = "duckdb"

    def __init__(self, db_path: str, **kwargs):
        self.db_path = db_path
        self.conn = duckdb.connect(db_path)
        # 必须手动调用父类初始化（关键！）
        super().__init__(**kwargs)

    def _execute_query(self, query: str, params=None):
        """统一的查询执行方法"""
        return self.conn.execute(query, params or []).fetchdf()