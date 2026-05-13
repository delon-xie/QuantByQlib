"""
DuckDB 特定工具函数
"""
import duckdb
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional, Tuple, Union
import json
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


def optimize_duckdb_connection(conn: duckdb.DuckDBPyConnection, config: Dict[str, Any] = None):
    """优化 DuckDB 连接配置"""
    if config is None:
        config = {
            "memory_limit": "16GB",
            "threads": 4,
            "enable_progress_bar": True,
            "preserve_insertion_order": False
        }
    
    try:
        # 设置内存限制
        if "memory_limit" in config:
            conn.execute(f"SET memory_limit='{config['memory_limit']}'")
        
        # 设置线程数
        if "threads" in config:
            conn.execute(f"SET threads={config['threads']}")
        
        # 启用进度条
        if config.get("enable_progress_bar", False):
            conn.execute("SET enable_progress_bar=true")
        
        # 不保持插入顺序（提高性能）
        if not config.get("preserve_insertion_order", True):
            conn.execute("SET preserve_insertion_order=false")
        
        # 启用性能优化
        conn.execute("PRAGMA enable_verification")
        conn.execute("PRAGMA enable_object_cache")
        
        logger.info(f"Optimized DuckDB connection with config: {config}")
        
    except Exception as e:
        logger.warning(f"Failed to optimize DuckDB connection: {e}")


def create_duckdb_index(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    column: str,
    index_name: str = None,
    unique: bool = False
) -> bool:
    """在 DuckDB 表上创建索引"""
    if index_name is None:
        index_name = f"idx_{table_name}_{column}"
    
    try:
        unique_str = "UNIQUE" if unique else ""
        
        # DuckDB 使用 CREATE INDEX 语法
        sql = f"CREATE {unique_str} INDEX IF NOT EXISTS {index_name} ON {table_name}({column})"
        conn.execute(sql)
        
        logger.info(f"Created index {index_name} on {table_name}({column})")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create index on {table_name}({column}): {e}")
        return False


def analyze_table(
    conn: duckdb.DuckDBPyConnection,
    table_name: str
) -> Dict[str, Any]:
    """分析表统计信息"""
    try:
        # 获取表信息
        table_info = conn.execute(f"""
            SELECT * 
            FROM duckdb_tables() 
            WHERE table_name = '{table_name}'
        """).fetchall()
        
        if not table_info:
            return {"error": f"Table {table_name} not found"}
        
        # 获取列信息
        columns_info = conn.execute(f"""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = '{table_name}'
            ORDER BY ordinal_position
        """).fetchall()
        
        # 获取行数
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
        
        # 获取数据范围（如果表有时序数据）
        stats = {"row_count": row_count, "columns": []}
        
        for col_name, data_type in columns_info:
            col_stats = {"name": col_name, "type": data_type}
            
            # 根据数据类型获取统计
            if data_type in ["DOUBLE", "FLOAT", "DECIMAL", "INTEGER", "BIGINT"]:
                # 数值型统计
                try:
                    num_stats = conn.execute(f"""
                        SELECT 
                            MIN({col_name}) as min_val,
                            MAX({col_name}) as max_val,
                            AVG({col_name}) as avg_val,
                            COUNT(DISTINCT {col_name}) as distinct_count
                        FROM {table_name}
                        WHERE {col_name} IS NOT NULL
                    """).fetchone()
                    
                    if num_stats:
                        col_stats.update({
                            "min": num_stats[0],
                            "max": num_stats[1],
                            "avg": num_stats[2],
                            "distinct_count": num_stats[3]
                        })
                except:
                    pass
            
            elif data_type in ["VARCHAR", "TEXT"]:
                # 字符串统计
                try:
                    str_stats = conn.execute(f"""
                        SELECT 
                            MIN(LENGTH({col_name})) as min_len,
                            MAX(LENGTH({col_name})) as max_len,
                            COUNT(DISTINCT {col_name}) as distinct_count
                        FROM {table_name}
                        WHERE {col_name} IS NOT NULL
                    """).fetchone()
                    
                    if str_stats:
                        col_stats.update({
                            "min_length": str_stats[0],
                            "max_length": str_stats[1],
                            "distinct_count": str_stats[2]
                        })
                except:
                    pass
            
            elif data_type in ["TIMESTAMP", "DATE"]:
                # 时间型统计
                try:
                    time_stats = conn.execute(f"""
                        SELECT 
                            MIN({col_name}) as min_date,
                            MAX({col_name}) as max_date
                        FROM {table_name}
                        WHERE {col_name} IS NOT NULL
                    """).fetchone()
                    
                    if time_stats:
                        col_stats.update({
                            "min_date": time_stats[0],
                            "max_date": time_stats[1]
                        })
                except:
                    pass
            
            stats["columns"].append(col_stats)
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to analyze table {table_name}: {e}")
        return {"error": str(e)}


def export_table_to_parquet(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    output_path: str,
    partitions: List[str] = None
) -> bool:
    """导出表到 Parquet 文件"""
    try:
        if partitions:
            # 分区导出
            partition_clause = f"PARTITION BY {', '.join(partitions)}"
            sql = f"""
                COPY (SELECT * FROM {table_name}) 
                TO '{output_path}' 
                (FORMAT PARQUET, {partition_clause})
            """
        else:
            # 普通导出
            sql = f"COPY {table_name} TO '{output_path}' (FORMAT PARQUET)"
        
        conn.execute(sql)
        
        logger.info(f"Exported table {table_name} to {output_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to export table {table_name} to {output_path}: {e}")
        return False


