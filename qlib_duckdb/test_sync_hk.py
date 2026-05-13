#!/usr/bin/env python3
"""
HK Qlib数据导入测试程序
同步HK市场的日历、标的和特征数据到DuckDB数据库
所有特征（open, close, low, high, volume, factor）存储在一个表中
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import argparse
import hashlib
import json

import duckdb
import pandas as pd
import numpy as np
import qlib
from qlib.data import D
from tqdm import tqdm

# ============================================================================
# 配置参数
# ============================================================================
QLIB_ROOT = Path.home() / ".qlib" / "qlib_data" / "hk_data"
DUCKDB_PATH = Path("hk_finance.duckdb")
LOG_DIR = Path("logs")

# 要同步的特征列表
FEATURES_TO_SYNC = ['open', 'close', 'low', 'high', 'volume']

# ============================================================================
# 导入验证器类
# ============================================================================
class ImportVerifier:
    """数据导入验证器，确保数据完整性和一致性"""
    
    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn
        self.verification_results = {}
        self._init_meta_tables()
    
    def _init_meta_tables(self):
        """初始化元数据表"""
        # 导入历史表
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS import_history (
            import_id INTEGER PRIMARY KEY,
            table_name VARCHAR NOT NULL,
            import_type VARCHAR NOT NULL,
            import_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            source_count INTEGER,
            target_count INTEGER,
            duration_seconds FLOAT,
            status VARCHAR,
            error_message TEXT
        )
        """)
        
        # 导入统计表
        self.conn.execute("""
        CREATE TABLE IF NOT EXISTS import_stats (
            stat_id INTEGER PRIMARY KEY,
            table_name VARCHAR NOT NULL,
            feature_name VARCHAR,
            row_count INTEGER,
            symbol_count INTEGER,
            date_range_start DATE,
            date_range_end DATE,
            update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    
    def start_import(self, table_name: str, import_type: str) -> int:
        """开始导入，返回导入ID"""
        # 获取当前最大ID
        result = self.conn.execute("""
            SELECT COALESCE(MAX(import_id), 0) FROM import_history
            """).fetchone()
    
        new_id = result[0] + 1
    
        result = self.conn.execute("""
        INSERT INTO import_history (import_id, table_name, import_type, status, import_time)
        VALUES (?, ?, ?, 'started', CURRENT_TIMESTAMP)
        RETURNING import_id
        """, [new_id, table_name, import_type])
        
        return result.fetchone()[0]
    
    def complete_import(self, import_id: int, source_count: int, target_count: int, 
                       duration: float, error: str = None):
        """完成导入，记录结果"""
        status = 'failed' if error else 'completed'
        error_msg = error if error else ''
        
        self.conn.execute("""
        UPDATE import_history 
        SET source_count = ?, target_count = ?, duration_seconds = ?,
            status = ?, error_message = ?
        WHERE import_id = ?
        """, [source_count, target_count, duration, status, error_msg, import_id])
    
    def update_stats(self, table_name: str, feature_name: str = None, 
                    row_count: int = None, symbol_count: int = None,
                    date_range_start: str = None, date_range_end: str = None):
        """更新导入统计"""
        # 获取当前最大ID
        result = self.conn.execute("""
        SELECT COALESCE(MAX(stat_id), 0) FROM import_stats
        """).fetchone()
        
        new_id = result[0] + 1
    
        self.conn.execute("""
        INSERT INTO import_stats (stat_id, table_name, feature_name, row_count, 
                                 symbol_count, date_range_start, date_range_end)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [new_id, table_name, feature_name, row_count, symbol_count, 
              date_range_start, date_range_end])
    
    def get_last_import(self, table_name: str) -> Optional[Dict]:
        """获取表的上次导入信息"""
        result = self.conn.execute("""
        SELECT * FROM import_history 
        WHERE table_name = ? AND status = 'completed'
        ORDER BY import_time DESC 
        LIMIT 1
        """, [table_name]).fetchone()
        
        if result:
            return {
                'import_id': result[0],
                'table_name': result[1],
                'import_type': result[2],
                'import_time': result[3],
                'source_count': result[4],
                'target_count': result[5],
                'duration': result[6],
                'status': result[7]
            }
        return None
    
    def generate_report(self) -> str:
        """生成导入报告"""
        result = self.conn.execute("""
        SELECT table_name, COUNT(*) as import_count, 
               MAX(import_time) as last_import,
               AVG(duration_seconds) as avg_duration
        FROM import_history
        WHERE status = 'completed'
        GROUP BY table_name
        ORDER BY last_import DESC
        """).fetchall()
        
        if not result:
            return "无导入记录"
        
        report_lines = ["=" * 80]
        report_lines.append("数据导入统计报告")
        report_lines.append("=" * 80)
        
        for row in result:
            table_name, import_count, last_import, avg_duration = row
            report_lines.append(f"\n表名: {table_name}")
            report_lines.append(f"  导入次数: {import_count}")
            report_lines.append(f"  最后导入: {last_import}")
            report_lines.append(f"  平均耗时: {avg_duration:.2f}秒")
        
        # 总体统计
        total_stats = self.conn.execute("""
        SELECT COUNT(DISTINCT table_name) as table_count,
               COUNT(*) as total_imports,
               SUM(duration_seconds) as total_time
        FROM import_history
        WHERE status = 'completed'
        """).fetchone()
        
        report_lines.append("\n" + "=" * 80)
        report_lines.append(f"总体统计:")
        report_lines.append(f"  表数量: {total_stats[0]}")
        report_lines.append(f"  总导入次数: {total_stats[1]}")
        report_lines.append(f"  总耗时: {total_stats[2]:.2f}秒")
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)

