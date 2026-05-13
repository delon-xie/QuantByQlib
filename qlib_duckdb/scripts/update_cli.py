"""
增量更新命令行工具
"""
import argparse
import sys
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import json

from ..managers.incremental_updater import IncrementalUpdateManager
from ..duckdb_connection import get_connection
from ..config import config
from ..utils.logging_setup import setup_logging
import logging

logger = logging.getLogger(__name__)


def update_from_csv(args):
    """从 CSV 文件更新数据"""
    reg = args.reg
    freq = args.freq
    csv_path = args.csv_path
    symbol_col = args.symbol_col
    datetime_col = args.datetime_col
    on_conflict = args.on_conflict
    
    print(f"📤 正在从 CSV 文件更新 {freq} 数据...")
    print(f"📁 文件: {csv_path}")
    print(f"🏷️  区域: {reg}")
    print("-" * 80)
    
    try:
        # 读取 CSV 文件
        print(f"正在读取 CSV 文件...")
        df = pd.read_csv(csv_path)
        print(f"✅ 读取成功: {len(df)} 行, {len(df.columns)} 列")
        
        # 显示前几行
        print("\n🔍 数据预览:")
        print(df.head())
        print(f"\n列名: {list(df.columns)}")
        
        # 检查必要列
        required_cols = ["open", "high", "low", "close", "volume"]
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            print(f"⚠️  警告: 缺少以下列: {missing_cols}")
            print("将在更新时填充 NaN 值")
        
        # 确认更新
        if not args.yes:
            confirm = input(f"\n⚠️  确认更新 {len(df)} 行数据到 {freq} 表? (y/n): ")
            if confirm.lower() != 'y':
                print("❌ 已取消更新")
                return
        
        # 执行更新
        print(f"\n🔄 正在更新数据到 {freq} 表...")
        updater = IncrementalUpdateManager(reg)
        
        affected = updater.update_from_dataframe(
            freq=freq,
            data=df,
            symbol_col=symbol_col,
            datetime_col=datetime_col,
            on_conflict=on_conflict
        )
        
        print(f"\n✅ 更新完成!")
        print(f"📊 影响行数: {affected:,}")
        
        # 显示统计
        symbols = df[symbol_col].nunique() if symbol_col in df.columns else 0
        if symbols > 0:
            print(f"📈 更新标的数: {symbols}")
        
        if 'datetime' in df.columns or datetime_col in df.columns:
            date_col = 'datetime' if 'datetime' in df.columns else datetime_col
            if date_col in df.columns:
                date_range = df[date_col].agg(['min', 'max'])
                print(f"📅 时间范围: {date_range['min']} 到 {date_range['max']}")
        
    except Exception as e:
        logger.error(f"从 CSV 更新失败: {e}")
        print(f"❌ 更新失败: {e}")
        sys.exit(1)


def update_single_symbol(args):
    """更新单个标的"""
    reg = args.reg
    symbol = args.symbol
    freq = args.freq
    data_file = args.data_file
    on_conflict = args.on_conflict
    
    print(f"📤 正在更新单个标的 {symbol} 的 {freq} 数据...")
    print(f"🏷️  区域: {reg}")
    print("-" * 80)
    
    try:
        # 读取数据文件
        print(f"正在读取数据文件: {data_file}")
        
        if data_file.endswith('.csv'):
            df = pd.read_csv(data_file)
        elif data_file.endswith('.parquet'):
            df = pd.read_parquet(data_file)
        elif data_file.endswith('.json'):
            df = pd.read_json(data_file)
        else:
            # 尝试读取 CSV
            df = pd.read_csv(data_file)
        
        print(f"✅ 读取成功: {len(df)} 行")
        
        # 确保 symbol 列存在
        if 'symbol' not in df.columns:
            # 添加 symbol 列
            df['symbol'] = symbol
            print(f"➕ 已添加 symbol 列: {symbol}")
        
        # 检查数据
        print("\n🔍 数据预览:")
        print(df.head())
        
        # 确认更新
        if not args.yes:
            confirm = input(f"\n⚠️  确认更新 {symbol} 的 {len(df)} 行数据? (y/n): ")
            if confirm.lower() != 'y':
                print("❌ 已取消更新")
                return
        
        # 执行更新
        print(f"\n🔄 正在更新 {symbol} 的数据...")
        updater = IncrementalUpdateManager(reg)
        
        # 准备数据字典格式
        data_dict = {freq: df}
        
        results = updater.update_symbol(
            symbol=symbol,
            data_dict=data_dict,
            on_conflict=on_conflict
        )
        
        print(f"\n✅ 更新完成!")
        print(f"📊 结果: {results}")
        
        # 显示最新时间
        latest = updater.get_latest_datetime(symbol, freq)
        if latest:
            print(f"⏰ 最新数据时间: {latest}")
        
    except Exception as e:
        logger.error(f"更新单个标的失败: {e}")
        print(f"❌ 更新失败: {e}")
        sys.exit(1)


