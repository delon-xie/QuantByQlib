import pandas as pd
from typing import List, Union
from .base import DuckDBBaseStorage
from qlib.data.storage import CalendarStorage, InstrumentStorage, FeatureStorage

class DuckDBCalendarStorage(DuckDBBaseStorage, CalendarStorage):
    """DuckDB 日历存储（必须符合 Qlib 0.9.7 CalendarStorage 接口）"""
    
    def __init__(self, freq: str, future: bool, db_path: str, **kwargs):
        # 注意：必须按 Qlib 基类顺序传参 (freq, future)
        self.freq = freq
        self.future = future
        super().__init__(db_path, freq=freq, future=future, **kwargs)

    @property
    def data(self) -> List[str]:
        """实现基类要求的 data 属性（返回日期字符串列表）"""
        df = self._execute_query(
            "SELECT DISTINCT calendar FROM duckdb_calendar WHERE freq=? AND future=? ORDER BY calendar",
            [self.freq, self.future]
        )
        return df['calendar'].astype(str).tolist()

    def __getitem__(self, i: Union[int, slice]) -> Union[str, List[str]]:
        """支持切片查询，如 calendar[0] 或 calendar[1:5]"""
        all_dates = self.data
        return all_dates[i]

    def __len__(self) -> int:
        return len(self.data)

    # 以下方法按需实现（如只需读，可抛异常）
    def clear(self):
        raise NotImplementedError("ReadOnly Storage")

    def extend(self, values):
        self.conn.execute(
            "INSERT INTO duckdb_calendar (freq, future, calendar) VALUES (?, ?, ?)",
            [self.freq, self.future, values]
        )