# ============================================================================
# 数据同步函数
# ============================================================================
def sync_calendars(conn: duckdb.DuckDBPyConnection, verifier: ImportVerifier) -> Dict[str, Any]:
    """同步日历数据"""
    print("📅 同步日历数据...")
    
    cal_dir = QLIB_ROOT / "calendars"
    if not cal_dir.exists():
        print(f"❌ 日历目录不存在: {cal_dir}")
        return {'success': False, 'error': f'日历目录不存在: {cal_dir}'}
    
    results = {}
    start_time = datetime.now()
    
    for cal_file in cal_dir.glob("*.txt"):
        freq = cal_file.stem
        if freq.endswith("_future"):
            continue
        
        try:
            # 开始导入
            import_id = verifier.start_import(f"calendar_{freq}", "calendar")
            
            # 读取日历文件
            df = pd.read_csv(cal_file, header=None, names=["datetime"])
            df_count = len(df)
            
            # 创建表
            table_name = f"calendar_{freq}"
            conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                datetime DATE PRIMARY KEY
            )
            """)
            
            # 清空表
            conn.execute(f"DELETE FROM {table_name}")
            
            # 插入数据
            temp_table = f"temp_cal_{freq}"
            conn.register(temp_table, df)
            conn.execute(f"""
            INSERT INTO {table_name}
            SELECT * FROM {temp_table}
            """)
            
            # 验证数据
            result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            
            # 完成导入
            duration = (datetime.now() - start_time).total_seconds()
            verifier.complete_import(import_id, df_count, result, duration)
            
            # 更新统计
            if result > 0:
                date_range = conn.execute(f"""
                SELECT MIN(datetime), MAX(datetime) FROM {table_name}
                """).fetchone()
                verifier.update_stats(
                    table_name=table_name,
                    row_count=result,
                    date_range_start=date_range[0],
                    date_range_end=date_range[1]
                )
            
            results[freq] = {
                'success': True,
                'source_count': df_count,
                'target_count': result,
                'duration': duration
            }
            
            print(f"  ✅ {freq}: {result} 个交易日")
            
        except Exception as e:
            print(f"  ❌ {freq}: 同步失败 - {e}")
            results[freq] = {'success': False, 'error': str(e)}
    
    return results

def sync_instruments(conn: duckdb.DuckDBPyConnection, verifier: ImportVerifier) -> Dict[str, Any]:
    """同步标的列表"""
    print("📈 同步标的列表...")
    
    inst_dir = QLIB_ROOT / "instruments"
    if not inst_dir.exists():
        print(f"❌ 标的目录不存在: {inst_dir}")
        return {'success': False, 'error': f'标的目录不存在: {inst_dir}'}
    
    start_time = datetime.now()
    all_symbols = set()
    index_results = {}
    
    # 开始导入
    import_id = verifier.start_import("instruments", "instruments")
    
    try:
        # 处理所有指数文件
        for index_file in inst_dir.glob("*.txt"):
            index_name = index_file.stem
            print(f"  处理指数: {index_name}")
            
            try:
                # 读取数据
                try:
                    df = pd.read_csv(
                        index_file,
                        sep="\t",
                        header=None,
                        names=["symbol", "start_date"]
                    )
                except pd.errors.ParserError:
                    df = pd.read_csv(
                        index_file,
                        sep="\t",
                        header=None,
                        usecols=[0],
                        names=["symbol"]
                    )
                    df["start_date"] = None
                
                df["end_date"] = None
                df["index_name"] = index_name
                
                # 添加到总集合
                for symbol in df["symbol"]:
                    all_symbols.add(symbol)
                
                # 创建临时表并插入
                temp_table = f"temp_idx_{index_name}"
                conn.register(temp_table, df[["index_name", "symbol", "start_date", "end_date"]])
                
                # 创建 index_member 表
                conn.execute("""
                CREATE TABLE IF NOT EXISTS index_member (
                    index_name VARCHAR,
                    symbol VARCHAR,
                    start_date DATE,
                    end_date DATE,
                    PRIMARY KEY (index_name, symbol)
                )
                """)
                
                # 使用 INSERT OR REPLACE
                conn.execute(f"""
                INSERT OR REPLACE INTO index_member
                SELECT * FROM {temp_table}
                """)
                
                index_results[index_name] = {
                    'success': True,
                    'symbol_count': len(df)
                }
                
                print(f"    ✅ {index_name}: {len(df)} 个标的")
                
            except Exception as e:
                print(f"    ❌ {index_name}: 处理失败 - {e}")
                index_results[index_name] = {'success': False, 'error': str(e)}
        
        # 创建 instrument 主表
        if all_symbols:
            data = []
            for symbol in all_symbols:
                data.append({
                    "symbol": symbol,
                    "start_date": None,
                    "end_date": None
                })
            
            df_instruments = pd.DataFrame(data)
            
            # 创建表
            conn.execute("""
            CREATE TABLE IF NOT EXISTS instrument (
                symbol VARCHAR PRIMARY KEY,
                start_date DATE,
                end_date DATE
            )
            """)
            
            # 插入数据
            conn.register("temp_instruments", df_instruments)
            conn.execute("""
            INSERT OR REPLACE INTO instrument
            SELECT * FROM temp_instruments
            """)
            
            instrument_count = len(df_instruments)
            print(f"  ✅ instrument 表: {instrument_count} 个唯一标的")
        
        # 获取统计
        instrument_count = conn.execute("SELECT COUNT(*) FROM instrument").fetchone()[0]
        index_member_count = conn.execute("SELECT COUNT(*) FROM index_member").fetchone()[0]
        
        # 完成导入
        duration = (datetime.now() - start_time).total_seconds()
        verifier.complete_import(import_id, len(all_symbols), instrument_count, duration)
        
        # 更新统计
        verifier.update_stats(
            table_name="instrument",
            row_count=instrument_count
        )
        verifier.update_stats(
            table_name="index_member",
            row_count=index_member_count
        )
        
        return {
            'success': True,
            'instruments': instrument_count,
            'index_members': index_member_count,
            'indices': len(index_results),
            'duration': duration
        }
        
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        verifier.complete_import(import_id, 0, 0, duration, str(e))
        return {'success': False, 'error': str(e)}

def sync_features_unified(conn: duckdb.DuckDBPyConnection, verifier: ImportVerifier, 
                          limit_symbols: int = None, features: List[str] = None) -> Dict[str, Any]:
    """同步特征数据到统一表（所有特征作为列）"""
    if features is None:
        features = FEATURES_TO_SYNC
    
    print(f"🎯 同步特征数据到统一表 ({', '.join(features)})...")
    
    # 获取标的列表
    symbols_result = conn.execute("SELECT symbol FROM instrument")
    if symbols_result is None:
        return {'success': False, 'error': '无法获取标的列表'}
    
    symbols = [row[0] for row in symbols_result.fetchall()]
    
    if limit_symbols and limit_symbols > 0:
        symbols = symbols[:limit_symbols]
        print(f"  测试模式: 只处理前 {limit_symbols} 个标的")
    else:
        print(f"  全量模式: 处理 {len(symbols)} 个标的")
    
    # 开始导入
    import_id = verifier.start_import("feature_day", "features")
    start_time = datetime.now()
    
    try:
        # 创建统一特征表
        table_name = "feature_day"
        
        # 构建CREATE TABLE语句
        columns_sql = ["symbol VARCHAR", "datetime DATE", "open DOUBLE", "high DOUBLE", "low DOUBLE", "close DOUBLE", "volume DOUBLE"]
        columns_sql.append("PRIMARY KEY (symbol, datetime)")
        
        create_table_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {', '.join(columns_sql)}
        )
        """
        
        conn.execute(create_table_sql)
        print(f"  ✅ 已创建/确认表: {table_name}")
        
        # 获取所有特征列名
        #qlib_features = [f"${feature}" for feature in features]
        
        total_rows = 0
        success_count = 0
        fail_count = 0
        
        # 使用进度条
        with tqdm(total=len(symbols), desc="同步进度", unit="股票", 
                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]") as pbar:
            
            for symbol in symbols:
                try:
                    # 获取该股票的所有特征数据
                    df = D.features(
                        [symbol],
                        ["$open", "$high", "$low", "$close", "$volume"],
                        freq="day"
                    ).reset_index()
                    #print(df.columns)
                    #['instrument', 'datetime', '$open', '$high', '$low', '$close', '$volume']
                    
                    if not df.empty:

                        # 插入数据
                        temp_table = f"temp_{symbol}".replace(".", "_")
                        conn.register(temp_table, df)
                        
                        insert_sql = f"""
                        INSERT OR REPLACE INTO {table_name} (symbol, datetime, open, high, low, close, volume)
                        SELECT "instrument" as symbol, "datetime" as datetime, "$open" as open, "$high" as high, "$low" as low, "$close" as close, "$volume" as volume
                        FROM {temp_table};
                        """
                        
                        conn.execute(insert_sql)
                        total_rows += len(df)
                        success_count += 1
                        pbar.set_postfix_str(f"{symbol}: {len(df)}行")
                        
                except Exception as e:
                    fail_count += 1
                    pbar.set_postfix_str(f"{symbol}: 错误")
                
                pbar.update(1)
        
        # 获取统计信息
        result = conn.execute(f"""
        SELECT 
            COUNT(*) as row_count, 
            COUNT(DISTINCT symbol) as symbol_count,
            MIN(datetime) as date_start,
            MAX(datetime) as date_end
        FROM {table_name}
        """).fetchone()
        
        row_count = result[0] if result[0] else 0
        symbol_count = result[1] if result[1] else 0
        date_start = result[2] if result[2] else None
        date_end = result[3] if result[3] else None
        
        # 获取各特征的非空值统计
        feature_stats = {}
        for feature in features:
            feature_result = conn.execute(f"""
            SELECT COUNT({feature}) as non_null_count
            FROM {table_name}
            """).fetchone()
            
            feature_stats[feature] = {
                'non_null_count': feature_result[0] if feature_result[0] else 0
            }
        
        # 完成导入
        duration = (datetime.now() - start_time).total_seconds()
        verifier.complete_import(import_id, success_count, row_count, duration)
        
        # 更新统计
        verifier.update_stats(
            table_name=table_name,
            row_count=row_count,
            symbol_count=symbol_count,
            date_range_start=date_start,
            date_range_end=date_end
        )
        
        # 打印统计
        print(f"\n📊 特征同步统计:")
        print(f"  成功处理: {success_count} 个标的")
        print(f"  失败处理: {fail_count} 个标的")
        print(f"  总数据行: {row_count} 行")
        print(f"  唯一标的: {symbol_count} 个")
        if date_start and date_end:
            print(f"  日期范围: {date_start} 到 {date_end}")
        
        print(f"\n  特征值统计:")
        for feature, stats in feature_stats.items():
            print(f"    {feature}: {stats['non_null_count']} 个非空值")
        
        return {
            'success': True,
            'total_rows': row_count,
            'success_count': success_count,
            'fail_count': fail_count,
            'feature_stats': feature_stats,
            'duration': duration
        }
        
    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        verifier.complete_import(import_id, 0, 0, duration, str(e))
        return {'success': False, 'error': str(e)}

