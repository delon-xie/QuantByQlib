import pandas as pd
import numpy as np
from .base import DuckDBBaseStorage
from qlib.data.storage import FeatureStorage

class DuckDBFeatureStorage(DuckDBBaseStorage, FeatureStorage):
    """DuckDB 特征存储（核心：通过切片读取）"""
    
    def __init__(self, instrument: str, field: str, freq: str, db_path: str, **kwargs):
        self.instrument = instrument
        self.field = field
        self.freq = freq
        super().__init__(db_path, instrument=instrument, field=field, freq=freq, **kwargs)

    def __getitem__(self, s: slice) -> pd.Series:
        """实现切片查询：feature_storage[0:10]"""
        # 1. 将日历索引转换为实际日期（此处需结合你的日历表逻辑）
        # 假设你有一张日历映射表 calendar_map(index, date)
        # 2. 查询 DuckDB
        query = """
            SELECT calendar, value 
            FROM duckdb_features 
            WHERE instrument=? AND field=? AND freq=?
                AND index BETWEEN ? AND ?
            ORDER BY index
        """
        df = self._execute_query(query, [
            self.instrument, self.field, self.freq, 
            s.start or 0, s.stop or 2**31-1
        ])
        
        if df.empty:
            return pd.Series(dtype=np.float32)
        
        # 返回 index 为整数索引的 Series（Qlib 内部通过日历映射日期）
        return pd.Series(
            data=df['value'].values, 
            index=pd.RangeIndex(start=s.start, stop=s.start + len(df))
        )

    @property
    def data(self) -> pd.Series:
        """返回完整数据（实现基类属性）"""
        return self[:]  # 调用上面的切片方法