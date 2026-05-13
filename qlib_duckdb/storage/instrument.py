from typing import Dict, List, Tuple
from .base import DuckDBBaseStorage
from qlib.data.storage import CalendarStorage, InstrumentStorage, FeatureStorage

class DuckDBInstrumentStorage(DuckDBBaseStorage, InstrumentStorage):
    """DuckDB 标的存储"""
    
    def __init__(self, market: str, freq: str, db_path: str, **kwargs):
        self.market = market
        self.freq = freq
        super().__init__(db_path, market=market, freq=freq, **kwargs)

    @property
    def data(self) -> Dict[str, List[Tuple[str, str]]]:
        """返回 {symbol: [(start_date, end_date)]}"""
        df = self._execute_query(
            #"SELECT symbol, start_date, end_date FROM duckdb_instruments WHERE market=?",
            "SELECT symbol, start_date, end_date FROM duckdb_instruments",
            [self.market]
        )
        result = {}
        for _, row in df.iterrows():
            symbol = row['symbol']
            if symbol not in result:
                result[symbol] = []
            result[symbol].append((row['start_date'], row['end_date']))
        return result

    def __getitem__(self, symbol: str):
        print(symbol)
        return self.data[symbol]

    def __len__(self):
        return len(self.data)