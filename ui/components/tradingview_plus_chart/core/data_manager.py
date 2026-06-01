# core/data_manager.py
import pandas as pd
import json
from typing import Dict, List, Optional, Any
import numpy as np

class DataManager:
    """数据管理器 - 处理数据的标准化、转换和验证"""
    
    def __init__(self):
        self.original_df: Optional[pd.DataFrame] = None
        self.standardized_df: Optional[pd.DataFrame] = None
        self.chart_data: List[Dict] = []
        
    def set_data(self, df: pd.DataFrame) -> None:
        """设置原始数据并进行标准化"""
        self.original_df = df.copy()
        self._standardize_columns()
        self._prepare_chart_data()
        
    def _standardize_columns(self) -> None:
        """标准化列名映射"""
        if self.original_df is None:
            return
            
        col_mapping = {}
        df_cols = [c.lower() for c in self.original_df.columns]
        
        # 查找日期列
        date_col = None
        for col in ['date', 'datetime', 'time', 'timestamp']:
            if col in df_cols:
                date_col = col
                break
                
        if date_col:
            col_mapping[date_col] = 'date'
            
        # 查找价格和成交量列
        price_mappings = {
            'open': ['open'],
            'high': ['high'],
            'low': ['low'],
            'close': ['close'],
            'volume': ['volume', 'vol']
        }
        
        for target, possible_names in price_mappings.items():
            for name in possible_names:
                for col in df_cols:
                    if name in col:
                        col_mapping[col] = target
                        break
                if target in col_mapping.values():
                    break
                    
        # 重命名列
        self.standardized_df = self.original_df.rename(columns=col_mapping)
        
    def _prepare_chart_data(self) -> None:
        """准备图表数据格式"""
        if self.standardized_df is None:
            return
            
        self.chart_data = []
        required_cols = ['date', 'open', 'high', 'low', 'close']
        
        # 确保所有必需列都存在
        for col in required_cols:
            if col not in self.standardized_df.columns:
                raise ValueError(f"缺少必需列: {col}")
                
        for _, row in self.standardized_df.iterrows():
            candle = {
                'time': str(row['date']),
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close'])
            }
            
            if 'volume' in self.standardized_df.columns:
                candle['volume'] = float(row['volume'])
            else:
                candle['volume'] = 0.0
                
            self.chart_data.append(candle)
            
    def get_chart_data_json(self) -> str:
        """获取图表数据的JSON格式"""
        return json.dumps(self.chart_data)
        
    def get_original_df(self) -> Optional[pd.DataFrame]:
        """获取原始数据"""
        return self.original_df