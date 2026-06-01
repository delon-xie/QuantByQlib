# indicators/moving_averages.py
import pandas as pd
import pandas_ta as ta
from typing import Dict, List, Any
from .base_indicator import BaseIndicator

class SimpleMovingAverage(BaseIndicator):
    """简单移动平均线"""
    
    def __init__(self, length: int = 20, source: str = 'close', **kwargs):
        super().__init__(**kwargs)
        self.length = length
        self.source = source
        
    def calculate(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """计算SMA指标"""
        if self.source not in df.columns:
            raise ValueError(f"数据中不存在列: {self.source}")
            
        sma_values = ta.sma(df[self.source], length=self.length)
        
        # 准备返回数据
        data = []
        for idx, (date, value) in enumerate(zip(df['date'], sma_values)):
            if pd.notna(value):
                data.append({
                    'time': str(date),
                    'value': float(value)
                })
                
        return data

class ExponentialMovingAverage(BaseIndicator):
    """指数移动平均线"""
    
    def __init__(self, length: int = 20, source: str = 'close', **kwargs):
        super().__init__(**kwargs)
        self.length = length
        self.source = source
        
    def calculate(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """计算EMA指标"""
        if self.source not in df.columns:
            raise ValueError(f"数据中不存在列: {self.source}")
            
        ema_values = ta.ema(df[self.source], length=self.length)
        
        data = []
        for idx, (date, value) in enumerate(zip(df['date'], ema_values)):
            if pd.notna(value):
                data.append({
                    'time': str(date),
                    'value': float(value)
                })
                
        return data