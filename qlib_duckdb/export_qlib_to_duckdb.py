#!/usr/bin/env python3
"""
Qlib数据完整导出脚本
从Qlib本地bin格式导出到DuckDB数据库
包括：日历、标的、特征、指数定义、指数成员数据
"""

import sys
import os
import pandas as pd
import numpy as np
from pathlib import Path
import logging
from datetime import datetime, timedelta
import time
from tqdm import tqdm
import duckdb

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))
# 获取项目根目录
project_root = Path(__file__).resolve().parent.parent

print(project_root)

# 添加到搜索路径
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
    
# 导入Qlib相关
import qlib
from qlib.data import D
from core.qlibhelper import REG_CN, REG_US, REG_HK

# 导入本地模块
from qlib_duckdb.duckdb_connection import DuckDBConnection
from qlib_duckdb.schema import SchemaManager
from qlib_duckdb.managers.index_manager import IndexManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('qlib_export.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class QlibToDuckDBExporter:
    """Qlib数据导出到DuckDB的完整解决方案"""
    
    def __init__(self, reg="hk", freq="day", db_path=None):
        """
        初始化导出器
        
        Args:
            reg: 地区，如 "hk", "cn", "us"
            freq: 频率，如 "day", "1min"
            db_path: DuckDB数据库路径，如果为None则使用默认路径
        """
        self.reg = reg
        self.freq = freq
        self.db_path = db_path or self._get_default_db_path()
        
        # 初始化Qlib
        self._init_qlib()
        
        # 数据库连接
        self.conn = None
        self.connection_pool = []
        
        # 导出统计
        self.stats = {
            'calendar_rows': 0,
            'instrument_rows': 0,
            'feature_symbols': 0,
            'feature_rows': 0,
            'indices': 0,
            'index_members': 0
        }
    
    def _get_default_db_path(self):
        """获取默认数据库路径"""
        qlib_dir = Path.home() / ".qlib"
        db_dir = qlib_dir / "duckdb"
        db_dir.mkdir(exist_ok=True)
        
        if self.reg == "hk":
            return str(db_dir / "hk_data.duckdb")
        elif self.reg == "cn":
            return str(db_dir / "cn_data.duckdb")
        elif self.reg == "us":
            return str(db_dir / "us_data.duckdb")
        else:
            return str(db_dir / f"{self.reg}_data.duckdb")
    
    def _init_qlib(self):
        """初始化Qlib并设置地区"""
        try:
            region = self.reg
            # 导入Qlib辅助模块
            sys.path.insert(0, str(Path(__file__).parent.parent))
            
            import qlib
            from qlib.data import D
            from core.app_state import get_state
            from core.qlibhelper import _check_qlib_init
            from core.event_bus import get_event_bus
            bus = get_event_bus()
            get_state().reg = region
            _check_qlib_init(bus)
            
            logger.info(f"✅ Qlib初始化成功，地区: {region}")
            return True
        except Exception as e:
            logger.error(f"❌ Qlib初始化失败: {e}")
            raise

    
    def _get_connection(self, read_only=False):
        """获取数据库连接"""
        if not self.conn:
            # 使用连接池获取连接
            db_conn = DuckDBConnection(self.reg, read_only=read_only)
            self.conn = db_conn.connection
            
            # 设置优化参数
            self.conn.execute("PRAGMA threads=4")
            self.conn.execute("PRAGMA memory_limit='4GB'")
        
        return self.conn
    
    def _close_connection(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None
    
    def export_all(self, start_date="2000-01-01", end_date=None):
        """
        导出所有数据
        
        Args:
            start_date: 开始日期
            end_date: 结束日期，默认为今天
        """
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"🚀 开始导出数据: region={self.reg}, freq={self.freq}, 日期范围={start_date}~{end_date}")
        logger.info(f"📁 数据库: {self.db_path}")
        
        start_time = time.time()
        
        try:
            # 1. 创建所有表
            self._create_tables()
            
            # 2. 导出日历数据
            self.export_calendar(start_date, end_date)
            
            # 3. 导出标的数据
            self.export_instruments()
            
            # 4. 导出特征数据
            self.export_features(start_date, end_date)
            
            # 5. 导出指数数据
            self.export_indices()
            
            # 6. 验证导出结果
            self.validate_export()
            
            # 计算总耗时
            total_time = time.time() - start_time
            
            # 输出统计信息
            self._print_stats(total_time)
            
            logger.info(f"🎉 数据导出完成!")
            
        except Exception as e:
            logger.error(f"❌ 数据导出失败: {e}")
            raise
        
        finally:
            # 确保关闭连接
            self._close_connection()
    
    def _create_tables(self):
        """创建所有需要的表"""
        logger.info("📊 创建数据库表...")
        
        conn = self._get_connection(read_only=False)
        
        # 使用SchemaManager创建表
        schema_manager = SchemaManager()
        schema_manager.create_all_tables(self.reg)
        schema_manager.create_all_tables_for_freq(self.reg, self.freq)
        
        logger.info("✅ 数据库表创建完成")
    
    def export_calendar(self, start_date, end_date):
        """导出日历数据"""
        logger.info("📅 导出日历数据...")
        
        try:
            # 从Qlib获取日历
            calendar = D.calendar(start_time=start_date, end_time=end_date, freq=self.freq)
            
            if len(calendar) == 0:
                logger.warning("⚠️  日历数据为空")
                return
            
            # 转换为DataFrame
            df_calendar = pd.DataFrame({"datetime": calendar})
            
            # 写入数据库
            conn = self._get_connection(read_only=False)
            table_name = f"calendar_{self.freq}"
            
            # 清空表
            conn.execute(f"DELETE FROM {table_name}")
            
            # 插入数据
            temp_table = "temp_calendar"
            conn.register(temp_table, df_calendar)
            conn.execute(f"INSERT INTO {table_name} SELECT * FROM {temp_table}")
            
            # 记录统计
            self.stats['calendar_rows'] = len(df_calendar)
            
            logger.info(f"✅ 导出日历数据完成: {len(df_calendar)} 行")
            
        except Exception as e:
            logger.error(f"❌ 导出日历数据失败: {e}")
            raise
    
    def export_instruments(self):
        """导出标的数据"""
        logger.info("📈 导出标的数据...")
        
        try:
            # 从Qlib获取所有标的
            all_instruments = D.instruments(market="all")
            all_symbols = D.list_instruments(all_instruments, freq=self.freq, as_list=True)
            
            if not all_symbols:
                logger.warning("⚠️  标的数据为空")
                return
            
            logger.info(f"📊 获取到 {len(all_symbols)} 个标的")
            
            # 准备数据
            data = []
            for symbol in all_symbols:
                # 这里可以添加获取标的具体信息（如起止日期）的逻辑
                data.append({
                    "symbol": symbol,
                    "start_date": None,  # 可以从Qlib获取实际日期
                    "end_date": None
                })
            
            df_instruments = pd.DataFrame(data)
            
            # 写入数据库
            conn = self._get_connection(read_only=False)
            
            # 清空表
            conn.execute("DELETE FROM instrument")
            
            # 插入数据
            temp_table = "temp_instruments"
            conn.register(temp_table, df_instruments)
            conn.execute("INSERT INTO instrument SELECT * FROM temp_instruments")
            
            # 记录统计
            self.stats['instrument_rows'] = len(df_instruments)
            
            logger.info(f"✅ 导出标的数据完成: {len(df_instruments)} 行")
            
        except Exception as e:
            logger.error(f"❌ 导出标的数据失败: {e}")
            raise
    
    def export_features(self, start_date, end_date, batch_size=50):
        """导出特征数据"""
        logger.info("🎯 导出特征数据...")
        
        try:
            # 获取所有标的
            all_instruments = D.instruments(market="all")
            all_symbols = D.list_instruments(all_instruments, freq=self.freq, as_list=True)
            
            if not all_symbols:
                logger.warning("⚠️  没有标的可导出特征数据")
                return
            
            logger.info(f"📊 准备导出 {len(all_symbols)} 个标的的特征数据")
            
            # 定义要导出的特征
            features = ['$open', '$close', '$low', '$high', '$volume']
            feature_mapping = {
                '$open': 'open',
                '$close': 'close',
                '$low': 'low',
                '$high': 'high',
                '$volume': 'volume',
                '$factor': 'factor',
                
                # 常见技术指标列
                '$vwap': 'vwap',            #成交量加权平均价
                '$body': 'body',            # abs(Close - Open)
                '$body_abs': 'body_abs',    # abs(Close - Open)
                '$range': 'range',          # High - Low
                '$change': 'change',        # Close - Previous Close
                #crypto列
                '$quote_volume': 'quote_volume',
                '$taker_buy_base': 'taker_buy_base',
                '$trade_count': 'trade_count',
                #中国市场
                '$adjclose': 'adjclose',
            }
            
            conn = self._get_connection(read_only=False)
            table_name = f"feature_{self.freq}"
            
            # 进度条
            total_symbols = len(all_symbols)
            success_count = 0
            total_rows = 0
            
            with tqdm(total=total_symbols, desc="导出进度", unit="股票", 
                     bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}{postfix}]") as pbar:
                
                # 分批处理
                for i in range(0, total_symbols, batch_size):
                    batch_symbols = all_symbols[i:i+batch_size]
                    
                    for symbol in batch_symbols:
                        try:
                            # 获取特征数据
                            df_feature = D.features(
                                [symbol],
                                features,
                                freq=self.freq
                            ).reset_index()
                            
                            if df_feature.empty:
                                pbar.set_postfix_str(f"{symbol}: 无数据")
                                continue
                            
                            # 重命名列
                            #df_feature = df_feature.rename(columns=feature_mapping)
                            
                            # 添加symbol列
                            #df_feature['symbol'] = symbol
                            
                            # 选择需要的列
                            #cols_to_keep = ['symbol', 'datetime', 'open', 'high', 'low', 'close', 'volume']
                            #df_feature = df_feature[cols_to_keep]
                            
                            # 插入数据
                            temp_table = f"temp_feature_{symbol.replace('.', '_')}"
                            conn.register(temp_table, df_feature)
                            
                            insert_sql = f"""
                            INSERT OR REPLACE INTO {table_name} (symbol, datetime, open, high, low, close, volume)
                            SELECT "instrument" as symbol, "datetime" as datetime, 
                                "$open" as open, "$high" as high, "$low" as low, 
                                "$close" as close, "$volume" as volume
                            FROM {temp_table}
                            """
                            
                            conn.execute(insert_sql)
                            
                            success_count += 1
                            total_rows += len(df_feature)
                            pbar.set_postfix_str(f"{symbol}: {len(df_feature)}行")
                            
                        except Exception as e:
                            pbar.set_postfix_str(f"{symbol}: 错误")
                            logger.debug(f"处理{symbol}时出错: {e}")
                        
                        pbar.update(1)
            
            # 记录统计
            self.stats['feature_symbols'] = success_count
            self.stats['feature_rows'] = total_rows
            
            logger.info(f"✅ 导出特征数据完成: {success_count} 个标的, {total_rows} 行数据")
            
        except Exception as e:
            logger.error(f"❌ 导出特征数据失败: {e}")
            raise
    
    def export_indices(self):
        """导出指数数据"""
        logger.info("📊 导出指数数据...")
        
        try:
            # 初始化IndexManager
            index_manager = IndexManager(reg=self.reg)
            
            # 从Qlib instruments目录同步指数数据
            qlib_dir = Path.home() / ".qlib" / "qlib_data" / f"{self.reg}_data"
            instruments_dir = qlib_dir / "instruments"
            
            if not instruments_dir.exists():
                logger.warning(f"⚠️  Qlib instruments目录不存在: {instruments_dir}")
                return
            
            # 查找所有指数文件
            index_files = list(instruments_dir.glob("*.txt"))
            
            if not index_files:
                logger.warning(f"⚠️  在 {instruments_dir} 中没有找到指数文件")
                return
            
            logger.info(f"📁 找到 {len(index_files)} 个指数文件")
            
            # 同步所有指数
            # 调用index_manager同步
            sync_result = index_manager.sync_from_qlib(qlib_dir)
            
            # 修复：检查 status 是否为 'completed' 或 'success'
            if sync_result.get('status') in ['completed', 'success']:
                # 从数据库获取统计信息
                conn = self._get_connection(read_only=True)
                
                # 获取指数数量
                result = conn.execute("SELECT COUNT(*) FROM index_def").fetchone()
                self.stats['indices'] = result[0] if result else 0
                
                # 获取指数成员数量
                result = conn.execute("SELECT COUNT(*) FROM index_member").fetchone()
                self.stats['index_members'] = result[0] if result else 0
                
                logger.info(f"✅ 导出指数数据完成: {self.stats['indices']} 个指数, {self.stats['index_members']} 个成员")
            else:
                logger.error(f"❌ 指数同步失败: {sync_result}")
                
        except Exception as e:
            logger.error(f"❌ 导出指数数据失败: {e}")
            raise
    
    def validate_export(self):
        """验证导出结果"""
        logger.info("🔍 验证导出结果...")
        
        try:
            conn = self._get_connection(read_only=True)
            
            # 检查表是否存在且有数据
            tables_to_check = [
                ("calendar", f"calendar_{self.freq}"),
                ("instrument", "instrument"),
                ("features", f"feature_{self.freq}"),
                ("indices", "index_def"),
                ("index_members", "index_member")
            ]
            
            for table_desc, table_name in tables_to_check:
                try:
                    result = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()
                    count = result[0] if result else 0
                    
                    if count > 0:
                        logger.info(f"✅ {table_desc}: {count} 行")
                    else:
                        logger.warning(f"⚠️  {table_desc}: 空表")
                        
                except Exception as e:
                    logger.warning(f"⚠️  检查表 {table_name} 失败: {e}")
            
            # 检查数据质量
            self._check_data_quality(conn)
            
            logger.info("✅ 验证完成")
            
        except Exception as e:
            logger.error(f"❌ 验证失败: {e}")
    
    def _check_data_quality(self, conn):
        """检查数据质量"""
        logger.info("🔬 检查数据质量...")
        
        # 检查日历数据的连续性
        try:
            result = conn.execute(f"""
            SELECT 
                MIN(datetime) as min_date,
                MAX(datetime) as max_date,
                COUNT(*) as total_days,
                COUNT(DISTINCT datetime) as unique_days
            FROM calendar_{self.freq}
            """).fetchone()
            
            if result:
                min_date, max_date, total_days, unique_days = result
                if total_days == unique_days:
                    logger.info(f"📅 日历数据连续: {min_date} 到 {max_date}, {total_days} 天")
                else:
                    logger.warning(f"⚠️  日历数据有重复: {total_days} 行, {unique_days} 唯一")
        except:
            pass
        
        # 检查特征数据的完整性
        try:
            result = conn.execute(f"""
            SELECT 
                COUNT(*) as total_rows,
                COUNT(DISTINCT symbol) as unique_symbols,
                AVG(CASE WHEN open IS NULL THEN 1 ELSE 0 END) as null_open_pct
            FROM feature_{self.freq}
            """).fetchone()
            
            if result:
                total_rows, unique_symbols, null_open_pct = result
                logger.info(f"📈 特征数据: {total_rows} 行, {unique_symbols} 个标的")
                
                if null_open_pct > 0.5:
                    logger.warning(f"⚠️  开盘价空值比例较高: {null_open_pct*100:.1f}%")
        except:
            pass
    
    def _print_stats(self, total_time):
        """打印统计信息"""
        print("\n" + "="*60)
        print("📊 导出统计信息")
        print("="*60)
        
        stats_table = [
            ("日历数据", f"{self.stats['calendar_rows']} 行"),
            ("标的数据", f"{self.stats['instrument_rows']} 个"),
            ("特征数据", f"{self.stats['feature_symbols']} 个标的, {self.stats['feature_rows']} 行"),
            ("指数定义", f"{self.stats['indices']} 个"),
            ("指数成员", f"{self.stats['index_members']} 个"),
        ]
        
        for item, value in stats_table:
            print(f"{item:15}: {value}")
        
        print(f"{'总耗时':15}: {total_time:.1f} 秒")
        print("="*60)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='从Qlib导出数据到DuckDB')
    parser.add_argument('--reg', type=str, default='hk', help='地区: hk/cn/us')
    parser.add_argument('--freq', type=str, default='day', help='频率: day/1min')
    parser.add_argument('--start', type=str, default='2000-01-01', help='开始日期')
    parser.add_argument('--end', type=str, default=None, help='结束日期')
    parser.add_argument('--db', type=str, default=None, help='数据库路径')
    parser.add_argument('--batch', type=int, default=50, help='批量处理大小')
    
    args = parser.parse_args()
    
    try:
        # 创建导出器
        exporter = QlibToDuckDBExporter(
            reg=args.reg,
            freq=args.freq,
            db_path=args.db
        )
        
        # 执行导出
        exporter.export_all(
            start_date=args.start,
            end_date=args.end
        )
        
    except KeyboardInterrupt:
        logger.info("⏹️  导出被用户中断")
        sys.exit(1)
    except Exception as e:
        logger.error(f"💥 导出过程发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()