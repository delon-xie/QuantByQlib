"""
index_manager.py 使用示例
"""
from qlib_duckdb.managers import IndexManager, CalendarManager

# 1. 指数管理器示例
reg = "cn"
index_manager = IndexManager(reg=reg)

# 从文件导入指数
result = index_manager.import_index_from_file(
    "csi300.txt", 
    index_type="csi", 
    description="沪深300指数"
)

# 从目录批量导入
results = index_manager.import_indexes_from_directory("./indices/")

# 获取指数成分股
members = index_manager.get_index_members("csi300", as_of_date="2023-12-31")

# 同步 Qlib 原始数据
index_manager.sync_from_qlib(f"~/.qlib/qlib_data/{reg}_data")

# 2. 日历管理器示例
calendar_manager = CalendarManager(reg=reg)

# 从文件导入日历
result = calendar_manager.import_calendar_from_file(
    "day.txt", 
    freq="day", 
    future=False
)

# 从目录批量导入
results = calendar_manager.import_calendars_from_directory("./calendars/")

# 生成未来日历
future_calendar = calendar_manager.generate_future_calendar("day", days=365)

# 更新未来日历
calendar_manager.update_future_calendar("day", days=180)

# 同步 Qlib 原始日历
calendar_manager.sync_from_qlib(f"~/.qlib/qlib_data/{reg}_data")

# 获取日历统计
stats = calendar_manager.get_calendar_stats("day")
print(f"历史日历: {stats['history']['count']} 个日期")
print(f"未来日历: {stats['future']['count']} 个日期")