"""
Qlib Provider 实现
"""
from typing import Dict, Optional, Any, List
#from qlib.data.storage import DataProvider
from .feature import DuckDBFeatureStorage
from .calendar import DuckDBCalendarStorage
from .instrument import DuckDBInstrumentStorage
from ..config import config
from ..duckdb_connection import DuckDBConnection
import logging
from ..compat import DataProvider

logger = logging.getLogger(__name__)

class DuckDBFeatureProvider(DataProvider):
    """DuckDB FeatureProvider 实现
    
    将 DuckDB Storage 适配到 Qlib 的 Provider 接口
    """
    
    def __init__(self, reg: str = None, **kwargs):
        """
        初始化 DuckDB FeatureProvider
        
        Parameters
        ----------
        reg : str, optional
            市场区域 (cn, us, hk 等)
        **kwargs : dict
            其他参数传递给 Storage
        """
        self.reg = reg or config.default_reg
        self.kwargs = kwargs
        
        # 初始化 Storage
        self.feature_storage = DuckDBFeatureStorage(self.reg, **kwargs)
        self.calendar_storage = DuckDBCalendarStorage(self.reg, **kwargs)
        self.instrument_storage = DuckDBInstrumentStorage(self.reg, **kwargs)
        
        # 多市场支持
        self._market_connections: Dict[str, DuckDBConnection] = {}
        
        logger.info(f"Initialized DuckDBFeatureProvider for region: {self.reg}")
    
    def _ensure_connection(self, reg: str = None) -> DuckDBConnection:
        """确保指定市场的连接存在"""
        if reg is None:
            reg = self.reg
        
        if reg not in self._market_connections:
            self._market_connections[reg] = DuckDBConnection.get_connection(reg)
        
        return self._market_connections[reg]
    
    def get_connection(self, reg: str = None) -> DuckDBConnection:
        """获取数据库连接"""
        return self._ensure_connection(reg)
    
    def close_all(self):
        """关闭所有连接"""
        for conn in self._market_connections.values():
            conn.close()
        self._market_connections.clear()
        logger.info("Closed all database connections")
    
    # ============== DataProvider 接口实现 ==============
    
    def get_config(self) -> Dict[str, Any]:
        """获取配置"""
        return {
            "reg": self.reg,
            "db_root_path": config.db_root_path,
            "memory_limit": config.memory_limit,
            "enable_cache": config.enable_cache,
        }
    
    def set_config(self, **kwargs):
        """设置配置"""
        for key, value in kwargs.items():
            if hasattr(config, key):
                setattr(config, key, value)
                logger.info(f"Updated config: {key}={value}")
    
    def feature(self, feature_field: str = None) -> DuckDBFeatureStorage:
        """获取特征存储"""
        if feature_field is not None:
            logger.warning(f"feature_field parameter '{feature_field}' is ignored in DuckDBFeatureProvider")
        
        return self.feature_storage
    
    def calendar(self) -> DuckDBCalendarStorage:
        """获取日历存储"""
        return self.calendar_storage
    
    def instrument(self) -> DuckDBInstrumentStorage:
        """获取标的存储"""
        return self.instrument_storage
    
    def list_instruments(
        self, 
        instruments: List[str], 
        start_time: Optional[str] = None, 
        end_time: Optional[str] = None, 
        freq: str = "day", 
        as_list: bool = False
    ) -> Any:
        """列出可用的标的
        
        这是 Qlib Provider 的标准接口
        """
        try:
            # 获取标的存储
            instr_storage = self.instrument()
            
            # 获取符合条件的标的
            instruments_df = instr_storage.get_instruments(
                instruments, start_time, end_time
            )
            
            if as_list:
                return instruments_df["symbol"].tolist() if not instruments_df.empty else []
            else:
                return instruments_df
            
        except Exception as e:
            logger.error(f"Failed to list instruments: {e}")
            return [] if as_list else None
    
    def instruments(
        self, 
        market: str = "all", 
        filter_pipe: Optional[List] = None
    ) -> List[str]:
        """获取市场所有标的
        
        这是 Qlib 的标准接口
        
        Parameters
        ----------
        market : str
            市场名称
        filter_pipe : list, optional
            过滤管道 (暂未实现)
        
        Returns
        -------
        list
            标的列表
        """
        try:
            # 获取所有标的
            all_instruments = self.instrument_storage.get_all_instruments()
            
            if all_instruments.empty:
                logger.warning(f"No instruments found for market {market}")
                return []
            
            # 简单过滤逻辑
            if market != "all":
                # 根据标的代码前缀过滤市场
                if market == "cn":
                    # A 股
                    filtered = all_instruments[
                        all_instruments["symbol"].str.startswith(("SH", "SZ", "BJ"))
                    ]
                elif market == "us":
                    # 美股
                    filtered = all_instruments[
                        all_instruments["symbol"].str.startswith(("US", "NASDAQ", "NYSE"))
                    ]
                elif market == "hk":
                    # 港股
                    filtered = all_instruments[
                        all_instruments["symbol"].str.startswith(("HK",))
                    ]
                else:
                    # 其他市场，返回全部
                    filtered = all_instruments
                    logger.warning(f"Unknown market '{market}', returning all instruments")
            else:
                filtered = all_instruments
            
            # 应用过滤管道 (如果提供)
            if filter_pipe:
                logger.warning("filter_pipe parameter is not yet implemented in DuckDBFeatureProvider")
            
            instruments_list = filtered["symbol"].tolist()
            logger.info(f"Found {len(instruments_list)} instruments for market {market}")
            
            return instruments_list
            
        except Exception as e:
            logger.error(f"Failed to get instruments for market {market}: {e}")
            return []
    
    def get_all_calendar(self, freq: str) -> List[str]:
        """获取所有日历（历史+未来）"""
        return self.calendar_storage.get_all_calendar(freq)
    
    def get_calendar(
        self, 
        freq: str, 
        future: bool = False, 
        start_time: Optional[str] = None, 
        end_time: Optional[str] = None
    ) -> List[str]:
        """获取日历"""
        return self.calendar_storage.get_calendar(freq, future, start_time, end_time)
    
    def features(
        self, 
        instruments: List[str], 
        fields: List[str], 
        start_time: str, 
        end_time: str, 
        freq: str
    ) -> Any:
        """获取特征数据
        
        这是 Qlib 的标准接口
        
        Parameters
        ----------
        instruments : list
            标的列表
        fields : list
            字段列表
        start_time : str
            开始时间
        end_time : str
            结束时间
        freq : str
            频率
        
        Returns
        -------
        pd.DataFrame
            特征数据
        """
        return self.feature_storage.fetch_all(
            instruments, fields, start_time, end_time, freq
        )
    
    def get_instruments_dates(
        self, 
        instruments: List[str], 
        start_time: str, 
        end_time: str, 
        freq: str
    ) -> Dict[str, List[str]]:
        """获取标的的日期范围"""
        result = {}
        
        for instrument in instruments:
            try:
                dates = self.feature_storage.get_symbol_dates(instrument, freq)
                
                # 过滤时间范围
                filtered_dates = []
                for date_str in dates:
                    if start_time and date_str < start_time:
                        continue
                    if end_time and date_str > end_time:
                        continue
                    filtered_dates.append(date_str)
                
                result[instrument] = filtered_dates
                
            except Exception as e:
                logger.warning(f"Failed to get dates for {instrument}: {e}")
                result[instrument] = []
        
        return result
    
    def clear_cache(self):
        """清除缓存"""
        # 清除 Storage 缓存
        if hasattr(self.feature_storage, '_cache'):
            self.feature_storage._cache.clear()
        
        if hasattr(self.calendar_storage, '_cache'):
            self.calendar_storage._cache.clear()
        
        if hasattr(self.instrument_storage, '_cache'):
            self.instrument_storage._cache.clear()
        
        # 清除连接池缓存
        DuckDBConnection.close_all()
        
        logger.info("Cleared all caches")
    
    def get_table_info(self, freq: str = None) -> Dict[str, Any]:
        """获取表信息"""
        from ..schema import SchemaManager
        
        if freq:
            table_name = f"feature_{freq}"
            if not self.feature_storage._table_exists(table_name):
                return {"error": f"Table {table_name} does not exist"}
            
            from ..utils.validation import get_table_stats
            return get_table_stats(self.reg, table_name)
        else:
            return SchemaManager.get_table_info(self.reg)
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all()
    
    def __del__(self):
        """析构函数，确保连接关闭"""
        try:
            self.close_all()
        except:
            pass


# 便捷函数
def init_qlib_with_duckdb(
    reg: str = None,
    provider_uri: str = None,
    **kwargs
) -> DuckDBFeatureProvider:
    """初始化 Qlib 使用 DuckDB 后端
    
    Parameters
    ----------
    reg : str, optional
        市场区域
    provider_uri : str, optional
        兼容 Qlib 接口，实际不使用
    **kwargs : dict
        传递给 DuckDBFeatureProvider 的参数
    
    Returns
    -------
    DuckDBFeatureProvider
        初始化的 Provider
    """
    import qlib
    
    # 创建 Provider
    provider = DuckDBFeatureProvider(reg=reg, **kwargs)
    
    # 初始化 Qlib
    qlib.init(provider=provider)
    
    logger.info(f"Qlib initialized with DuckDB backend for region: {reg}")
    return provider


# 兼容性函数
def get_duckdb_provider(reg: str = None, **kwargs) -> DuckDBFeatureProvider:
    """获取 DuckDB Provider (兼容旧版)"""
    return DuckDBFeatureProvider(reg=reg, **kwargs)