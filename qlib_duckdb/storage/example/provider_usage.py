"""
使用示例
"""
import qlib
import pandas as pd
from qlib_duckdb import DuckDBFeatureProvider, init_qlib_with_duckdb
from qlib_duckdb import DuckDBFeatureProvider

# 方法1: 直接初始化
provider = DuckDBFeatureProvider(reg="cn")
qlib.init(provider=provider)

# 方法2: 使用便捷函数
provider = init_qlib_with_duckdb(reg="cn")

# 现在可以使用标准的 Qlib API
from qlib.data import D

# 获取数据
data = D.features(["SH600000", "SZ000001"], ["$close", "$volume"], freq="day")
print(data.head())

# 获取日历
calendar = D.calendar(start_time="2020-01-01", end_time="2020-12-31", freq="day")
print(f"Calendar length: {len(calendar)}")

# 获取标的
instruments = D.instruments(market="cn")
print(f"Number of instruments: {len(instruments)}")