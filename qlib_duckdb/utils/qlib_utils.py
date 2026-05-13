"""
Qlib 数据结构交互工具
"""
import os
import pandas as pd
import numpy as np
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def convert_qlib_date(date_str: str) -> str:
    """转换 Qlib 日期格式为标准格式
    
    Qlib 使用 "YYYYMMDD" 格式，转换为 "YYYY-MM-DD"
    """
    if not date_str:
        return date_str
    
    # 如果已经是标准格式，直接返回
    if "-" in date_str:
        return date_str
    
    # 尝试不同格式
    try:
        # 格式: YYYYMMDD
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        
        # 格式: YYYY-MM-DD HH:MM:SS
        if " " in date_str and ":" in date_str:
            return date_str
        
        # 其他格式，尝试解析
        dt = pd.to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
        
    except Exception as e:
        logger.warning(f"Failed to parse date {date_str}: {e}")
        return date_str


def convert_to_qlib_date(date_str: str) -> str:
    """转换标准日期格式为 Qlib 格式
    
    标准格式转换为 "YYYYMMDD"
    """
    if not date_str:
        return date_str
    
    try:
        # 移除时间部分
        if " " in date_str:
            date_part = date_str.split(" ")[0]
        else:
            date_part = date_str
        
        # 移除分隔符
        date_part = date_part.replace("-", "").replace("/", "").replace(".", "")
        
        # 确保是8位
        if len(date_part) == 8 and date_part.isdigit():
            return date_part
        else:
            dt = pd.to_datetime(date_str)
            return dt.strftime("%Y%m%d")
            
    except Exception as e:
        logger.warning(f"Failed to convert to Qlib date {date_str}: {e}")
        return date_str


def parse_instruments_file(filepath: str) -> List[Tuple[str, Optional[str], Optional[str]]]:
    """解析 Qlib instruments 文件
    
    格式: symbol\tstart_date\tend_date
    """
    instruments = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            parts = line.split('\t')
            if len(parts) >= 1:
                symbol = parts[0].strip()
                start_date = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
                end_date = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
                
                # 转换日期格式
                if start_date:
                    start_date = convert_qlib_date(start_date)
                if end_date:
                    end_date = convert_qlib_date(end_date)
                
                instruments.append((symbol, start_date, end_date))
    
    return instruments


def parse_calendar_file(filepath: str) -> List[str]:
    """解析 Qlib calendar 文件"""
    calendar = []
    
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                calendar.append(line)
    
    return calendar


def get_qlib_data_dir() -> str:
    """获取 Qlib 数据目录"""
    # 1. 检查环境变量
    qlib_dir = os.environ.get("QLIB_DATA_DIR")
    if qlib_dir:
        return os.path.expanduser(qlib_dir)
    
    # 2. 默认路径
    default_dir = os.path.expanduser("~/.qlib/qlib_data")
    
    # 3. 检查是否存在
    if os.path.exists(default_dir):
        return default_dir
    
    # 4. 检查当前目录
    current_dir = "./qlib_data"
    if os.path.exists(current_dir):
        return os.path.abspath(current_dir)
    
    return default_dir


def get_qlib_freq_mapping() -> Dict[str, str]:
    """获取 Qlib 频率映射
    
    将标准频率映射到 Qlib 内部频率表示
    """
    return {
        "day": "1d",
        "week": "1w", 
        "3day": "3d",
        "1h": "1h",
        "4h": "4h",
        "2h": "2h",
        "6h": "6h", 
        "8h": "8h",
        "12h": "12h",
        "1m": "1m",
        "3m": "3m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "1s": "1s"
    }


def get_qlib_fields_mapping() -> Dict[str, str]:
    """获取 Qlib 字段映射
    
    将标准字段名映射到 Qlib 字段名
    """
    return {
        "open": "$open",
        "high": "$high", 
        "low": "$low",
        "close": "$close",
        "volume": "$volume",
        "vwap": "$vwap",
        "money": "$money",
        "factor": "$factor",
        "change": "$change",
        "pct_change": "$change_ratio"
    }


def convert_to_qlib_fields(fields: List[str]) -> List[str]:
    """转换字段名为 Qlib 格式"""
    mapping = get_qlib_fields_mapping()
    qlib_fields = []
    
    for field in fields:
        qlib_field = mapping.get(field, field)
        qlib_fields.append(qlib_field)
    
    return qlib_fields


def convert_from_qlib_fields(qlib_fields: List[str]) -> List[str]:
    """从 Qlib 字段名转换回标准字段名"""
    mapping = get_qlib_fields_mapping()
    # 创建反向映射
    reverse_mapping = {v: k for k, v in mapping.items()}
    
    standard_fields = []
    for qlib_field in qlib_fields:
        standard_field = reverse_mapping.get(qlib_field, qlib_field)
        standard_fields.append(standard_field)
    
    return standard_fields


