# indicators/base_indicator.py
from abc import ABC, abstractmethod
from typing import Dict, List, Any
import pandas as pd

class BaseIndicator(ABC):
    """指标基类"""
    
    def __init__(self, **kwargs):
        self.options = kwargs
        
    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """计算指标 - 子类必须实现此方法"""
        pass
        
    def validate_data(self, df: pd.DataFrame, required_cols: List[str]) -> None:
        """验证数据"""
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"数据缺少必需的列: {missing_cols}")
            
    def get_indicator_type(self) -> str:
        """获取指标类型"""
        return self.options.get('type', 'line')
        
    def get_indicator_color(self) -> str:
        """获取指标颜色"""
        return self.options.get('color', '#2196F3')
        
    def is_visible(self) -> bool:
        """是否可见"""
        return self.options.get('visible', True)