"""
数据迁移管理器
"""
import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Optional, Dict, Any
from tqdm import tqdm
import logging

from ..duckdb_connection import DuckDBConnection
from ..schema import SchemaManager
from ..constants import SUPPORTED_FREQS, BASE_FIELDS
from ..storage.feature import DuckDBFeatureStorage
from ..storage.calendar import DuckDBCalendarStorage
from ..storage.instrument import DuckDBInstrumentStorage
from ..exceptions import MigrationError, ValidationError
from ..config import config

logger = logging.getLogger(__name__)


class DataMigrateManager:
    """数据迁移管理器"""
    
    def __init__(self, reg: str = None, qlib_dir: str = None):
        self.reg = reg or config.default_reg
        self.qlib_dir = qlib_dir
        self.feature_storage = DuckDBFeatureStorage(self.reg)
        self.calendar_storage = DuckDBCalendarStorage(self.reg)
        self.instrument_storage = DuckDBInstrumentStorage(self.reg)
        
        if not self.qlib_dir:
            # 尝试从环境变量获取
            self.qlib_dir = os.environ.get("QLIB_DATA_DIR", "~/.qlib/qlib_data")
        self.qlib_dir = os.path.expanduser(self.qlib_dir)
    
    def _get_qlib_calendar(self, freq: str) -> List[str]:
        """从 Qlib 获取日历或从文件路径读取日历"""
        # 检查参数是否是文件路径
        if os.path.isfile(freq):
            # 如果是文件路径，直接读取
            calendar_path = freq
        else:
            # 如果是频率名称，构建路径
            calendar_path = os.path.join(self.qlib_dir, "calendars", f"{freq}.txt")
        
        if not os.path.exists(calendar_path):
            raise FileNotFoundError(f"Calendar file not found: {calendar_path}")
        
        with open(calendar_path, 'r') as f:
            calendar = [line.strip() for line in f if line.strip()]
        
        return calendar
    
    # 在 qlib_duckdb/managers/data_migrate.py 中修改 _get_qlib_instruments 方法
    def _get_qlib_instruments(self) -> pd.DataFrame:
        """获取 Qlib 标的数据"""
        try:
            qlib_dir = Path(self.qlib_dir)
            
            # 查找所有 instrument 文件
            instruments_dir = qlib_dir / "instruments"
            if not instruments_dir.exists():
                logger.warning(f"Instruments directory not found: {instruments_dir}")
                return pd.DataFrame()
            
            all_symbols = set()
            all_data = []
            
            # 处理所有 instrument 文件
            for inst_file in instruments_dir.glob("all.txt"):
                index_name = inst_file.stem
                logger.info(f"Reading instrument file: {inst_file}")
                
                try:
                    # 尝试读取文件
                    with open(inst_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                    
                    if not lines:
                        continue
                    
                    # 检查分隔符和列数
                    sample_line = lines[0].strip()
                    parts = sample_line.split('\t')
                    
                    if len(parts) == 1:
                        # 只有一列，只有 symbol
                        for line in lines:
                            symbol = line.strip()
                            if symbol:  # 跳过空行
                                all_symbols.add(symbol)
                                all_data.append({
                                    "symbol": symbol,
                                    "start_date": None,
                                    "end_date": None
                                })
                    
                    elif len(parts) >= 3:
                        # 有 symbol, start_date, end_date
                        for line in lines:
                            parts = line.strip().split('\t')
                            if len(parts) >= 3 and parts[0]:
                                symbol = parts[0]
                                start_date = parts[1] if len(parts) > 1 and parts[1] else None
                                end_date = parts[2] if len(parts) > 2 and parts[2] else None
                                
                                all_symbols.add(symbol)
                                all_data.append({
                                    "symbol": symbol,
                                    "start_date": start_date,
                                    "end_date": end_date
                                })
                    
                    else:
                        logger.warning(f"Unexpected format in {inst_file}: {sample_line}")
                        continue
                        
                except Exception as e:
                    logger.error(f"Error reading instrument file {inst_file}: {e}")
                    continue
            
            if not all_data:
                logger.warning("No instrument data found")
                return pd.DataFrame()
            
            # 创建 DataFrame
            df = pd.DataFrame(all_data)
            
            # 处理日期格式
            for col in ["start_date", "end_date"]:
                if col in df.columns:
                    # 尝试转换为日期
                    try:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                    except:
                        pass
            
            logger.info(f"Found {len(df)} instrument entries from {len(all_symbols)} unique symbols")
            return df
            
        except Exception as e:
            logger.error(f"Error getting Qlib instruments: {e}")
            return pd.DataFrame()
    def _get_qlib_instruments_del(self) -> pd.DataFrame:
        """从 Qlib 获取标的"""
        import qlib
        from qlib.data import D
        
        # 初始化 Qlib
        #if not qlib.initialized():
        #    qlib.init(provider_uri=self.qlib_dir)
        
        from core.qlibhelper import _check_qlib_init, get_state
        get_state().reg = "hk"
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        _check_qlib_init(bus)
        
        # 获取所有标的
        instruments = D.instruments(market="all")
        df_list = []
        
        for inst in tqdm(instruments, desc="Loading instruments"):
            try:
                # 获取标的的起止日期
                data = D.features([inst], ["$close"], freq="day")
                if not data.empty:
                    dates = data.index.get_level_values('datetime')
                    start_date = dates.min()
                    end_date = dates.max()
                    
                    df_list.append({
                        "symbol": inst,
                        "start_date": pd.Timestamp(start_date),
                        "end_date": pd.Timestamp(end_date)
                    })
            except Exception as e:
                logger.warning(f"Failed to get dates for {inst}: {e}")
                continue
        
        return pd.DataFrame(df_list)
    
    def _get_qlib_features(self, freq: str) -> pd.DataFrame:
        """从 Qlib 获取特征数据"""
        import qlib
        from qlib.data import D
        
        # 初始化 Qlib
        #if not qlib.initialized():
        #    qlib.init(provider_uri=self.qlib_dir)
        
        from core.qlibhelper import _check_qlib_init, get_state
        get_state().reg = "hk"
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        _check_qlib_init(bus)
        
        # 获取该频率的所有标的
        instruments = D.list_instruments(D.instruments(market="all"), freq=freq)
        
        all_data = []
        batch_size = 100
        
        for i in tqdm(range(0, len(instruments), batch_size), 
                     desc=f"Loading {freq} features"):
            batch = instruments[i:i + batch_size]
            
            try:
                # 获取数据
                data = D.features(
                    batch,
                    BASE_FIELDS,
                    freq=freq
                )
                
                if not data.empty:
                    # 重置索引以便处理
                    df = data.reset_index()
                    all_data.append(df)
                    
            except Exception as e:
                logger.warning(f"Failed to get features for batch {i}: {e}")
                continue
        
        if all_data:
            return pd.concat(all_data, ignore_index=True)
        return pd.DataFrame()
    
    def _validate_data(self, df: pd.DataFrame, freq: str) -> bool:
        """验证数据"""
        if df.empty:
            logger.warning(f"No data to validate for freq {freq}")
            return True
        
        # 检查必要字段
        required_cols = ["symbol", "datetime"] + BASE_FIELDS
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValidationError(f"Missing required columns: {missing_cols}")
        
        # 检查数据质量
        stats = {
            "total_rows": len(df),
            "unique_symbols": df["symbol"].nunique(),
            "date_range": f"{df['datetime'].min()} to {df['datetime'].max()}",
            "null_counts": df[BASE_FIELDS].isnull().sum().to_dict()
        }
        
        logger.info(f"Validation stats for {freq}: {stats}")
        return True
    
    def migrate_freq(self, freq: str, use_temp_table: bool = True) -> Dict[str, Any]:
        """迁移指定频率的数据"""
        logger.info(f"Starting migration for freq: {freq}")
        
        if 1 == 1:
        #try:
            # 1. 创建表结构
            SchemaManager.create_all_tables_for_freq(self.reg, freq)
            
            # 2. 迁移日历
            logger.info(f"Migrating calendar for {freq}")
            calendar = self._get_qlib_calendar(freq)
            if calendar:
                self.calendar_storage.write_calendar(calendar, freq, future=False)
                logger.info(f"Migrated {len(calendar)} calendar entries for {freq}")
            
            # 3. 迁移特征数据（使用临时表）
            logger.info(f"Migrating features for {freq}")
            temp_table = f"temp_feature_{freq}" if use_temp_table else f"feature_{freq}"
            
            with DuckDBConnection.get_connection(self.reg, read_only=False) as conn:
                # 创建临时表
                if use_temp_table:
                    create_sql = f"""
                    CREATE TEMPORARY TABLE {temp_table} AS 
                    SELECT * FROM feature_{freq} WHERE 1=0
                    """
                    conn.execute(create_sql, fetch=False)
                
                # 批量获取和插入数据
                features_df = self._get_qlib_features(freq)
                
                if not features_df.empty:
                    # 验证数据
                    self._validate_data(features_df, freq)
                    
                    # 批量插入
                    batch_size = config.migrate_batch_size
                    total_rows = len(features_df)
                    
                    for i in tqdm(range(0, total_rows, batch_size), 
                                desc=f"Inserting {freq} data"):
                        batch = features_df.iloc[i:i + batch_size]
                        records = batch.to_records(index=False)
                        
                        # 构建插入语句
                        columns = ["symbol", "datetime", "open", "high", "low", "close", "volume"]
                        placeholders = ", ".join(["?"] * len(columns))
                        
                        insert_sql = f"""
                        INSERT INTO {temp_table} ({', '.join(columns)})
                        VALUES ({placeholders})
                        """
                        
                        conn.connection.executemany(insert_sql, records)
                    
                    # 如果使用了临时表，复制到正式表
                    if use_temp_table:
                        conn.execute(f"""
                            INSERT OR REPLACE INTO feature_{freq}
                            SELECT * FROM {temp_table}
                        """, fetch=False)
                        
                        # 删除临时表
                        conn.execute(f"DROP TABLE {temp_table}", fetch=False)
                    
                    logger.info(f"Migrated {total_rows} rows for freq {freq}")
                else:
                    logger.warning(f"No feature data found for freq {freq}")
            
            # 4. 创建索引
            with DuckDBConnection.get_connection(self.reg, read_only=False) as conn:
                # 确保主键索引存在
                conn.execute(f"""
                    CREATE UNIQUE INDEX IF NOT EXISTS pk_feature_{freq} 
                    ON feature_{freq} (symbol, datetime)
                """, fetch=False)
                
                # 创建 datetime 索引
                conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS idx_datetime_{freq} 
                    ON feature_{freq} (datetime)
                """, fetch=False)
            
            logger.info(f"Successfully migrated freq {freq}")
            return {
                "freq": freq,
                "calendar_entries": len(calendar) if calendar else 0,
                "feature_rows": len(features_df) if not features_df.empty else 0,
                "status": "success"
            }
            
        #except Exception as e:
        #    logger.error(f"Failed to migrate freq {freq}: {e}")
            
        #    # 清理临时表
        #    if use_temp_table:
        #        try:
        #            with DuckDBConnection.get_connection(self.reg, read_only=False) as conn:
        #                conn.execute(f"DROP TABLE IF EXISTS temp_feature_{freq}", fetch=False)
        #        except:
        #            pass
            
        #    raise MigrationError(f"Migration failed for freq {freq}: {e}")
    
    def migrate_all_freqs(self, freqs: List[str] = None) -> Dict[str, Dict]:
        """迁移所有频率数据"""
        if freqs is None:
            freqs = SUPPORTED_FREQS
        
        results = {}
        
        # 1. 迁移标的
        logger.info("Migrating instruments")
        try:
            instruments_df = self._get_qlib_instruments()
            if not instruments_df.empty:
                self.instrument_storage.write_instruments(instruments_df)
                logger.info(f"Migrated {len(instruments_df)} instruments")
        except Exception as e:
            logger.error(f"Failed to migrate instruments: {e}")
        
        # 2. 迁移各频率数据
        for freq in tqdm(freqs, desc="Migrating frequencies"):
            try:
                result = self.migrate_freq(freq)
                results[freq] = result
            except Exception as e:
                logger.error(f"Failed to migrate {freq}: {e}")
                results[freq] = {"freq": freq, "status": "failed", "error": str(e)}
        
        # 3. 打印摘要
        self._print_migration_summary(results)
        return results
    
    def _print_migration_summary(self, results: Dict[str, Dict]):
        """打印迁移摘要"""
        logger.info("=" * 50)
        logger.info("Migration Summary")
        logger.info("=" * 50)
        
        success_count = 0
        fail_count = 0
        total_rows = 0
        
        for freq, result in results.items():
            if result.get("status") == "success":
                success_count += 1
                rows = result.get("feature_rows", 0)
                total_rows += rows
                logger.info(f"{freq:10s} | Success | {rows:>10,d} rows")
            else:
                fail_count += 1
                error = result.get("error", "Unknown error")
                logger.error(f"{freq:10s} | Failed  | {error}")
        
        logger.info("=" * 50)
        logger.info(f"Total: {success_count} succeeded, {fail_count} failed")
        logger.info(f"Total rows migrated: {total_rows:,d}")