def create_sample_queries(conn: duckdb.DuckDBPyConnection):
    """创建示例查询，验证数据可用性"""
    print("\n🔍 创建示例查询验证数据...")
    
    queries = [
        ("日历数据统计", "SELECT COUNT(*) as 交易日数 FROM calendar_day"),
        ("标的数量", "SELECT COUNT(*) as 标的数量 FROM instrument"),
        ("指数成员数量", "SELECT COUNT(*) as 指数成员数 FROM index_member"),
        ("指数分布", """
         SELECT index_name, COUNT(*) as 标的数 
         FROM index_member 
         GROUP BY index_name 
         ORDER BY 标的数 DESC
         """),
        ("特征表结构", """
         SELECT column_name, data_type 
         FROM information_schema.columns 
         WHERE table_name = 'feature_day'
         """),
        ("特征表数据统计", """
         SELECT 
             COUNT(*) as 总行数,
             COUNT(DISTINCT symbol) as 唯一标的,
             MIN(datetime) as 最早日期,
             MAX(datetime) as 最晚日期
         FROM feature_day
         """),
        ("特征值完整性", """
         SELECT 
             COUNT(open) as open非空,
             COUNT(close) as close非空,
             COUNT(high) as high非空,
             COUNT(low) as low非空,
             COUNT(volume) as volume非空
         FROM feature_day
         """),
        ("示例数据查看（前5行）", """
         SELECT * 
         FROM feature_day 
         ORDER BY symbol, datetime 
         LIMIT 5
         """),
        ("标的示例（前10个）", """
         SELECT DISTINCT symbol 
         FROM feature_day 
         ORDER BY symbol 
         LIMIT 10
         """),
        ("价格数据查询示例", """
         SELECT symbol, datetime, open, close, volume
         FROM feature_day
         WHERE symbol = 'HK_000001'
         ORDER BY datetime DESC
         LIMIT 10
         """)
    ]
    
    for title, query in queries:
        try:
            result = conn.execute(query).fetchall()
            print(f"\n{title}:")
            for row in result:
                print(f"  {row}")
        except Exception as e:
            print(f"\n{title}: 查询失败 - {e}")

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='HK Qlib数据同步工具')
    parser.add_argument('--test', action='store_true', help='测试模式（只同步前10个标的）')
    parser.add_argument('--symbols', type=int, default=None, help='限制同步的标的数量')
    parser.add_argument('--features', type=str, nargs='+', default=FEATURES_TO_SYNC,
                       help=f'要同步的特征列表，默认: {FEATURES_TO_SYNC}')
    parser.add_argument('--skip-calendars', action='store_true', help='跳过日历同步')
    parser.add_argument('--skip-instruments', action='store_true', help='跳过标的同步')
    parser.add_argument('--skip-features', action='store_true', help='跳过特征同步')
    parser.add_argument('--output', type=str, default=None, help='输出数据库文件路径')
    
    args = parser.parse_args()
    
    # 设置输出路径
    if args.output:
        db_path = Path(args.output)
    else:
        db_path = DUCKDB_PATH
    
    # 创建日志目录
    LOG_DIR.mkdir(exist_ok=True)
    
    print("=" * 80)
    print("🚀 HK Qlib数据同步系统")
    print("=" * 80)
    print(f"Qlib数据源: {QLIB_ROOT}")
    print(f"DuckDB文件: {db_path}")
    print(f"同步特征: {', '.join(args.features)}")
    print(f"特征表名: feature_day (统一表)")
    if args.test or args.symbols:
        limit_symbols = args.symbols or 10
        print(f"测试模式: 限制 {limit_symbols} 个标的")
    print("=" * 80)
    
    # 检查数据源
    if not QLIB_ROOT.exists():
        print(f"❌ 错误: Qlib数据目录不存在: {QLIB_ROOT}")
        sys.exit(1)
    
    # 初始化Qlib
    try:
        qlib.init(provider_uri=str(QLIB_ROOT))
        print("✅ Qlib初始化成功")
    except Exception as e:
        print(f"❌ Qlib初始化失败: {e}")
        sys.exit(1)
    
    # 连接DuckDB
    try:
        conn = duckdb.connect(str(db_path))
        print("✅ DuckDB连接成功")
    except Exception as e:
        print(f"❌ DuckDB连接失败: {e}")
        sys.exit(1)
    
    # 初始化验证器
    verifier = ImportVerifier(conn)
    
    # 记录开始时间
    total_start_time = datetime.now()
    
    try:
        # 同步日历数据
        calendar_results = {}
        if not args.skip_calendars:
            calendar_results = sync_calendars(conn, verifier)
        else:
            print("⏭️  跳过日历同步")
        
        # 同步标的数据
        instrument_results = {}
        if not args.skip_instruments:
            instrument_results = sync_instruments(conn, verifier)
        else:
            print("⏭️  跳过期标同步")
        
        # 同步特征数据
        feature_results = {}
        if not args.skip_features:
            limit_symbols = None
            if args.test:
                limit_symbols = 10
            elif args.symbols:
                limit_symbols = args.symbols
            
            # 使用统一表版本的函数
            feature_results = sync_features_unified(
                conn, verifier, 
                limit_symbols=limit_symbols,
                features=args.features
            )
        else:
            print("⏭️  跳过特征同步")
        
        # 创建示例查询
        create_sample_queries(conn)
        
        # 计算总耗时
        total_duration = (datetime.now() - total_start_time).total_seconds()
        
        # 生成报告
        print("\n" + "=" * 80)
        print("📊 同步完成报告")
        print("=" * 80)
        
        report = verifier.generate_report()
        print(report)
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = LOG_DIR / f"sync_report_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("HK Qlib数据同步报告\n")
            f.write("=" * 80 + "\n")
            f.write(f"同步时间: {datetime.now()}\n")
            f.write(f"数据源: {QLIB_ROOT}\n")
            f.write(f"数据库: {db_path}\n")
            f.write(f"特征表: feature_day\n")
            f.write(f"同步特征: {', '.join(args.features)}\n")
            f.write(f"总耗时: {total_duration:.2f}秒\n")
            f.write("=" * 80 + "\n\n")
            f.write(report)
        
        print(f"📄 详细报告已保存: {report_file}")
        print("=" * 80)
        print(f"✅ 同步完成! 总耗时: {total_duration:.2f}秒")
        print(f"📁 数据库文件: {db_path.absolute()}")
        print(f"📊 特征表: feature_day")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ 同步过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        conn.close()
        print("\n🔌 数据库连接已关闭")

if __name__ == "__main__":
    main()