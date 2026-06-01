# core/indicator_manager.py
from typing import Dict, List, Optional, Any, Callable
import pandas as pd
import json
from datetime import datetime
import importlib

class IndicatorManager:
    """指标管理器 - 管理技术指标的计算和状态"""
    
    def __init__(self, widget):
        self.widget = widget
        self.active_indicators: Dict[str, Dict] = {}
        self.indicator_handlers = self._init_indicator_handlers()
        
    def _init_indicator_handlers(self) -> Dict[str, Callable]:
        """初始化指标处理器映射"""
        return {
            # 移动平均线
            'SMA': self._create_sma_handler(20),
            'SMA_5': self._create_sma_handler(5),
            'SMA_10': self._create_sma_handler(10),
            'SMA_20': self._create_sma_handler(20),
            'EMA': self._create_ema_handler(20),
            'EMA_12': self._create_ema_handler(12),
            'EMA_26': self._create_ema_handler(26),
            
            # 振荡指标
            'RSI': lambda df, options: self._calculate_rsi(df, options),
            'MACD': lambda df, options: self._calculate_macd(df, options),
            
            # 趋势指标
            'BollingerBands': lambda df, options: self._calculate_bollinger_bands(df, options),
            
            # 自定义指标
            'PROFILE': lambda df, options: self._calculate_yearly_profile(df, options),
        }
        
    def _create_sma_handler(self, length: int):
        """创建SMA处理器"""
        def handler(df: pd.DataFrame, options: Dict) -> str:
            from indicators.moving_averages import SimpleMovingAverage
            sma = SimpleMovingAverage(length=length)
            data = sma.calculate(df, **options)
            return json.dumps(data)
        return handler
        
    def _create_ema_handler(self, length: int):
        """创建EMA处理器"""
        def handler(df: pd.DataFrame, options: Dict) -> str:
            from indicators.moving_averages import ExponentialMovingAverage
            ema = ExponentialMovingAverage(length=length)
            data = ema.calculate(df, **options)
            return json.dumps(data)
        return handler
        
    def add_indicator(self, indicator_name: str, options: Dict) -> None:
        """添加指标"""
        if indicator_name not in self.indicator_handlers:
            raise ValueError(f"不支持的指标: {indicator_name}")
            
        # 获取数据
        data_manager = self.widget.data_manager
        df = data_manager.get_original_df()
        
        if df is None:
            raise ValueError("没有可用数据，请先设置图表数据")
            
        # 计算指标
        handler = self.indicator_handlers[indicator_name]
        data_json = handler(df, options)
        
        # 发送到JavaScript
        self.widget.bridge_manager.send_indicator_to_js(indicator_name, data_json, options)
        
        # 记录活跃指标
        self.active_indicators[indicator_name] = {
            'timestamp': datetime.now(),
            'options': options
        }
        
    def remove_indicator(self, indicator_name: str) -> None:
        """移除指标"""
        if indicator_name in self.active_indicators:
            del self.active_indicators[indicator_name]
            self.widget.bridge_manager.remove_indicator_from_js(indicator_name)
            
    def clear_all_indicators(self) -> None:
        """清除所有指标"""
        self.active_indicators.clear()
        self.widget.bridge_manager.clear_all_indicators_from_js()
        
    def _calculate_rsi(self, df: pd.DataFrame, options: Dict) -> List[Dict]:
        """计算RSI指标"""
        from indicators.oscillators import RelativeStrengthIndex
        rsi = RelativeStrengthIndex(**options)
        return rsi.calculate(df)
        
    def _calculate_macd(self, df: pd.DataFrame, options: Dict) -> Dict[str, List]:
        """计算MACD指标"""
        from indicators.momentum import MovingAverageConvergenceDivergence
        macd = MovingAverageConvergenceDivergence(**options)
        return macd.calculate(df)
        
    def _calculate_bollinger_bands(self, df: pd.DataFrame, options: Dict) -> Dict[str, List]:
        """计算布林带"""
        from indicators.volatility import BollingerBands
        bb = BollingerBands(**options)
        return bb.calculate(df)
        
    def _calculate_yearly_profile(self, df: pd.DataFrame, options: Dict) -> List[Dict]:
        """计算年度成交量分布"""
        from indicators.volume import YearlyVolumeProfile
        profile = YearlyVolumeProfile(**options)
        return profile.calculate(df)