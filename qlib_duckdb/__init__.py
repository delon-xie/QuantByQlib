"""
qlib-duckdb 主包
"""
from .version import __version__
from .config import DuckDBConfig, config
from .duckdb_connection import DuckDBConnection, get_connection
from .storage.provider import DuckDBFeatureProvider
from .managers.data_migrate import DataMigrateManager
from .managers.incremental_updater import IncrementalUpdateManager
from .managers.bin_exporter import BinExportManager
from .utils.logging_setup import setup_logging

# 初始化日志
setup_logging()

# 导出主要接口
__all__ = [
    '__version__',
    'DuckDBConfig',
    'config',
    'DuckDBConnection', 
    'get_connection',
    'DuckDBFeatureProvider',
    'DataMigrateManager',
    'IncrementalUpdateManager',
    'BinExportManager',
    'setup_logging',
]