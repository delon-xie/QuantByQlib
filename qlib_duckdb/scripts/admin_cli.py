"""
管理命令行工具
"""
import argparse
import sys
import json
import pandas as pd
from pathlib import Path
from typing import Optional, List, Dict, Any
from tabulate import tabulate

from ..duckdb_connection import get_connection, DuckDBConnection
from ..schema import SchemaManager
from ..utils.validation import get_table_stats
from ..constants import SUPPORTED_FREQS, FEATURE_TABLE_PREFIX, CALENDAR_TABLE_PREFIX
from ..config import config
from ..managers.index_manager import IndexManager
from ..managers.calendar_manager import CalendarManager
from ..utils.logging_setup import setup_logging
import logging

logger = logging.getLogger(__name__)


def _format_size(size_bytes: int) -> str:
    """格式化字节大小为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


def check_status(args):
    """检查系统状态"""
    reg = args.reg
    
    print(f"📊 DuckDB 数据库状态检查 (区域: {reg})")
    print("=" * 80)
    
    try:
        with get_connection(reg, read_only=False) as conn:
            # 检查数据库信息
            db_info = conn.execute("SELECT * FROM duckdb_settings() WHERE name = 'database'")
            if db_info:
                db_path = db_info[0][1]
                print(f"📁 数据库路径: {db_path}")
                
                # 检查文件大小
                if Path(db_path).exists():
                    size = Path(db_path).stat().st_size
                    print(f"📦 文件大小: {_format_size(size)}")
            
            # 获取内存设置
            memory_info = conn.execute("PRAGMA memory_limit")
            if memory_info:
                print(f"💾 内存限制: {memory_info[0][0]}")
            
            # 获取线程数
            threads_info = conn.execute("PRAGMA threads")
            if threads_info:
                print(f"⚙️  线程数: {threads_info[0][0]}")
            
            print()
            
            # 获取所有表
            print("🗂️  数据库表概览:")
            print("-" * 80)
            
            tables = conn.execute("""
                SELECT table_name, column_count, estimated_size 
                FROM duckdb_tables() 
                WHERE table_schema = 'main'
                ORDER BY table_name
            """)
            
            if tables:
                table_data = []
                total_size = 0
                
                for table_name, columns, size in tables:
                    size_str = _format_size(size) if size else "N/A"
                    table_data.append([table_name, columns, size_str])
                    if size:
                        total_size += size
                
                print(tabulate(table_data, 
                             headers=["表名", "列数", "估算大小"], 
                             tablefmt="grid"))
                print(f"📈 总大小: {_format_size(total_size)}")
            else:
                print("❌ 数据库中没有表")
            
            print()
            
            # 获取特征表统计
            print("📈 特征表详细统计:")
            print("-" * 80)
            
            feature_tables = [t for t in tables if t[0].startswith(FEATURE_TABLE_PREFIX)] if tables else []
            
            if feature_tables:
                stats_data = []
                for table_name, _, _ in feature_tables:
                    try:
                        stats = get_table_stats(reg, table_name)
                        freq = table_name.replace(FEATURE_TABLE_PREFIX, "")
                        
                        stats_data.append([
                            freq,
                            f"{stats['row_count']:,}",
                            f"{stats['symbol_count']:,}",
                            str(stats['min_time'])[:19] if stats['min_time'] else "N/A",
                            str(stats['max_time'])[:19] if stats['max_time'] else "N/A"
                        ])
                    except Exception as e:
                        logger.warning(f"Failed to get stats for {table_name}: {e}")
                
                if stats_data:
                    print(tabulate(stats_data, 
                                 headers=["频率", "行数", "标的数", "最早时间", "最晚时间"], 
                                 tablefmt="grid"))
                else:
                    print("⏳ 特征表中暂无数据")
            else:
                print("⏳ 尚未创建特征表")
            
            print()
            
            # 检查日历表
            print("📅 日历表状态:")
            print("-" * 80)
            
            calendar_manager = CalendarManager(reg)
            calendar_stats = []
            
            for freq in ["day", "1h", "5m"]:  # 检查主要频率
                try:
                    stats = calendar_manager.get_calendar_stats(freq)
                    calendar_stats.append([
                        freq,
                        stats["history"]["count"],
                        stats["history"]["min_date"],
                        stats["history"]["max_date"],
                        stats["future"]["count"],
                        stats["future"]["min_date"] if stats["future"]["min_date"] else "N/A",
                        stats["future"]["max_date"] if stats["future"]["max_date"] else "N/A"
                    ])
                except Exception as e:
                    # 表可能不存在
                    calendar_stats.append([freq, 0, "N/A", "N/A", 0, "N/A", "N/A"])
            
            if calendar_stats:
                print(tabulate(calendar_stats, 
                             headers=["频率", "历史日期数", "最早", "最晚", "未来日期数", "最早", "最晚"], 
                             tablefmt="grid"))
            
            print()
            
            # 检查指数
            print("📊 指数信息:")
            print("-" * 80)
            
            index_manager = IndexManager(reg)
            indexes = index_manager.get_all_indexes()
            
            if not indexes.empty:
                index_data = []
                for _, row in indexes.iterrows():
                    members = index_manager.get_index_members(row["index_name"])
                    index_data.append([
                        row["index_name"],
                        row["index_type"],
                        len(members),
                        row["description"][:50] + "..." if len(row["description"]) > 50 else row["description"]
                    ])
                
                print(tabulate(index_data, 
                             headers=["指数名", "类型", "成分股数", "描述"], 
                             tablefmt="grid"))
            else:
                print("📝 尚未导入指数")
            
            print()
            
            # 检查连接状态
            print("🔗 连接状态:")
            print("-" * 80)
            print("✅ 数据库连接正常")
            
    except Exception as e:
        print(f"❌ 状态检查失败: {e}")
        sys.exit(1)


def create_tables(args):
    """创建表"""
    reg = args.reg
    
    print(f"🗃️  正在为区域 {reg} 创建表...")
    print("-" * 80)
    
    try:
        schema_manager = SchemaManager()
        
        if args.table_type == "all":
            # 创建所有表
            schema_manager.create_all_tables(reg)
            print("✅ 已创建所有表")
            
        elif args.table_type == "feature":
            # 创建特征表
            if args.freq:
                for freq in args.freq:
                    if freq not in SUPPORTED_FREQS:
                        print(f"⚠️  不支持的频率: {freq}，跳过")
                        continue
                    
                    schema_manager.create_feature_table(reg, freq)
                    print(f"✅ 已创建特征表: feature_{freq}")
            else:
                # 创建所有频率的特征表
                for freq in SUPPORTED_FREQS:
                    schema_manager.create_feature_table(reg, freq)
                print(f"✅ 已创建所有 {len(SUPPORTED_FREQS)} 个特征表")
        
        elif args.table_type == "calendar":
            # 创建日历表
            if args.freq:
                for freq in args.freq:
                    if freq not in SUPPORTED_FREQS:
                        print(f"⚠️  不支持的频率: {freq}，跳过")
                        continue
                    
                    schema_manager.create_calendar_table(reg, freq, future=False)
                    schema_manager.create_calendar_table(reg, freq, future=True)
                    print(f"✅ 已创建日历表: calendar_{freq} 和 calendar_{freq}_future")
            else:
                # 创建所有频率的日历表
                for freq in SUPPORTED_FREQS:
                    schema_manager.create_calendar_table(reg, freq, future=False)
                    schema_manager.create_calendar_table(reg, freq, future=True)
                print(f"✅ 已创建所有日历表")
        
        elif args.table_type == "instrument":
            # 创建标的表
            schema_manager.create_instrument_table(reg)
            print("✅ 已创建标的表")
        
        elif args.table_type == "index":
            # 创建指数表
            schema_manager.create_index_tables(reg)
            print("✅ 已创建指数表")
        
        print("🎉 表创建完成")
        
    except Exception as e:
        print(f"❌ 创建表失败: {e}")
        sys.exit(1)


def list_tables(args):
    """列出所有表"""
    reg = args.reg
    
    print(f"📋 区域 {reg} 的表列表:")
    print("-" * 80)
    
    try:
        with get_connection(reg, read_only=False) as conn:
            tables = conn.execute("""
                SELECT 
                    table_name,
                    column_count,
                    estimated_size,
                    temporary
                FROM duckdb_tables() 
                WHERE table_schema = 'main'
                ORDER BY table_name
            """)
            
            if tables:
                table_data = []
                for table_name, columns, size, temp in tables:
                    size_str = _format_size(size) if size else "N/A"
                    temp_str = "是" if temp else "否"
                    table_data.append([table_name, columns, size_str, temp_str])
                
                print(tabulate(table_data, 
                             headers=["表名", "列数", "大小", "临时表"], 
                             tablefmt="grid"))
                print(f"总计: {len(table_data)} 张表")
            else:
                print("📭 数据库中没有表")
                
    except Exception as e:
        print(f"❌ 列出表失败: {e}")
        sys.exit(1)


def table_info(args):
    """获取表详细信息"""
    reg = args.reg
    table_name = args.table_name
    
    print(f"📄 表详细信息: {table_name}")
    print("-" * 80)
    
    try:
        with get_connection(reg, read_only=False) as conn:
            # 获取表结构
            columns = conn.execute(f"""
                SELECT 
                    column_name,
                    data_type,
                    is_nullable
                FROM information_schema.columns
                WHERE table_name = ?
                ORDER BY ordinal_position
            """, (table_name,))
            
            if columns:
                print("📊 表结构:")
                column_data = []
                for col_name, data_type, nullable in columns:
                    nullable_str = "是" if nullable == "YES" else "否"
                    column_data.append([col_name, data_type, nullable_str])
                
                print(tabulate(column_data, 
                             headers=["列名", "数据类型", "允许为空"], 
                             tablefmt="grid"))
                print()
            else:
                print(f"⚠️  表 {table_name} 不存在或没有列")
                return
            
            # 获取表统计
            try:
                stats = get_table_stats(reg, table_name)
                print("📈 表统计:")
                stats_data = [
                    ["行数", f"{stats['row_count']:,}"],
                    ["标的数", stats['symbol_count']],
                    ["最早时间", stats['min_time']],
                    ["最晚时间", stats['max_time']]
                ]
                print(tabulate(stats_data, headers=["指标", "值"], tablefmt="grid"))
                print()
            except:
                pass
            
            # 获取示例数据
            if args.sample:
                print("🔍 示例数据 (前5行):")
                sample = conn.execute(f"SELECT * FROM {table_name} LIMIT 5")
                
                if sample:
                    # 获取列名
                    col_names_result = conn.execute(f"DESCRIBE {table_name}")
                    if col_names_result:
                        col_names = [row[0] for row in col_names_result]
                        sample_data = []
                        for row in sample:
                            sample_data.append(list(row))
                        
                        print(tabulate(sample_data, headers=col_names, tablefmt="grid"))
                else:
                    print("📭 表中没有数据")
            
    except Exception as e:
        print(f"❌ 获取表信息失败: {e}")
        sys.exit(1)


def execute_sql(args):
    """执行 SQL 语句"""
    reg = args.reg
    sql = args.sql
    
    print(f"⚡ 执行 SQL: {sql[:100]}..." if len(sql) > 100 else f"⚡ 执行 SQL: {sql}")
    print("-" * 80)
    
    try:
        with get_connection(reg, read_only=False) as conn:
            result = conn.execute(sql)
            
            if result is not None:
                if result:
                    # 显示结果
                    print("✅ 执行结果:")
                    
                    # 尝试获取列名
                    try:
                        # 使用 DESCRIBE 获取结果格式
                        temp_result = conn.execute(f"DESCRIBE ({sql})")
                        if temp_result:
                            col_names = [row[0] for row in temp_result]
                        else:
                            col_names = [f"col{i}" for i in range(len(result[0]))]
                    except:
                        col_names = [f"col{i}" for i in range(len(result[0]))]
                    
                    # 显示数据
                    data = []
                    for row in result[:args.limit]:  # 限制显示行数
                        data.append(list(row))
                    
                    print(tabulate(data, headers=col_names, tablefmt="grid"))
                    print(f"显示 {len(data)} 行 (共 {len(result)} 行)")
                else:
                    print("✅ 执行成功，无返回数据")
            else:
                print("✅ SQL 执行完成")
                
    except Exception as e:
        print(f"❌ SQL 执行失败: {e}")
        sys.exit(1)


def clear_cache(args):
    """清除缓存"""
    reg = args.reg
    
    print(f"🧹 正在清除区域 {reg} 的缓存...")
    print("-" * 80)
    
    try:
        # 关闭所有连接
        DuckDBConnection.close_all()
        
        # 清除文件系统缓存
        import shutil
        import tempfile
        
        # DuckDB 可能会在临时目录中缓存数据
        temp_dir = tempfile.gettempdir()
        duckdb_temp_files = list(Path(temp_dir).glob("*.tmp"))
        duckdb_temp_files.extend(list(Path(temp_dir).glob("duckdb_*")))
        
        cleared_count = 0
        for temp_file in duckdb_temp_files:
            try:
                if temp_file.is_file():
                    temp_file.unlink()
                    cleared_count += 1
            except:
                pass
        
        print(f"✅ 已清除 {cleared_count} 个临时文件")
        print("✅ 已关闭所有数据库连接")
        print("🔄 下次查询时会创建新的连接")
        
    except Exception as e:
        print(f"❌ 清除缓存失败: {e}")
        sys.exit(1)


def vacuum_db(args):
    """优化数据库"""
    reg = args.reg
    
    print(f"🧹 正在优化数据库 {reg}...")
    print("-" * 80)
    
    try:
        with get_connection(reg, read_only=False) as conn:
            # 执行 VACUUM
            print("正在执行 VACUUM...")
            conn.execute("VACUUM", fetch=False)
            
            # 执行 ANALYZE
            print("正在执行 ANALYZE...")
            conn.execute("ANALYZE", fetch=False)
            
            print("✅ 数据库优化完成")
            
    except Exception as e:
        print(f"❌ 数据库优化失败: {e}")
        sys.exit(1)


def export_schema(args):
    """导出表结构"""
    reg = args.reg
    output_file = args.output
    
    print(f"📤 正在导出区域 {reg} 的表结构...")
    print("-" * 80)
    
    try:
        with get_connection(reg, read_only=False) as conn:
            # 获取所有表
            tables = conn.execute("""
                SELECT table_name
                FROM duckdb_tables() 
                WHERE table_schema = 'main'
                ORDER BY table_name
            """)
            
            if not tables:
                print("📭 数据库中没有表")
                return
            
            schema_data = {}
            
            for table_row in tables:
                table_name = table_row[0]
                
                # 获取表结构
                columns = conn.execute(f"""
                    SELECT 
                        column_name,
                        data_type,
                        is_nullable
                    FROM information_schema.columns
                    WHERE table_name = ?
                    ORDER BY ordinal_position
                """, (table_name,))
                
                table_schema = []
                for col_name, data_type, nullable in columns:
                    table_schema.append({
                        "column_name": col_name,
                        "data_type": data_type,
                        "is_nullable": nullable
                    })
                
                schema_data[table_name] = table_schema
            
            # 导出到文件
            if output_file.endswith('.json'):
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(schema_data, f, indent=2, ensure_ascii=False)
                print(f"✅ 表结构已导出到 JSON 文件: {output_file}")
            else:
                # 导出为 SQL
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(f"-- DuckDB 表结构导出 (区域: {reg})\n")
                    f.write(f"-- 导出时间: {pd.Timestamp.now()}\n")
                    f.write("\n")
                    
                    for table_name, columns in schema_data.items():
                        f.write(f"-- 表: {table_name}\n")
                        f.write(f"CREATE TABLE IF NOT EXISTS {table_name} (\n")
                        
                        col_defs = []
                        for col in columns:
                            nullable = "NULL" if col["is_nullable"] == "YES" else "NOT NULL"
                            col_defs.append(f"    {col['column_name']} {col['data_type']} {nullable}")
                        
                        f.write(",\n".join(col_defs))
                        f.write("\n);\n\n")
                
                print(f"✅ 表结构已导出到 SQL 文件: {output_file}")
            
    except Exception as e:
        print(f"❌ 导出表结构失败: {e}")
        sys.exit(1)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="qlib-duckdb 管理命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 检查数据库状态
  python -m qlib_duckdb.scripts.admin_cli check-status --reg cn
  
  # 创建所有表
  python -m qlib_duckdb.scripts.admin_cli create-tables --reg cn --table-type all
  
  # 创建指定频率的特征表
  python -m qlib_duckdb.scripts.admin_cli create-tables --reg cn --table-type feature --freq day 5m 1h
  
  # 列出所有表
  python -m qlib_duckdb.scripts.admin_cli list-tables --reg cn
  
  # 获取表信息
  python -m qlib_duckdb.scripts.admin_cli table-info --reg cn --table-name feature_day
  
  # 执行 SQL
  python -m qlib_duckdb.scripts.admin_cli execute-sql --reg cn --sql "SELECT COUNT(*) FROM feature_day"
  
  # 清除缓存
  python -m qlib_duckdb.scripts.admin_cli clear-cache --reg cn
  
  # 优化数据库
  python -m qlib_duckdb.scripts.admin_cli vacuum-db --reg cn
  
  # 导出表结构
  python -m qlib_duckdb.scripts.admin_cli export-schema --reg cn --output schema.json
        """
    )
    
    parser.add_argument("--reg", type=str, default="cn", 
                       help="市场区域 (cn, us, hk 等)")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="显示详细日志")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # check-status 命令
    status_parser = subparsers.add_parser("check-status", help="检查系统状态")
    status_parser.set_defaults(func=check_status)
    
    # create-tables 命令
    create_parser = subparsers.add_parser("create-tables", help="创建表")
    create_parser.add_argument("--table-type", type=str, required=True,
                              choices=["all", "feature", "calendar", "instrument", "index"],
                              help="表类型")
    create_parser.add_argument("--freq", type=str, nargs="+",
                              help="频率列表 (仅用于 feature 和 calendar 类型)")
    create_parser.set_defaults(func=create_tables)
    
    # list-tables 命令
    list_parser = subparsers.add_parser("list-tables", help="列出所有表")
    list_parser.set_defaults(func=list_tables)
    
    # table-info 命令
    info_parser = subparsers.add_parser("table-info", help="获取表详细信息")
    info_parser.add_argument("--table-name", type=str, required=True,
                            help="表名")
    info_parser.add_argument("--sample", action="store_true",
                            help="显示示例数据")
    info_parser.set_defaults(func=table_info)
    
    # execute-sql 命令
    sql_parser = subparsers.add_parser("execute-sql", help="执行 SQL 语句")
    sql_parser.add_argument("--sql", type=str, required=True,
                           help="SQL 语句")
    sql_parser.add_argument("--limit", type=int, default=20,
                           help="显示结果行数限制")
    sql_parser.set_defaults(func=execute_sql)
    
    # clear-cache 命令
    cache_parser = subparsers.add_parser("clear-cache", help="清除缓存")
    cache_parser.set_defaults(func=clear_cache)
    
    # vacuum-db 命令
    vacuum_parser = subparsers.add_parser("vacuum-db", help="优化数据库")
    vacuum_parser.set_defaults(func=vacuum_db)
    
    # export-schema 命令
    export_parser = subparsers.add_parser("export-schema", help="导出表结构")
    export_parser.add_argument("--output", type=str, required=True,
                              help="输出文件路径 (支持 .json 或 .sql)")
    export_parser.set_defaults(func=export_schema)
    
    args = parser.parse_args()
    
    # 设置日志
    if args.verbose:
        setup_logging("DEBUG")
    else:
        setup_logging("INFO")
    
    if args.command is None:
        parser.print_help()
        sys.exit(1)
    
    try:
        args.func(args)
    except Exception as e:
        logger.error(f"命令执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()