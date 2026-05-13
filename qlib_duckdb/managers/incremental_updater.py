"""
增量更新管理器
"""
import pandas as pd
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
import logging
from tqdm import tqdm

from ..duckdb_connection import get_connection
from ..schema import SchemaManager
from ..storage.feature import DuckDBFeatureStorage
from ..exceptions import ValidationError
from ..config import config
from ..utils.validation import validate_price_data

logger = logging.getLogger(__name__)


class IncrementalUpdateManager:
    """增量更新管理器"""
    
    def __init__(self, reg: str = None):
        self.reg = reg or config.default_reg
        self.feature_storage = DuckDBFeatureStorage(self.reg)
    
    def update_symbol_freq(
        self,
        symbol: str,
        freq: str,
        data: pd.DataFrame,
        on_conflict: str = None
    ) -> int:
        """更新单个标的的单个频率数据"""
        if on_conflict is None:
            on_conflict = config.on_conflict
        
        if data.empty:
            logger.warning(f"No data to update for {symbol} {freq}")
            return 0
        
        # 验证数据
        try:
            validate_price_data(data)
        except ValidationError as e:
            logger.error(f"Data validation failed for {symbol} {freq}: {e}")
            raise
        
        # 写入数据
        try:
            affected = self.feature_storage.write(data, freq, on_conflict=on_conflict)
            logger.info(f"Updated {symbol} {freq}: {affected} rows affected")
            return affected
        except Exception as e:
            logger.error(f"Failed to update {symbol} {freq}: {e}")
            raise
    
    def update_symbol(
        self,
        symbol: str,
        data_dict: Dict[str, pd.DataFrame],
        on_conflict: str = None
    ) -> Dict[str, int]:
        """更新单个标的的多个频率数据"""
        results = {}
        
        for freq, data in data_dict.items():
            try:
                affected = self.update_symbol_freq(symbol, freq, data, on_conflict)
                results[freq] = affected
            except Exception as e:
                logger.error(f"Failed to update {symbol} {freq}: {e}")
                results[freq] = 0
        
        return results
    
    def update_batch(
        self,
        updates: Dict[str, Dict[str, pd.DataFrame]],  # symbol -> freq -> data
        on_conflict: str = None
    ) -> Dict[str, Dict[str, int]]:
        """批量更新多个标的"""
        results = {}
        
        for symbol, freq_data in tqdm(updates.items(), desc="Updating symbols"):
            try:
                symbol_results = self.update_symbol(symbol, freq_data, on_conflict)
                results[symbol] = symbol_results
            except Exception as e:
                logger.error(f"Failed to update symbol {symbol}: {e}")
                results[symbol] = {"error": str(e)}
        
        return results
    
    def get_latest_datetime(self, symbol: str, freq: str) -> Optional[datetime]:
        """获取某个标的的最新数据时间"""
        table_name = f"feature_{freq}"
        
        with get_connection(self.reg, read_only=False) as conn:
            result = conn.execute(f"""
                SELECT MAX(datetime) 
                FROM {table_name} 
                WHERE symbol = ?
            """, (symbol,))
            
            if result and result[0][0]:
                return result[0][0]
        
        return None
    
    def get_missing_periods(
        self,
        symbol: str,
        freq: str,
        start_time: datetime,
        end_time: datetime
    ) -> List[Tuple[datetime, datetime]]:
        """获取缺失的时间段"""
        table_name = f"feature_{freq}"
        
        with get_connection(self.reg, read_only=False) as conn:
            # 获取已有的时间点
            result = conn.execute(f"""
                SELECT datetime 
                FROM {table_name} 
                WHERE symbol = ? 
                  AND datetime >= ? 
                  AND datetime <= ?
                ORDER BY datetime
            """, (symbol, start_time, end_time))
            
            existing_times = {row[0] for row in result} if result else set()
        
        # 根据频率确定时间间隔
        if freq == "day":
            delta = timedelta(days=1)
        elif freq == "1h":
            delta = timedelta(hours=1)
        elif freq == "5m":
            delta = timedelta(minutes=5)
        else:
            # 默认按天
            delta = timedelta(days=1)
        
        # 找出缺失的时间段
        missing_periods = []
        current = start_time
        
        while current <= end_time:
            if current not in existing_times:
                # 找到缺失段的开始
                missing_start = current
                # 找到缺失段的结束
                while current <= end_time and current not in existing_times:
                    current += delta
                missing_end = current - delta
                missing_periods.append((missing_start, missing_end))
            else:
                current += delta
        
        return missing_periods
    
    def update_from_dataframe(
        self,
        freq: str,
        data: pd.DataFrame,
        symbol_col: str = "symbol",
        datetime_col: str = "datetime",
        on_conflict: str = None
    ) -> int:
        """从 DataFrame 更新数据"""
        if data.empty:
            return 0
        
        # 重命名列
        if symbol_col != "symbol":
            data = data.rename(columns={symbol_col: "symbol"})
        if datetime_col != "datetime":
            data = data.rename(columns={datetime_col: "datetime"})
        
        # 确保必要的列存在
        required_cols = ["symbol", "datetime", "open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in data.columns:
                if col in ["open", "high", "low", "close", "volume"]:
                    data[col] = pd.NA
                else:
                    raise ValueError(f"Missing required column: {col}")
        
        # 按标的分组更新
        total_affected = 0
        symbols = data["symbol"].unique()
        
        for symbol in tqdm(symbols, desc=f"Updating {freq} data"):
            symbol_data = data[data["symbol"] == symbol].copy()
            try:
                affected = self.update_symbol_freq(
                    symbol, freq, symbol_data, on_conflict
                )
                total_affected += affected
            except Exception as e:
                logger.error(f"Failed to update {symbol} in {freq}: {e}")
        
        logger.info(f"Total updated rows for {freq}: {total_affected}")
        return total_affected