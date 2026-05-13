"""
导出为 Qlib bin 格式
"""
import os
import shutil
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict
import logging
from tqdm import tqdm

from ..duckdb_connection import get_connection
from ..constants import SUPPORTED_FREQS
from ..config import config

logger = logging.getLogger(__name__)


class BinExportManager:
    """导出为 Qlib bin 格式管理器"""
    
    def __init__(self, reg: str = None, output_dir: str = None):
        self.reg = reg or config.default_reg
        self.output_dir = output_dir or f"./qlib_{self.reg}"
        
        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
    
    def export_freq_to_csv(self, freq: str, csv_dir: str = None) -> str:
        """导出指定频率数据到 CSV"""
        if csv_dir is None:
            csv_dir = os.path.join(self.output_dir, "csv", freq)
        os.makedirs(csv_dir, exist_ok=True)
        
        table_name = f"feature_{freq}"
        
        with get_connection(self.reg, read_only=False) as conn:
            # 获取所有标的
            symbols_result = conn.execute(
                f"SELECT DISTINCT symbol FROM {table_name} ORDER BY symbol"
            )
            symbols = [row[0] for row in symbols_result] if symbols_result else []
        
        if not symbols:
            logger.warning(f"No symbols found for freq {freq}")
            return csv_dir
        
        # 为每个标的导出 CSV
        for symbol in tqdm(symbols, desc=f"Exporting {freq} to CSV"):
            csv_path = os.path.join(csv_dir, f"{symbol.lower()}.csv")
            
            with get_connection(self.reg, read_only=False) as conn:
                # 查询数据
                data = conn.execute(f"""
                    SELECT datetime, open, high, low, close, volume
                    FROM {table_name}
                    WHERE symbol = ?
                    ORDER BY datetime
                """, (symbol,))
            
            if data:
                # 转换为 DataFrame
                df = pd.DataFrame(data, columns=["datetime", "open", "high", "low", "close", "volume"])
                
                # 转换日期格式
                df["date"] = pd.to_datetime(df["datetime"]).dt.strftime("%Y-%m-%d")
                df["time"] = pd.to_datetime(df["datetime"]).dt.strftime("%H:%M:%S")
                
                # 重新排列列
                df = df[["date", "time", "open", "high", "low", "close", "volume"]]
                
                # 保存为 CSV
                df.to_csv(csv_path, index=False)
        
        logger.info(f"Exported {len(symbols)} symbols for freq {freq} to {csv_dir}")
        return csv_dir
    
    def export_calendar(self, freq: str, output_dir: str = None) -> str:
        """导出日历"""
        if output_dir is None:
            output_dir = os.path.join(self.output_dir, "calendars")
        os.makedirs(output_dir, exist_ok=True)
        
        calendar_path = os.path.join(output_dir, f"{freq}.txt")
        
        with get_connection(self.reg, read_only=False) as conn:
            # 查询日历
            data = conn.execute(f"""
                SELECT datetime 
                FROM calendar_{freq} 
                ORDER BY datetime
            """)
        
        if data:
            # 写入文件
            with open(calendar_path, 'w') as f:
                for row in data:
                    dt_str = row[0].strftime("%Y-%m-%d")
                    if freq != "day":
                        dt_str = row[0].strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"{dt_str}\n")
            
            logger.info(f"Exported calendar for {freq}: {len(data)} entries")
        
        return calendar_path
    
    def export_instruments(self, output_dir: str = None) -> str:
        """导出标的"""
        if output_dir is None:
            output_dir = os.path.join(self.output_dir, "instruments")
        os.makedirs(output_dir, exist_ok=True)
        
        with get_connection(self.reg, read_only=False) as conn:
            # 获取所有标的
            instruments = conn.execute("""
                SELECT symbol, start_date, end_date 
                FROM instrument 
                ORDER BY symbol
            """)
        
        if instruments:
            # 按市场分组（简单按前缀判断）
            instruments_by_market = {}
            
            for symbol, start_date, end_date in instruments:
                # 简单判断市场
                if symbol.startswith(("SH", "SZ", "BJ")):
                    market = "cn"
                elif symbol.startswith(("US", )):
                    market = "us"
                elif symbol.startswith(("HK", )):
                    market = "hk"
                elif symbol.startswith(("TW", )):
                    market = "tw"
                elif symbol.startswith(("JP", )):
                    market = "jp"
                elif symbol.startswith(("KR", )):
                    market = "kr"
                else:
                    market = "other"
                
                if market not in instruments_by_market:
                    instruments_by_market[market] = []
                
                instruments_by_market[market].append(symbol)
            
            # 写入文件
            for market, symbols in instruments_by_market.items():
                market_path = os.path.join(output_dir, f"{market}.txt")
                with open(market_path, 'w') as f:
                    for symbol in symbols:
                        f.write(f"{symbol}\n")
                
                logger.info(f"Exported {len(symbols)} instruments for market {market}")
        
        return output_dir
    
    def export_to_qlib_bin(self, freq: str, dump_all: bool = True) -> Dict[str, str]:
        """导出为 Qlib bin 格式"""
        try:
            from qlib.scripts.dump_bin import DumpDataAll
        except ImportError:
            raise ImportError("Qlib is required for bin export. Install with: pip install pyqlib")
        
        # 1. 导出到 CSV
        csv_dir = self.export_freq_to_csv(freq)
        
        # 2. 导出日历
        calendar_dir = os.path.dirname(self.export_calendar(freq))
        
        # 3. 导出标的
        instrument_dir = self.export_instruments()
        
        # 4. 准备 Qlib 目录结构
        qlib_dir = os.path.join(self.output_dir, f"qlib_bin_{freq}")
        
        if os.path.exists(qlib_dir):
            shutil.rmtree(qlib_dir)
        
        os.makedirs(qlib_dir)
        
        # 5. 使用 Qlib 的 dump_bin
        dumper = DumpDataAll(
            csv_path=csv_dir,
            qlib_dir=qlib_dir,
            freq=freq,
            exclude_fields="date,symbol",
        )
        
        if dump_all:
            dumper.dump()
        else:
            dumper.dump_all()
        
        logger.info(f"Successfully exported {freq} data to Qlib bin format at {qlib_dir}")
        
        return {
            "csv_dir": csv_dir,
            "calendar_dir": calendar_dir,
            "instrument_dir": instrument_dir,
            "qlib_dir": qlib_dir
        }
    
    def export_all_freqs(self, freqs: List[str] = None) -> Dict[str, Dict[str, str]]:
        """导出所有频率"""
        if freqs is None:
            freqs = SUPPORTED_FREQS
        
        results = {}
        
        for freq in tqdm(freqs, desc="Exporting frequencies"):
            try:
                result = self.export_to_qlib_bin(freq)
                results[freq] = result
                logger.info(f"Successfully exported {freq}")
            except Exception as e:
                logger.error(f"Failed to export {freq}: {e}")
                results[freq] = {"error": str(e)}
        
        return results