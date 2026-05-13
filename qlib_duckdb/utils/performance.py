"""
性能监控和基准测试工具
"""
import time
import gc
import psutil
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Callable, Tuple
import logging
from functools import wraps
from contextlib import contextmanager
import warnings
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """性能监控器"""
    
    def __init__(self, name: str = "default"):
        self.name = name
        self.metrics = {}
        self._start_times = {}
    
    def start(self, operation: str):
        """开始计时"""
        self._start_times[operation] = time.time()
    
    def end(self, operation: str) -> float:
        """结束计时并返回耗时（秒）"""
        if operation not in self._start_times:
            warnings.warn(f"Operation {operation} was not started")
            return 0.0
        
        elapsed = time.time() - self._start_times[operation]
        
        if operation not in self.metrics:
            self.metrics[operation] = []
        
        self.metrics[operation].append(elapsed)
        del self._start_times[operation]
        
        return elapsed
    
    def get_stats(self, operation: str = None) -> Dict[str, Any]:
        """获取统计信息"""
        if operation:
            if operation not in self.metrics:
                return {}
            
            times = self.metrics[operation]
            if not times:
                return {}
            
            return {
                "operation": operation,
                "count": len(times),
                "total_time": sum(times),
                "avg_time": sum(times) / len(times),
                "min_time": min(times),
                "max_time": max(times),
                "last_time": times[-1],
                "times": times
            }
        else:
            # 所有操作的统计
            all_stats = {}
            for op in self.metrics:
                all_stats[op] = self.get_stats(op)
            return all_stats
    
    def reset(self, operation: str = None):
        """重置统计"""
        if operation:
            if operation in self.metrics:
                del self.metrics[operation]
        else:
            self.metrics.clear()
            self._start_times.clear()
    
    def save_report(self, filepath: str):
        """保存性能报告"""
        report = {
            "name": self.name,
            "timestamp": datetime.now().isoformat(),
            "stats": self.get_stats()
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Performance report saved to {filepath}")


def time_it(func):
    """函数计时装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        
        elapsed = end_time - start_time
        logger.info(f"Function {func.__name__} took {elapsed:.4f} seconds")
        
        return result
    return wrapper


@contextmanager
def timer_context(name: str = "operation"):
    """计时上下文管理器"""
    start_time = time.time()
    start_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
    
    try:
        yield
    finally:
        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        
        elapsed = end_time - start_time
        memory_used = end_memory - start_memory
        
        logger.info(f"{name} took {elapsed:.4f} seconds, memory used: {memory_used:.2f} MB")


def get_system_stats() -> Dict[str, Any]:
    """获取系统统计信息"""
    try:
        import psutil
        
        process = psutil.Process()
        system_info = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "percent": psutil.cpu_percent(interval=1),
                "count": psutil.cpu_count(),
                "freq": psutil.cpu_freq().current if hasattr(psutil.cpu_freq(), 'current') else None
            },
            "memory": {
                "total": psutil.virtual_memory().total / 1024 / 1024 / 1024,  # GB
                "available": psutil.virtual_memory().available / 1024 / 1024 / 1024,  # GB
                "percent": psutil.virtual_memory().percent,
                "used": psutil.virtual_memory().used / 1024 / 1024 / 1024  # GB
            },
            "process": {
                "memory_rss": process.memory_info().rss / 1024 / 1024,  # MB
                "memory_percent": process.memory_percent(),
                "cpu_percent": process.cpu_percent(interval=0.1),
                "threads": process.num_threads()
            }
        }
        
        return system_info
        
    except ImportError:
        warnings.warn("psutil is not installed. Cannot get system stats.")
        return {}
    except Exception as e:
        logger.warning(f"Failed to get system stats: {e}")
        return {}


class QueryBenchmark:
    """查询基准测试"""
    
    def __init__(self, connection_func: Callable):
        """
        初始化基准测试
        
        Args:
            connection_func: 返回 DuckDB 连接的函数
        """
        self.connection_func = connection_func
        self.results = {}
    
    def benchmark_query(
        self,
        query_name: str,
        sql: str,
        params: tuple = None,
        iterations: int = 5,
        warmup: int = 2
    ) -> Dict[str, Any]:
        """基准测试单个查询"""
        from ..utils.duckdb_utils import execute_query_with_stats
        
        logger.info(f"Benchmarking query: {query_name}")
        
        # 预热
        for i in range(warmup):
            with self.connection_func() as conn:
                execute_query_with_stats(conn, sql, params)
        
        # 正式测试
        times = []
        row_counts = []
        
        for i in range(iterations):
            gc.collect()  # 清理内存
            
            with self.connection_func() as conn:
                result = execute_query_with_stats(conn, sql, params)
                
                if result["stats"]["success"]:
                    times.append(result["stats"]["execution_time_ms"])
                    row_counts.append(result["stats"]["row_count"])
                else:
                    logger.error(f"Query failed: {result['stats'].get('error')}")
                    break
        
        if not times:
            return {"error": "All iterations failed"}
        
        # 计算统计
        stats = {
            "query_name": query_name,
            "sql": sql,
            "iterations": len(times),
            "times_ms": times,
            "row_counts": row_counts,
            "avg_time_ms": sum(times) / len(times),
            "min_time_ms": min(times),
            "max_time_ms": max(times),
            "std_time_ms": np.std(times) if len(times) > 1 else 0,
            "avg_rows": sum(row_counts) / len(row_counts) if row_counts else 0,
            "rows_per_ms": (sum(row_counts) / len(row_counts)) / (sum(times) / len(times)) 
                          if times and row_counts else 0
        }
        
        self.results[query_name] = stats
        return stats
    
    def benchmark_queries(
        self,
        queries: Dict[str, Dict[str, Any]],
        iterations: int = 5,
        warmup: int = 2
    ) -> Dict[str, Dict[str, Any]]:
        """基准测试多个查询"""
        results = {}
        
        for query_name, query_info in queries.items():
            sql = query_info["sql"]
            params = query_info.get("params")
            
            result = self.benchmark_query(
                query_name=query_name,
                sql=sql,
                params=params,
                iterations=iterations,
                warmup=warmup
            )
            
            results[query_name] = result
        
        return results
    
    def compare_with_qlib(
        self,
        qlib_times: Dict[str, List[float]],
        output_file: str = None
    ) -> pd.DataFrame:
        """与 Qlib 性能对比"""
        comparison_data = []
        
        for query_name, duckdb_stats in self.results.items():
            if query_name in qlib_times:
                qlib_times_list = qlib_times[query_name]
                
                comparison = {
                    "query": query_name,
                    "duckdb_avg_ms": duckdb_stats["avg_time_ms"],
                    "duckdb_min_ms": duckdb_stats["min_time_ms"],
                    "duckdb_max_ms": duckdb_stats["max_time_ms"],
                    "qlib_avg_ms": sum(qlib_times_list) / len(qlib_times_list),
                    "qlib_min_ms": min(qlib_times_list),
                    "qlib_max_ms": max(qlib_times_list),
                    "speedup": (sum(qlib_times_list) / len(qlib_times_list)) / duckdb_stats["avg_time_ms"]
                               if duckdb_stats["avg_time_ms"] > 0 else float('inf')
                }
                
                comparison_data.append(comparison)
        
        df = pd.DataFrame(comparison_data)
        
        if output_file:
            df.to_csv(output_file, index=False)
            logger.info(f"Comparison results saved to {output_file}")
        
        return df
    
    def save_results(self, filepath: str):
        """保存基准测试结果"""
        report = {
            "timestamp": datetime.now().isoformat(),
            "system": get_system_stats(),
            "results": self.results
        }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str, ensure_ascii=False)
        
        logger.info(f"Benchmark results saved to {filepath}")


def profile_memory(func):
    """内存分析装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        import tracemalloc
        
        # 开始内存跟踪
        tracemalloc.start()
        
        # 记录开始状态
        snapshot1 = tracemalloc.take_snapshot()
        
        # 执行函数
        result = func(*args, **kwargs)
        
        # 记录结束状态
        snapshot2 = tracemalloc.take_snapshot()
        
        # 停止跟踪
        tracemalloc.stop()
        
        # 分析内存使用
        top_stats = snapshot2.compare_to(snapshot1, 'lineno')
        
        logger.info(f"Memory profiling for {func.__name__}:")
        for stat in top_stats[:10]:  # 显示前10个
            logger.info(stat)
        
        return result
    return wrapper


def analyze_query_performance(
    conn,
    table_name: str,
    sample_queries: List[str] = None
) -> Dict[str, Any]:
    """分析查询性能"""
    if sample_queries is None:
        # 默认样本查询
        sample_queries = [
            f"SELECT COUNT(*) FROM {table_name}",
            f"SELECT symbol, COUNT(*) FROM {table_name} GROUP BY symbol",
            f"SELECT * FROM {table_name} WHERE symbol = 'SH600000' ORDER BY datetime LIMIT 100",
            f"SELECT symbol, AVG(close) FROM {table_name} GROUP BY symbol",
            f"SELECT * FROM {table_name} WHERE datetime >= '2023-01-01' AND datetime <= '2023-12-31'"
        ]
    
    from ..utils.duckdb_utils import execute_query_with_stats
    
    results = {}
    
    for i, query in enumerate(sample_queries):
        query_name = f"query_{i+1}"
        
        result = execute_query_with_stats(
            conn=conn,
            sql=query,
            explain=True
        )
        
        results[query_name] = {
            "query": query,
            "stats": result["stats"],
            "row_count": len(result["result"]) if result["result"] else 0
        }
    
    return results


def generate_performance_report(
    reg: str,
    output_dir: str = "./reports"
) -> str:
    """生成性能报告"""
    os.makedirs(output_dir, exist_ok=True)
    
    from ..duckdb_connection import get_connection
    from ..utils.duckdb_utils import get_database_size, analyze_table
    from ..constants import FEATURE_TABLE_PREFIX, SUPPORTED_FREQS
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(output_dir, f"performance_report_{reg}_{timestamp}.json")
    
    report = {
        "timestamp": datetime.now().isoformat(),
        "region": reg,
        "system": get_system_stats(),
        "database": {},
        "tables": {},
        "queries": {}
    }
    
    try:
        with get_connection(reg, read_only=False) as conn:
            # 数据库大小
            db_size = get_database_size(conn)
            report["database"]["size"] = db_size
            
            # 表分析
            for freq in SUPPORTED_FREQS[:5]:  # 只分析前5个频率
                table_name = f"{FEATURE_TABLE_PREFIX}{freq}"
                try:
                    table_stats = analyze_table(conn, table_name)
                    if "error" not in table_stats:
                        report["tables"][table_name] = table_stats
                except:
                    pass
            
            # 查询性能
            if report["tables"]:
                first_table = list(report["tables"].keys())[0]
                query_results = analyze_query_performance(conn, first_table)
                report["queries"] = query_results
        
        # 保存报告
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, default=str, ensure_ascii=False)
        
        logger.info(f"Performance report generated: {report_file}")
        return report_file
        
    except Exception as e:
        logger.error(f"Failed to generate performance report: {e}")
        return str(e)