def update_from_directory(args):
    """从目录批量更新"""
    reg = args.reg
    directory = args.directory
    freq = args.freq
    file_pattern = args.pattern
    on_conflict = args.on_conflict
    
    print(f"📤 正在从目录批量更新 {freq} 数据...")
    print(f"📁 目录: {directory}")
    print(f"🏷️  区域: {reg}")
    print(f"🔍 文件模式: {file_pattern}")
    print("-" * 80)
    
    try:
        # 查找文件
        from glob import glob
        file_paths = list(Path(directory).glob(file_pattern))
        
        if not file_paths:
            print(f"❌ 未找到匹配的文件: {file_pattern}")
            return
        
        print(f"📂 找到 {len(file_paths)} 个文件")
        
        # 预览文件
        for i, file_path in enumerate(file_paths[:5], 1):
            print(f"  {i}. {file_path.name}")
        if len(file_paths) > 5:
            print(f"  ... 还有 {len(file_paths) - 5} 个文件")
        
        # 确认更新
        if not args.yes:
            total_rows = 0
            print("\n📊 正在统计总行数...")
            
            for file_path in file_paths[:10]:  # 限制检查前10个文件
                try:
                    if file_path.suffix == '.csv':
                        df = pd.read_csv(file_path, nrows=0)
                        # 估计行数
                        with open(file_path, 'r', encoding='utf-8') as f:
                            line_count = sum(1 for _ in f) - 1  # 减去标题行
                        total_rows += line_count
                except:
                    pass
            
            print(f"📈 预估总行数: {total_rows:,}")
            
            confirm = input(f"\n⚠️  确认批量更新 {len(file_paths)} 个文件? (y/n): ")
            if confirm.lower() != 'y':
                print("❌ 已取消更新")
                return
        
        # 执行批量更新
        print(f"\n🔄 正在批量更新数据...")
        updater = IncrementalUpdateManager(reg)
        total_affected = 0
        file_results = {}
        
        for i, file_path in enumerate(file_paths, 1):
            try:
                print(f"\n[{i}/{len(file_paths)}] 处理: {file_path.name}")
                
                # 读取文件
                if file_path.suffix == '.csv':
                    df = pd.read_csv(file_path)
                elif file_path.suffix == '.parquet':
                    df = pd.read_parquet(file_path)
                elif file_path.suffix == '.json':
                    df = pd.read_json(file_path)
                else:
                    print(f"⚠️  不支持的格式: {file_path.suffix}，跳过")
                    continue
                
                print(f"  读取: {len(df):,} 行")
                
                # 更新数据
                affected = updater.update_from_dataframe(
                    freq=freq,
                    data=df,
                    symbol_col='symbol',
                    datetime_col='datetime',
                    on_conflict=on_conflict
                )
                
                print(f"  ✅ 更新: {affected:,} 行")
                total_affected += affected
                file_results[file_path.name] = {"status": "success", "rows": affected}
                
            except Exception as e:
                print(f"  ❌ 失败: {e}")
                file_results[file_path.name] = {"status": "failed", "error": str(e)}
        
        print(f"\n✅ 批量更新完成!")
        print(f"📊 总影响行数: {total_affected:,}")
        print(f"📁 成功文件: {sum(1 for r in file_results.values() if r['status'] == 'success')}")
        print(f"❌ 失败文件: {sum(1 for r in file_results.values() if r['status'] == 'failed')}")
        
        # 保存结果
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "reg": reg,
                    "freq": freq,
                    "total_affected": total_affected,
                    "file_results": file_results
                }, f, indent=2, ensure_ascii=False)
            print(f"📄 详细结果已保存到: {args.output}")
        
    except Exception as e:
        logger.error(f"批量更新失败: {e}")
        print(f"❌ 批量更新失败: {e}")
        sys.exit(1)


