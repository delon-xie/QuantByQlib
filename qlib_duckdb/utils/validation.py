"""
数据验证工具
"""
import pandas as pd
import numpy as np
from typing import Dict, Any
from ..exceptions import ValidationError


def validate_price_data(df: pd.DataFrame) -> bool:
    """验证价格数据"""
    if df.empty:
        return True
    
    # 检查必要列
    required_cols = ["open", "high", "low", "close", "volume"]
    for col in required_cols:
        if col not in df.columns:
            raise ValidationError(f"Missing required column: {col}")
    
    errors = []
    
    # 检查价格合理性
    for idx, row in df.iterrows():
        # 高价 >= 低价
        if not (row['high'] >= row['low']):
            errors.append(f"Row {idx}: high ({row['high']}) < low ({row['low']})")
        
        # 收盘价在高低之间
        if not (row['high'] >= row['close'] >= row['low']):
            errors.append(f"Row {idx}: close ({row['close']}) not between high/low")
        
        # 开盘价在高低之间
        if not (row['high'] >= row['open'] >= row['low']):
            errors.append(f"Row {idx}: open ({row['open']}) not between high/low")
        
        # 价格为正数
        for col in ['open', 'high', 'low', 'close']:
            if row[col] <= 0:
                errors.append(f"Row {idx}: {col} ({row[col]}) <= 0")
        
        # 成交量为非负数
        if row['volume'] < 0:
            errors.append(f"Row {idx}: volume ({row['volume']}) < 0")
    
    if errors:
        raise ValidationError(f"Data validation failed: {errors[:5]}")  # 只显示前5个错误
    
    return True


def validate_calendar(calendar: list) -> bool:
    """验证日历"""
    if not calendar:
        return True
    
    # 检查是否按时间排序
    try:
        dates = [pd.Timestamp(dt) for dt in calendar]
        sorted_dates = sorted(dates)
        
        if dates != sorted_dates:
            raise ValidationError("Calendar is not sorted")
        
        # 检查重复
        if len(set(calendar)) != len(calendar):
            raise ValidationError("Duplicate dates in calendar")
        
    except Exception as e:
        raise ValidationError(f"Calendar validation failed: {e}")
    
    return True


def validate_instrument_df(df: pd.DataFrame) -> bool:
    """验证标的 DataFrame"""
    if df.empty:
        return True
    
    required_cols = ["symbol", "start_date", "end_date"]
    for col in required_cols:
        if col not in df.columns:
            raise ValidationError(f"Missing required column: {col}")
    
    # 检查起止日期合理性
    for idx, row in df.iterrows():
        if pd.notna(row['start_date']) and pd.notna(row['end_date']):
            if row['start_date'] > row['end_date']:
                raise ValidationError(f"Row {idx}: start_date > end_date")
    
    return True


def get_table_stats(reg: str, table_name: str) -> Dict[str, Any]:
    """获取表统计信息"""
    from ..duckdb_connection import get_connection
    
    with get_connection(reg, read_only=False) as conn:
        # 获取行数
        count_result = conn.execute(f"SELECT COUNT(*) FROM {table_name}")
        row_count = count_result[0][0] if count_result else 0
        
        # 获取时间范围
        time_result = conn.execute(f"""
            SELECT MIN(datetime), MAX(datetime) 
            FROM {table_name}
        """)
        
        if time_result and time_result[0][0]:
            min_time, max_time = time_result[0]
        else:
            min_time = max_time = None
        
        # 获取标的数
        symbol_result = conn.execute(f"SELECT COUNT(DISTINCT symbol) FROM {table_name}")
        symbol_count = symbol_result[0][0] if symbol_result else 0
        
        return {
            "table_name": table_name,
            "row_count": row_count,
            "min_time": min_time,
            "max_time": max_time,
            "symbol_count": symbol_count
        }