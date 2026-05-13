"""
DuckDB 后端配置模块
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class DuckDBConfig:
    """DuckDB 配置类"""
    
    # 数据库根路径
    db_root_path: str = field(default_factory=lambda: os.path.expanduser("~/.qlib/duckdb"))
    
    # 内存限制
    memory_limit: str = "16GB"
    
    # 线程数配置
    default_threads: int = 4
    
    # 连接池大小
    connection_pool_size: int = 5
    
    # 各频率建议的线程数
    freq_threads_map: Dict[str, int] = field(default_factory=lambda: {
        "day": 4,
        "week": 2,
        "3day": 2,
        "1h": 6,
        "4h": 6,
        "5m": 8,
        "15m": 8,
        "30m": 8,
        "1m": 16,
        "1s": 16
    })
    
    # 默认市场
    default_reg: str = "cn"
    
    # 是否启用查询缓存
    enable_cache: bool = True
    
    # 缓存大小
    cache_size: int = 1000
    
    # 日志级别
    log_level: str = "INFO"
    
    # 迁移时批量大小
    migrate_batch_size: int = 10000
    
    # 增量更新冲突处理策略
    on_conflict: str = "replace"  # replace/ignore/error
    
    _instance: Optional['DuckDBConfig'] = None
    
    def __post_init__(self):
        """初始化后处理"""
        # 确保数据库目录存在
        os.makedirs(self.db_root_path, exist_ok=True)
    
    @classmethod
    def get_instance(cls) -> 'DuckDBConfig':
        """获取配置单例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def set_default(cls, **kwargs):
        """设置默认配置"""
        instance = cls.get_instance()
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
    
    def get_db_path(self, reg: str) -> str:
        """获取数据库文件路径"""
        return os.path.join(self.db_root_path, f"{reg}_data.duckdb")
    
    def get_threads_for_freq(self, freq: str) -> int:
        """获取指定频率的建议线程数"""
        return self.freq_threads_map.get(freq, self.default_threads)


# 全局配置实例
config = DuckDBConfig.get_instance()