def check_missing(args):
    """检查缺失数据"""
    reg = args.reg
    symbol = args.symbol
    freq = args.freq
    start_time = args.start_time
    end_time = args.end_time
    
    print(f"🔍 正在检查 {symbol} 的缺失数据...")
    print(f"📅 频率: {freq}")
    print(f"⏰ 时间范围: {start_time} 到 {end_time}")
    print(f"🏷️  区域: {reg}")
    print("-" * 80)
    
    try:
        updater = IncrementalUpdateManager(reg)
        
        # 转换时间
        start_dt = pd.Timestamp(start_time)
        end_dt = pd.Timestamp(end_time)
        
        # 获取缺失时间段
        missing_periods = updater.get_missing_periods(
            symbol=symbol,
            freq=freq,
            start_time=start_dt,
            end_time=end_dt
        )
        
        if missing_periods:
            print(f"❌ 发现 {len(missing_periods)} 个缺失时间段:")
            
            for i, (start, end) in enumerate(missing_periods, 1):
                # 计算缺失天数/条数
                if freq == "day":
                    days = (end - start).days + 1
                    print(f"  {i}. {start.date()} 到 {end.date()} ({days} 天)")
                elif freq == "1h":
                    hours = (end - start).total_seconds() / 3600 + 1
                    print(f"  {i}. {start} 到 {end} ({hours:.0f} 小时)")
                elif freq in ["5m", "15m", "30m"]:
                    minutes = (end - start).total_seconds() / 60 + 1
                    interval = int(freq[:-1])  # 提取分钟数
                    bars = minutes / interval
                    print(f"  {i}. {start} 到 {end} ({bars:.0f} 根K线)")
                else:
                    print(f"  {i}. {start} 到 {end}")
        else:
            print(f"✅ 无缺失数据，时间段完整!")
        
        # 获取最新数据时间
        latest = updater.get_latest_datetime(symbol, freq)
        if latest:
            print(f"\n⏰ 最新数据时间: {latest}")
            
            # 计算最后更新时间
            now = datetime.now()
            if isinstance(latest, pd.Timestamp):
                latest_dt = latest.to_pydatetime()
            else:
                latest_dt = latest
            
            time_diff = now - latest_dt
            if time_diff.days > 0:
                print(f"⏳ 最后更新: {time_diff.days} 天前")
            elif time_diff.seconds > 3600:
                print(f"⏳ 最后更新: {time_diff.seconds // 3600} 小时前")
            elif time_diff.seconds > 60:
                print(f"⏳ 最后更新: {time_diff.seconds // 60} 分钟前")
            else:
                print(f"⏳ 最后更新: {time_diff.seconds} 秒前")
        
    except Exception as e:
        logger.error(f"检查缺失数据失败: {e}")
        print(f"❌ 检查失败: {e}")
        sys.exit(1)