def import_from_parquet(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    parquet_path: str,
    if_exists: str = "replace"
) -> bool:
    """从 Parquet 文件导入数据"""
    try:
        # 检查表是否存在
        table_exists = conn.execute(f"""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = '{table_name}'
        """).fetchone()[0] > 0
        
        if table_exists:
            if if_exists == "replace":
                conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            elif if_exists == "append":
                pass  # 直接追加
            elif if_exists == "fail":
                raise ValueError(f"Table {table_name} already exists")
        
        # 创建表
        sql = f"CREATE TABLE {table_name} AS SELECT * FROM read_parquet('{parquet_path}')"
        conn.execute(sql)
        
        logger.info(f"Imported data from {parquet_path} to table {table_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to import from {parquet_path} to {table_name}: {e}")
        return False


def execute_query_with_stats(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    params: tuple = None,
    explain: bool = False
) -> Dict[str, Any]:
    """执行查询并返回统计信息"""
    import time
    
    start_time = time.time()
    
    try:
        # 解释查询计划
        if explain:
            explain_result = conn.execute(f"EXPLAIN {sql}", params).fetchall()
            explain_text = "\n".join([str(row) for row in explain_result])
        else:
            explain_text = None
        
        # 执行查询
        if params:
            result = conn.execute(sql, params).fetchall()
        else:
            result = conn.execute(sql).fetchall()
        
        execution_time = time.time() - start_time
        
        # 获取查询统计
        stats = {
            "execution_time_ms": execution_time * 1000,
            "row_count": len(result),
            "success": True,
            "explain": explain_text
        }
        
        return {"result": result, "stats": stats}
        
    except Exception as e:
        execution_time = time.time() - start_time
        return {
            "result": None,
            "stats": {
                "execution_time_ms": execution_time * 1000,
                "error": str(e),
                "success": False
            }
        }


def vacuum_database(conn: duckdb.DuckDBPyConnection) -> bool:
    """优化数据库（VACUUM 和 ANALYZE）"""
    try:
        # 执行 VACUUM
        conn.execute("VACUUM")
        logger.info("Executed VACUUM")
        
        # 执行 ANALYZE
        conn.execute("ANALYZE")
        logger.info("Executed ANALYZE")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to vacuum database: {e}")
        return False


def get_database_size(conn: duckdb.DuckDBPyConnection) -> Dict[str, Any]:
    """获取数据库大小信息"""
    try:
        # 获取所有表的大小
        tables_size = conn.execute("""
            SELECT 
                table_name,
                estimated_size
            FROM duckdb_tables()
            ORDER BY estimated_size DESC
        """).fetchall()
        
        total_size = sum(size for _, size in tables_size if size)
        
        # 获取内存使用
        memory_info = conn.execute("PRAGMA memory").fetchall()
        memory_usage = {}
        for row in memory_info:
            if len(row) >= 2:
                memory_usage[row[0]] = row[1]
        
        return {
            "total_size_bytes": total_size,
            "total_size_human": _format_size(total_size),
            "tables": [
                {"table_name": name, "size_bytes": size, "size_human": _format_size(size)}
                for name, size in tables_size
            ],
            "memory_usage": memory_usage
        }
        
    except Exception as e:
        logger.error(f"Failed to get database size: {e}")
        return {"error": str(e)}


def _format_size(size_bytes: int) -> str:
    """格式化字节大小"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def create_materialized_view(
    conn: duckdb.DuckDBPyConnection,
    view_name: str,
    query: str,
    refresh: bool = False
) -> bool:
    """创建物化视图"""
    try:
        if refresh:
            # 删除已存在的视图
            conn.execute(f"DROP VIEW IF EXISTS {view_name}")
        
        # 创建物化视图
        sql = f"CREATE VIEW {view_name} AS {query}"
        conn.execute(sql)
        
        logger.info(f"Created materialized view: {view_name}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to create materialized view {view_name}: {e}")
        return False


def bulk_insert_dataframe(
    conn: duckdb.DuckDBPyConnection,
    table_name: str,
    df: pd.DataFrame,
    if_exists: str = "append",
    batch_size: int = 10000
) -> int:
    """批量插入 DataFrame 到 DuckDB"""
    if df.empty:
        return 0
    
    try:
        # 检查表是否存在
        table_exists = conn.execute(f"""
            SELECT COUNT(*) 
            FROM information_schema.tables 
            WHERE table_name = '{table_name}'
        """).fetchone()[0] > 0
        
        if not table_exists:
            # 创建表
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df LIMIT 0")
            logger.info(f"Created table {table_name}")
        
        elif if_exists == "replace":
            # 替换表
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df LIMIT 0")
            logger.info(f"Replaced table {table_name}")
        
        # 分批插入
        total_rows = len(df)
        inserted_rows = 0
        
        for i in range(0, total_rows, batch_size):
            batch = df.iloc[i:i + batch_size]
            
            # 使用 INSERT INTO
            placeholders = ", ".join(["?"] * len(batch.columns))
            columns = ", ".join(batch.columns)
            
            # 准备数据
            records = batch.replace({np.nan: None}).to_records(index=False)
            
            # 构建 SQL
            sql = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
            
            # 执行批量插入
            conn.executemany(sql, records)
            
            inserted_rows += len(batch)
            logger.debug(f"Inserted batch {i//batch_size + 1}: {len(batch)} rows")
        
        logger.info(f"Bulk insert completed: {inserted_rows} rows inserted into {table_name}")
        return inserted_rows
        
    except Exception as e:
        logger.error(f"Failed to bulk insert into {table_name}: {e}")
        raise