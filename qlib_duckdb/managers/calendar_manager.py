"""
日历管理器
CalendarManager 功能：
从文件导入日历
生成未来日历
日历合并
与 Qlib 原始日历同步
日历统计
导出日历文件

"""
import os
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
import logging
from tqdm import tqdm
from datetime import datetime, timedelta

from ..duckdb_connection import get_connection
from ..schema import SchemaManager
from ..storage.calendar import DuckDBCalendarStorage
from ..exceptions import MigrationError, ValidationError
from ..config import config
from ..utils.validation import validate_calendar

logger = logging.getLogger(__name__)


class CalendarManager:
    """日历管理器 - 处理日历数据的同步与管理"""
    
    def __init__(self, reg: str = None):
        self.reg = reg or config.default_reg
        self.calendar_storage = DuckDBCalendarStorage(self.reg)
    
    def _parse_calendar_file(self, filepath: str) -> List[str]:
        """解析日历文件"""
        calendar = []
        
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # 尝试解析日期时间
                try:
                    # 尝试不同格式
                    formats = [
                        "%Y-%m-%d %H:%M:%S",
                        "%Y-%m-%d %H:%M",
                        "%Y-%m-%d",
                        "%Y%m%d %H%M%S",
                        "%Y%m%d"
                    ]
                    
                    dt = None
                    for fmt in formats:
                        try:
                            dt = datetime.strptime(line, fmt)
                            break
                        except ValueError:
                            continue
                    
                    if dt is None:
                        logger.warning(f"Invalid date format in line {line_num}: {line}")
                        continue
                    
                    # 标准化格式
                    if ":" in line:  # 包含时间的格式
                        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:  # 只包含日期的格式
                        dt_str = dt.strftime("%Y-%m-%d")
                    
                    calendar.append(dt_str)
                    
                except Exception as e:
                    logger.warning(f"Failed to parse line {line_num}: {line} - {e}")
        
        logger.info(f"Parsed calendar file {filepath}: {len(calendar)} entries")
        return calendar
    
    def import_calendar_from_file(
        self, 
        filepath: str, 
        freq: str,
        future: bool = False,
        on_conflict: str = "replace"
    ) -> Dict[str, Any]:
        """从文件导入日历"""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Calendar file not found: {filepath}")
        
        try:
            # 1. 解析文件
            calendar = self._parse_calendar_file(filepath)
            
            if not calendar:
                logger.warning(f"No valid calendar entries found in {filepath}")
                return {"freq": freq, "future": future, "entries_imported": 0}
            
            # 2. 验证数据
            validate_calendar(calendar)
            
            # 3. 确保表存在
            SchemaManager.create_calendar_table(self.reg, freq, future)
            
            # 4. 写入数据库
            entries_imported = self.calendar_storage.write_calendar(
                calendar, freq, future, on_conflict
            )
            
            logger.info(f"Imported calendar for {freq} (future={future}): {entries_imported} entries")
            
            return {
                "freq": freq,
                "future": future,
                "file": Path(filepath).name,
                "entries_imported": entries_imported,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"Failed to import calendar from {filepath}: {e}")
            raise MigrationError(f"Failed to import calendar: {e}")
    
    def import_calendars_from_directory(
        self, 
        directory: str,
        freq: str = None,
        future: bool = False,
        on_conflict: str = "replace"
    ) -> Dict[str, Dict[str, Any]]:
        """从目录批量导入日历"""
        if not os.path.exists(directory):
            raise FileNotFoundError(f"Directory not found: {directory}")
        
        results = {}
        
        # 确定要导入的文件
        if freq:
            # 导入指定频率的文件
            filename = f"{freq}{'_future' if future else ''}.txt"
            filepath = os.path.join(directory, filename)
            
            if os.path.exists(filepath):
                try:
                    result = self.import_calendar_from_file(
                        filepath, freq, future, on_conflict
                    )
                    results[filename] = result
                except Exception as e:
                    logger.error(f"Failed to import {filename}: {e}")
                    results[filename] = {
                        "freq": freq,
                        "future": future,
                        "status": "failed",
                        "error": str(e)
                    }
            else:
                logger.warning(f"Calendar file not found: {filepath}")
        else:
            # 导入目录下所有日历文件
            txt_files = list(Path(directory).glob("*.txt"))
            
            if not txt_files:
                logger.warning(f"No .txt files found in {directory}")
                return results
            
            logger.info(f"Found {len(txt_files)} calendar files in {directory}")
            
            for filepath in tqdm(txt_files, desc="Importing calendars"):
                try:
                    # 从文件名解析频率和future标志
                    filename = filepath.stem
                    future_flag = False
                    
                    if filename.endswith("_future"):
                        freq_name = filename[:-7]  # 去掉"_future"
                        future_flag = True
                    else:
                        freq_name = filename
                    
                    result = self.import_calendar_from_file(
                        str(filepath), freq_name, future_flag, on_conflict
                    )
                    results[filepath.name] = result
                    
                except Exception as e:
                    logger.error(f"Failed to import {filepath.name}: {e}")
                    results[filepath.name] = {
                        "freq": freq_name if 'freq_name' in locals() else "unknown",
                        "future": future_flag if 'future_flag' in locals() else False,
                        "status": "failed",
                        "error": str(e)
                    }
        
        # 打印摘要
        self._print_import_summary(results)
        return results
    
    def _print_import_summary(self, results: Dict[str, Dict[str, Any]]):
        """打印导入摘要"""
        logger.info("=" * 50)
        logger.info("Calendar Import Summary")
        logger.info("=" * 50)
        
        success_count = 0
        fail_count = 0
        total_entries = 0
        
        for filename, result in results.items():
            if result.get("status") == "success":
                success_count += 1
                entries = result.get("entries_imported", 0)
                total_entries += entries
                freq = result.get("freq", "unknown")
                future = "(future)" if result.get("future") else ""
                logger.info(f"{filename:<30} | Success | {entries:>8,d} entries {freq} {future}")
            else:
                fail_count += 1
                error = result.get("error", "Unknown error")
                logger.error(f"{filename:<30} | Failed  | {error}")
        
        logger.info("=" * 50)
        logger.info(f"Total: {success_count} succeeded, {fail_count} failed")
        logger.info(f"Total calendar entries imported: {total_entries:,d}")
    
    def sync_from_qlib(self, qlib_dir: str = None) -> Dict[str, Any]:
        """从 Qlib 原始 calendars 目录同步日历"""
        if qlib_dir is None:
            qlib_dir = os.environ.get("QLIB_DATA_DIR", f"~/.qlib/qlib_data/{self.reg}_data")
        qlib_dir = os.path.expanduser(qlib_dir)
        
        calendars_dir = os.path.join(qlib_dir, "calendars")
        if not os.path.exists(calendars_dir):
            logger.warning(f"Qlib calendars directory not found: {calendars_dir}")
            return {"status": "skipped", "reason": "Directory not found"}
        
        # 导入所有日历文件
        results = self.import_calendars_from_directory(
            calendars_dir,
            freq=None,  # None 表示导入所有
            on_conflict="replace"
        )
        
        return {
            "status": "completed",
            "results": results,
            "source_dir": calendars_dir
        }
    
    def get_calendar(
        self, 
        freq: str, 
        future: bool = False,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[str]:
        """获取日历"""
        return self.calendar_storage.get_calendar(freq, future, start_date, end_date)
    
    def get_all_calendar(self, freq: str) -> List[str]:
        """获取所有日历（历史+未来）"""
        return self.calendar_storage.get_all_calendar(freq)
    
    def generate_future_calendar(
        self, 
        freq: str, 
        days: int = 365,
        start_date: Optional[str] = None
    ) -> List[str]:
        """生成未来日历"""
        from dateutil.rrule import rrule, DAILY, HOURLY, MINUTELY
        from dateutil.relativedelta import relativedelta
        
        # 获取历史日历的最后日期
        history_calendar = self.get_calendar(freq, future=False)
        
        if not history_calendar and not start_date:
            raise ValueError(f"No historical calendar for {freq} and no start_date provided")
        
        if start_date:
            start_dt = pd.Timestamp(start_date)
        else:
            # 使用历史日历的最后日期
            last_date = pd.Timestamp(history_calendar[-1])
            start_dt = last_date + timedelta(days=1)
        
        # 根据频率确定规则
        if freq == "day":
            rule = DAILY
            interval = 1
            end_dt = start_dt + relativedelta(days=days)
        elif freq == "1h":
            rule = HOURLY
            interval = 1
            end_dt = start_dt + relativedelta(days=days)
        elif freq == "5m":
            rule = MINUTELY
            interval = 5
            end_dt = start_dt + relativedelta(days=days)
        elif freq == "15m":
            rule = MINUTELY
            interval = 15
            end_dt = start_dt + relativedelta(days=days)
        elif freq == "30m":
            rule = MINUTELY
            interval = 30
            end_dt = start_dt + relativedelta(days=days)
        elif freq == "1m":
            rule = MINUTELY
            interval = 1
            end_dt = start_dt + relativedelta(days=days)
        else:
            # 默认为日线
            rule = DAILY
            interval = 1
            end_dt = start_dt + relativedelta(days=days)
        
        # 生成日期序列
        dates = list(rrule(
            rule,
            interval=interval,
            dtstart=start_dt,
            until=end_dt
        ))
        
        # 过滤工作日（如果是日线）
        if freq == "day":
            from pandas.tseries.offsets import BDay
            business_days = pd.date_range(start=start_dt, end=end_dt, freq=BDay())
            dates = [d for d in dates if d in business_days]
        
        # 转换为字符串
        future_calendar = []
        for dt in dates:
            if freq == "day":
                dt_str = dt.strftime("%Y-%m-%d")
            else:
                dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            future_calendar.append(dt_str)
        
        logger.info(f"Generated {len(future_calendar)} future calendar entries for {freq}")
        return future_calendar
    
    def update_future_calendar(
        self, 
        freq: str, 
        days: int = 365,
        on_conflict: str = "replace"
    ) -> int:
        """更新未来日历"""
        try:
            # 生成未来日历
            future_calendar = self.generate_future_calendar(freq, days)
            
            if not future_calendar:
                logger.warning(f"No future calendar generated for {freq}")
                return 0
            
            # 写入数据库
            entries_imported = self.calendar_storage.write_calendar(
                future_calendar, freq, future=True, on_conflict=on_conflict
            )
            
            logger.info(f"Updated future calendar for {freq}: {entries_imported} entries")
            return entries_imported
            
        except Exception as e:
            logger.error(f"Failed to update future calendar for {freq}: {e}")
            raise
    
    def export_calendar_to_file(
        self, 
        freq: str, 
        future: bool = False,
        output_dir: str = None
    ) -> str:
        """导出日历到文件"""
        if output_dir is None:
            output_dir = "./calendars"
        os.makedirs(output_dir, exist_ok=True)
        
        filename = f"{freq}{'_future' if future else ''}.txt"
        output_path = os.path.join(output_dir, filename)
        
        # 获取日历
        calendar = self.get_calendar(freq, future)
        
        if not calendar:
            logger.warning(f"No calendar found for {freq} (future={future})")
            return ""
        
        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            for dt_str in calendar:
                f.write(f"{dt_str}\n")
        
        logger.info(f"Exported calendar to {output_path}: {len(calendar)} entries")
        return output_path
    
    def merge_calendars(
        self, 
        freq: str, 
        calendars: List[List[str]],
        on_conflict: str = "replace"
    ) -> int:
        """合并多个日历"""
        # 合并并去重
        all_dates = set()
        for cal in calendars:
            all_dates.update(cal)
        
        sorted_dates = sorted(list(all_dates))
        
        # 写入数据库
        entries_imported = self.calendar_storage.write_calendar(
            sorted_dates, freq, future=False, on_conflict=on_conflict
        )
        
        logger.info(f"Merged calendars for {freq}: {entries_imported} unique entries")
        return entries_imported
    
    def get_calendar_stats(self, freq: str) -> Dict[str, Any]:
        """获取日历统计信息"""
        with get_connection(self.reg, read_only=False) as conn:
            # 历史日历统计
            history_result = conn.execute(f"""
                SELECT COUNT(*), MIN(datetime), MAX(datetime)
                FROM calendar_{freq}
            """)
            
            # 未来日历统计
            future_result = conn.execute(f"""
                SELECT COUNT(*), MIN(datetime), MAX(datetime)
                FROM calendar_{freq}_future
            """)
        
        stats = {
            "freq": freq,
            "history": {
                "count": history_result[0][0] if history_result and history_result[0][0] else 0,
                "min_date": history_result[0][1] if history_result and history_result[0][1] else None,
                "max_date": history_result[0][2] if history_result and history_result[0][2] else None
            },
            "future": {
                "count": future_result[0][0] if future_result and future_result[0][0] else 0,
                "min_date": future_result[0][1] if future_result and future_result[0][1] else None,
                "max_date": future_result[0][2] if future_result and future_result[0][2] else None
            }
        }
        
        return stats