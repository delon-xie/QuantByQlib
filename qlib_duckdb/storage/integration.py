import qlib
from pathlib import Path
from typing import Union, Optional
from qlib.constant import REG_CN, REG_US


def init_from_duckdb(
    db_path: Union[str, Path],
    region: str = REG_US,
    enable_cache: bool = True,
    redis_port: Optional[int] = 6379,
    cache_memory: int = 8 * 1024**3,  # 8GB
    max_workers: int = 1,  # 限制线程数
    **kwargs
):
    """
    从 DuckDB 数据库初始化 Qlib
    
    Parameters
    ----------
    db_path : str or Path
        DuckDB 数据库文件路径
    region : str
        区域代码，默认为 REG_US（美股）
    enable_cache : bool
        是否启用缓存
    redis_port : int, optional
        Redis 端口，None 表示禁用
    cache_memory : int
        缓存内存大小（字节）
    **kwargs
        传递给 qlib.init 的其他参数
    """
    # 转换为 Path 对象
    db_path = Path(db_path)
    
    # 构建 provider_uri 映射
    # 注意：即使使用 DuckDB，仍然需要提供有效的 provider_uri
    # 因为 Qlib 内部仍然依赖这个路径来构建某些对象
    provider_uri = {
        "day": db_path.parent.absolute().as_posix(),
        "1min": db_path.parent.absolute().as_posix(),
    }
    
    # 准备自定义的 provider 配置
    # 参考 integration.py 中的配置方式
    calendar_provider = {
        "class": "LocalCalendarProvider",
        "module_path": "qlib.data.data",
        "kwargs": {
            "backend": {
                "class": "DuckDBCalendarStorage",
                "module_path": "your_module.calendar",  # 替换为你的模块路径
                "kwargs": {"db_path": str(db_path)},
            },
        },
    }
    
    feature_provider = {
        "class": "LocalFeatureProvider",
        "module_path": "qlib.data.data",
        "kwargs": {
            "backend": {
                "class": "DuckDBFeatureStorage",
                "module_path": "your_module.feature",  # 替换为你的模块路径
                "kwargs": {"db_path": str(db_path)},
            },
        },
    }
    
    import qlib
    from qlib.config import C
    
    # 1. 设置单线程模式，避免并发问题
    C["kernels"] = 1
    C["enable_multiprocess"] = False
    
    # 2. 初始化，禁用缓存和 Redis
    # 初始化 Qlib
    qlib.init(
        provider_uri=provider_uri,
        region=region,
        auto_mount=False,
        redis_port=redis_port if enable_cache else -1,
        cache_memory=cache_memory if enable_cache else 0,
        # 文档4中显示可以配置自定义的 provider
        calendar_provider=calendar_provider,
        feature_provider=feature_provider,
        kernels=1,  # 单核运行
        clear_mem_cache=True,
        **kwargs
    )


# 使用示例
if __name__ == "__main__":
    # 初始化 DuckDB 存储的 Qlib
    init_from_duckdb(
        db_path="/path/to/your/data.duckdb",
        region=REG_US,
        enable_cache=True,
        redis_port=6379
    )
    
    # 使用 Qlib
    from qlib.data import D
    data = D.features(["AAPL"], ["$close"], start_time="2020-01-01")
    print(data.head())