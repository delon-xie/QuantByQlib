from qlib_duckdb.config import DuckDBConfig
from qlib_duckdb import DuckDBFeatureProvider

# 全局配置
DuckDBConfig.set_default(
    db_root_path="./my_duckdb_data",  # 自定义数据库路径
    memory_limit='32GB',              # 内存限制
    default_threads=8,                # 默认线程数
    enable_cache=True,                # 启用缓存
    log_level="INFO"                  # 日志级别
)

# 然后初始化
provider = DuckDBFeatureProvider(reg="cn")