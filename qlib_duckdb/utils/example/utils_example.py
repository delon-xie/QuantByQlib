"""
工具函数使用示例
"""
from qlib_duckdb.utils import *

# 1. Qlib 工具
# 日期格式转换
qlib_date = convert_to_qlib_date("2023-12-31")  # "20231231"
std_date = convert_qlib_date("20231231")  # "2023-12-31"

# 字段映射
qlib_fields = convert_to_qlib_fields(["open", "close", "volume"])
# 返回: ["$open", "$close", "$volume"]

# 2. DuckDB 工具
from qlib_duckdb.duckdb_connection import get_connection

with get_connection("cn") as conn:
    # 优化连接
    optimize_duckdb_connection(conn.connection, {"memory_limit": "32GB", "threads": 8})
    
    # 分析表
    stats = analyze_table(conn.connection, "feature_day")
    print(f"表统计: {stats}")
    
    # 执行带统计的查询
    result = execute_query_with_stats(
        conn.connection,
        "SELECT COUNT(*) FROM feature_day",
        explain=True
    )
    print(f"查询统计: {result['stats']}")

# 3. 性能监控
monitor = PerformanceMonitor("data_migration")
monitor.start("load_data")
# ... 加载数据操作 ...
elapsed = monitor.end("load_data")
print(f"加载数据耗时: {elapsed:.2f}秒")

# 使用装饰器
@time_it
def process_data():
    import time
    time.sleep(1)

# 使用上下文管理器
with timer_context("数据处理"):
    # 数据处理代码
    pass

# 4. 基准测试
benchmark = QueryBenchmark(lambda: get_connection("cn"))
results = benchmark.benchmark_query(
    query_name="count_query",
    sql="SELECT COUNT(*) FROM feature_day",
    iterations=10
)
print(f"基准测试结果: {results}")

# 5. 生成性能报告
report_file = generate_performance_report("cn", "./reports")
print(f"性能报告: {report_file}")