def validate_qlib_data(data: pd.DataFrame, freq: str) -> bool:
    """验证 Qlib 数据格式"""
    if data.empty:
        return True
    
    # 检查索引格式
    if isinstance(data.index, pd.MultiIndex):
        # 检查索引层级
        if data.index.nlevels >= 2:
            # 应该包含 instrument 和 datetime
            level_names = data.index.names
            if "instrument" in str(level_names) and "datetime" in str(level_names):
                return True
    
    # 检查列名
    expected_columns = ["open", "high", "low", "close", "volume"]
    missing_columns = [col for col in expected_columns if col not in data.columns]
    
    if missing_columns:
        logger.warning(f"Missing expected columns: {missing_columns}")
    
    return True


def align_with_qlib_calendar(
    data: pd.DataFrame, 
    calendar: List[str], 
    freq: str
) -> pd.DataFrame:
    """将数据与 Qlib 日历对齐"""
    if data.empty or not calendar:
        return data
    
    # 确保 datetime 是索引
    if "datetime" in data.columns:
        data = data.set_index("datetime")
    
    # 创建完整的时间索引
    calendar_index = pd.DatetimeIndex(pd.to_datetime(calendar))
    
    # 重新索引
    aligned_data = data.reindex(calendar_index)
    
    return aligned_data


def calculate_missing_dates(
    data: pd.DataFrame,
    calendar: List[str],
    freq: str
) -> List[str]:
    """计算缺失的日期"""
    if data.empty or not calendar:
        return calendar if data.empty else []
    
    # 获取数据中的日期
    if "datetime" in data.columns:
        data_dates = set(pd.to_datetime(data["datetime"]).dt.strftime("%Y-%m-%d"))
    elif isinstance(data.index, pd.DatetimeIndex):
        data_dates = set(data.index.strftime("%Y-%m-%d"))
    else:
        logger.warning("Cannot extract dates from data")
        return []
    
    # 获取日历日期
    calendar_dates = set(pd.to_datetime(calendar).strftime("%Y-%m-%d"))
    
    # 计算缺失日期
    missing_dates = sorted(list(calendar_dates - data_dates))
    
    return missing_dates


def convert_qlib_bin_to_df(
    bin_dir: str,
    symbol: str,
    fields: List[str],
    start_time: str = None,
    end_time: str = None
) -> pd.DataFrame:
    """从 Qlib bin 文件读取数据并转换为 DataFrame
    
    注意: 这需要 Qlib 库支持
    """
    try:
        import qlib
        from qlib.data import D
        qlib.init(provider_uri=str("~/.qlib/data/hk_data"), region="cn")
        
        # 获取数据
        data = D.features(
            [symbol],
            convert_to_qlib_fields(fields),
            start_time=start_time,
            end_time=end_time
        )
        
        if data.empty:
            return pd.DataFrame()
        
        # 重置索引
        df = data.reset_index()
        
        # 重命名列
        df = df.rename(columns={"instrument": "symbol"})
        
        return df
        
    except ImportError:
        logger.error("Qlib is not installed. Cannot read bin files.")
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Failed to read Qlib bin data: {e}")
        return pd.DataFrame()


def compare_with_qlib(
    duckdb_data: pd.DataFrame,
    qlib_data: pd.DataFrame,
    tolerance: float = 1e-6
) -> Dict[str, Any]:
    """比较 DuckDB 数据和 Qlib 数据"""
    if duckdb_data.empty and qlib_data.empty:
        return {"status": "both_empty", "message": "Both datasets are empty"}
    
    if duckdb_data.empty:
        return {"status": "duckdb_empty", "message": "DuckDB data is empty"}
    
    if qlib_data.empty:
        return {"status": "qlib_empty", "message": "Qlib data is empty"}
    
    # 标准化数据
    if "datetime" in duckdb_data.columns:
        duckdb_data = duckdb_data.set_index("datetime")
    
    if "datetime" in qlib_data.columns:
        qlib_data = qlib_data.set_index("datetime")
    
    # 对齐索引
    common_index = duckdb_data.index.intersection(qlib_data.index)
    
    if len(common_index) == 0:
        return {"status": "no_common_dates", "message": "No common dates found"}
    
    # 比较数据
    results = {
        "status": "compared",
        "common_dates": len(common_index),
        "duckdb_only_dates": len(duckdb_data.index) - len(common_index),
        "qlib_only_dates": len(qlib_data.index) - len(common_index),
        "column_comparison": {},
        "max_abs_diff": 0,
        "mean_abs_diff": 0
    }
    
    # 比较每列
    common_columns = duckdb_data.columns.intersection(qlib_data.columns)
    
    for col in common_columns:
        duckdb_col = duckdb_data.loc[common_index, col]
        qlib_col = qlib_data.loc[common_index, col]
        
        # 计算差异
        diff = duckdb_col - qlib_col
        abs_diff = diff.abs()
        
        results["column_comparison"][col] = {
            "max_abs_diff": float(abs_diff.max()),
            "mean_abs_diff": float(abs_diff.mean()),
            "std_diff": float(diff.std()),
            "match_percentage": float((abs_diff <= tolerance).mean() * 100)
        }
        
        # 更新总体统计
        results["max_abs_diff"] = max(results["max_abs_diff"], float(abs_diff.max()))
        results["mean_abs_diff"] = max(results["mean_abs_diff"], float(abs_diff.mean()))
    
    return results