def sync_from_api(args):
    """从 API 同步数据"""
    reg = args.reg
    symbol = args.symbol
    freq = args.freq
    days = args.days
    data_source = args.data_source
    on_conflict = args.on_conflict
    
    print(f"🔄 正在从 {data_source} API 同步数据...")
    print(f"📈 标的: {symbol}")
    print(f"📅 频率: {freq}")
    print(f"⏰ 天数: {days}")
    print(f"🏷️  区域: {reg}")
    print("-" * 80)
    
    try:
        # 导入数据获取模块
        try:
            if data_source == "akshare":
                import akshare as ak
                print("✅ 已导入 akshare")
            elif data_source == "yfinance":
                import yfinance as yf
                print("✅ 已导入 yfinance")
            elif data_source == "tushare":
                import tushare as ts
                print("✅ 已导入 tushare")
            else:
                print(f"❌ 不支持的数据源: {data_source}")
                print("支持的数据源: akshare, yfinance, tushare")
                sys.exit(1)
        except ImportError as e:
            print(f"❌ 无法导入 {data_source}: {e}")
            print(f"请安装: pip install {data_source}")
            sys.exit(1)
        
        # 获取最新数据时间
        updater = IncrementalUpdateManager(reg)
        latest = updater.get_latest_datetime(symbol, freq)
        
        if latest:
            print(f"📅 数据库中最新时间: {latest}")
            start_date = pd.Timestamp(latest) + timedelta(days=1)
        else:
            print("📅 数据库中无数据，获取历史数据")
            start_date = datetime.now() - timedelta(days=days)
        
        end_date = datetime.now()
        
        print(f"📅 获取时间范围: {start_date} 到 {end_date}")
        
        # 确认同步
        if not args.yes:
            confirm = input(f"\n⚠️  确认从 {data_source} 同步数据? (y/n): ")
            if confirm.lower() != 'y':
                print("❌ 已取消同步")
                return
        
        # 获取数据
        print(f"\n📥 正在从 {data_source} 获取数据...")
        
        df = None
        
        if data_source == "akshare":
            # 根据频率调用不同接口
            if freq == "day":
                df = ak.stock_zh_a_hist(
                    symbol=symbol[2:],  # 去掉市场前缀
                    period="daily",
                    start_date=start_date.strftime("%Y%m%d"),
                    end_date=end_date.strftime("%Y%m%d"),
                    adjust="qfq"
                )
                if not df.empty:
                    df = df.rename(columns={
                        '日期': 'datetime',
                        '开盘': 'open',
                        '最高': 'high',
                        '最低': 'low',
                        '收盘': 'close',
                        '成交量': 'volume'
                    })
                    df['symbol'] = symbol
        
        elif data_source == "yfinance":
            # yfinance
            ticker = yf.Ticker(symbol)
            
            if freq == "day":
                interval = "1d"
            elif freq == "1h":
                interval = "1h"
            elif freq == "5m":
                interval = "5m"
            else:
                interval = "1d"
            
            df = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval
            )
            
            if not df.empty:
                df = df.reset_index()
                df = df.rename(columns={
                    'Date': 'datetime',
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Close': 'close',
                    'Volume': 'volume'
                })
                df['symbol'] = symbol
        
        elif data_source == "tushare":
            # 需要先设置 token
            ts_token = input("请输入 tushare token (或按 Enter 跳过): ")
            if ts_token:
                ts.set_token(ts_token)
                pro = ts.pro_api()
                
                if freq == "day":
                    df = pro.daily(
                        ts_code=symbol,
                        start_date=start_date.strftime("%Y%m%d"),
                        end_date=end_date.strftime("%Y%m%d")
                    )
                    if not df.empty:
                        df = df.rename(columns={
                            'trade_date': 'datetime',
                            'open': 'open',
                            'high': 'high',
                            'low': 'low',
                            'close': 'close',
                            'vol': 'volume'
                        })
                        df['datetime'] = pd.to_datetime(df['datetime'])
                        df['symbol'] = symbol
        
        if df is None or df.empty:
            print("⚠️  未获取到数据")
            return
        
        print(f"✅ 获取到 {len(df)} 行数据")
        print("\n🔍 数据预览:")
        print(df.head())
        
        # 更新数据
        print(f"\n🔄 正在更新到数据库...")
        
        data_dict = {freq: df}
        results = updater.update_symbol(
            symbol=symbol,
            data_dict=data_dict,
            on_conflict=on_conflict
        )
        
        print(f"\n✅ 同步完成!")
        print(f"📊 结果: {results}")
        
        # 显示最新时间
        new_latest = updater.get_latest_datetime(symbol, freq)
        if new_latest:
            print(f"⏰ 最新数据时间: {new_latest}")
        
    except Exception as e:
        logger.error(f"API 同步失败: {e}")
        print(f"❌ 同步失败: {e}")
        sys.exit(1)


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="qlib-duckdb 增量更新命令行工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 从 CSV 文件更新
  python -m qlib_duckdb.scripts.update_cli from-csv --reg cn --freq day --csv-path data.csv
  
  # 更新单个标的
  python -m qlib_duckdb.scripts.update_cli single-symbol --reg cn --symbol SH600000 --freq day --data-file data.csv
  
  # 从目录批量更新
  python -m qlib_duckdb.scripts.update_cli from-dir --reg cn --freq day --directory ./data/ --pattern "*.csv"
  
  # 检查缺失数据
  python -m qlib_duckdb.scripts.update_cli check-missing --reg cn --symbol SH600000 --freq day --start-time 2023-01-01 --end-time 2023-12-31
  
  # 从 API 同步数据
  python -m qlib_duckdb.scripts.update_cli from-api --reg cn --symbol SH600000 --freq day --days 30 --data-source akshare
  
  # 自动确认 (跳过确认提示)
  在所有命令后添加 --yes
        """
    )
    
    parser.add_argument("--reg", type=str, default="cn", 
                       help="市场区域 (cn, us, hk 等)")
    parser.add_argument("--yes", "-y", action="store_true",
                       help="自动确认，跳过提示")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="显示详细日志")
    
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # from-csv 命令
    csv_parser = subparsers.add_parser("from-csv", help="从 CSV 文件更新数据")
    csv_parser.add_argument("--freq", type=str, required=True,
                           help="频率 (day, 5m, 1h 等)")
    csv_parser.add_argument("--csv-path", type=str, required=True,
                           help="CSV 文件路径")
    csv_parser.add_argument("--symbol-col", type=str, default="symbol",
                           help="标的代码列名")
    csv_parser.add_argument("--datetime-col", type=str, default="datetime",
                           help="日期时间列名")
    csv_parser.add_argument("--on-conflict", type=str, default="replace",
                           choices=["replace", "ignore", "error"],
                           help="冲突处理策略")
    csv_parser.set_defaults(func=update_from_csv)
    
    # single-symbol 命令
    symbol_parser = subparsers.add_parser("single-symbol", help="更新单个标的")
    symbol_parser.add_argument("--symbol", type=str, required=True,
                              help="标的代码")
    symbol_parser.add_argument("--freq", type=str, required=True,
                              help="频率")
    symbol_parser.add_argument("--data-file", type=str, required=True,
                              help="数据文件路径 (支持 csv, parquet, json)")
    symbol_parser.add_argument("--on-conflict", type=str, default="replace",
                              choices=["replace", "ignore", "error"],
                              help="冲突处理策略")
    symbol_parser.set_defaults(func=update_single_symbol)
    
    # from-dir 命令
    dir_parser = subparsers.add_parser("from-dir", help="从目录批量更新")
    dir_parser.add_argument("--freq", type=str, required=True,
                           help="频率")
    dir_parser.add_argument("--directory", type=str, required=True,
                           help="数据目录")
    dir_parser.add_argument("--pattern", type=str, default="*.csv",
                           help="文件匹配模式")
    dir_parser.add_argument("--on-conflict", type=str, default="replace",
                           choices=["replace", "ignore", "error"],
                           help="冲突处理策略")
    dir_parser.add_argument("--output", type=str,
                           help="结果输出文件路径")
    dir_parser.set_defaults(func=update_from_directory)
    
    # check-missing 命令
    missing_parser = subparsers.add_parser("check-missing", help="检查缺失数据")
    missing_parser.add_argument("--symbol", type=str, required=True,
                               help="标的代码")
    missing_parser.add_argument("--freq", type=str, required=True,
                               help="频率")
    missing_parser.add_argument("--start-time", type=str, required=True,
                               help="开始时间 (YYYY-MM-DD)")
    missing_parser.add_argument("--end-time", type=str, required=True,
                               help="结束时间 (YYYY-MM-DD)")
    missing_parser.set_defaults(func=check_missing)
    
    # from-api 命令
    api_parser = subparsers.add_parser("from-api", help="从 API 同步数据")
    api_parser.add_argument("--symbol", type=str, required=True,
                           help="标的代码")
    api_parser.add_argument("--freq", type=str, required=True,
                           help="频率")
    api_parser.add_argument("--days", type=int, default=30,
                           help="获取最近多少天的数据")
    api_parser.add_argument("--data-source", type=str, required=True,
                           choices=["akshare", "yfinance", "tushare"],
                           help="数据源")
    api_parser.add_argument("--on-conflict", type=str, default="replace",
                           choices=["replace", "ignore", "error"],
                           help="冲突处理策略")
    api_parser.set_defaults(func=sync_from_api)
    
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