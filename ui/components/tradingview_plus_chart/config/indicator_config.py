# config/indicator_config.py
from typing import Dict, List, Any
from enum import Enum

class IndicatorCategory(Enum):
    """指标分类"""
    MOVING_AVERAGES = "移动平均线"
    OSCILLATORS = "振荡指标"
    MOMENTUM = "动量指标"
    TREND = "趋势指标"
    VOLATILITY = "波动率"
    VOLUME = "成交量"
    CUSTOM = "自定义"

class IndicatorType(Enum):
    """指标类型"""
    LINE = "line"
    HISTOGRAM = "histogram"
    AREA = "area"
    BAR = "bar"

def get_common_indicators() -> Dict[str, Dict]:
    """获取常用指标配置（无需参数）"""
    return {
        "SMA_20": {
            "id": "SMA_20",
            "name": "SMA(20)",
            "description": "20日简单移动平均线",
            "category": IndicatorCategory.MOVING_AVERAGES.value,
            "type": IndicatorType.LINE.value,
            "chart": "main",  # 主图显示
            "default_parameters": {
                "length": 20,
                "source": "close",
                "color": "#2962FF"
            }
        },
        "SMA_50": {
            "id": "SMA_50",
            "name": "SMA(50)",
            "description": "50日简单移动平均线",
            "category": IndicatorCategory.MOVING_AVERAGES.value,
            "type": IndicatorType.LINE.value,
            "chart": "main",
            "default_parameters": {
                "length": 50,
                "source": "close",
                "color": "#FF6B6B"
            }
        },
        "EMA_12": {
            "id": "EMA_12",
            "name": "EMA(12)",
            "description": "12日指数移动平均线",
            "category": IndicatorCategory.MOVING_AVERAGES.value,
            "type": IndicatorType.LINE.value,
            "chart": "main",
            "default_parameters": {
                "length": 12,
                "source": "close",
                "color": "#4CAF50"
            }
        },
        "RSI": {
            "id": "RSI",
            "name": "RSI",
            "description": "相对强弱指数",
            "category": IndicatorCategory.OSCILLATORS.value,
            "type": IndicatorType.LINE.value,
            "chart": "sub",  # 副图显示
            "default_parameters": {
                "length": 14,
                "overbought": 70,
                "oversold": 30,
                "color": "#FF9800"
            }
        },
        "MACD": {
            "id": "MACD",
            "name": "MACD",
            "description": "指数平滑异同移动平均线",
            "category": IndicatorCategory.MOMENTUM.value,
            "type": IndicatorType.HISTOGRAM.value,
            "chart": "sub",
            "default_parameters": {
                "fast_length": 12,
                "slow_length": 26,
                "signal_length": 9,
                "color": "#2196F3"
            }
        },
        "Volume": {
            "id": "Volume",
            "name": "成交量",
            "description": "成交量柱状图",
            "category": IndicatorCategory.VOLUME.value,
            "type": IndicatorType.HISTOGRAM.value,
            "chart": "sub",
            "default_parameters": {
                "up_color": "#4CAF50",
                "down_color": "#F44336"
            }
        }
    }

def get_advanced_indicators() -> Dict[str, Dict]:
    """获取高级指标配置（需要参数）"""
    return {
        "BollingerBands": {
            "id": "BollingerBands",
            "name": "布林带",
            "description": "布林带指标，显示价格波动范围",
            "category": IndicatorCategory.VOLATILITY.value,
            "type": IndicatorType.LINE.value,
            "chart": "main",
            "parameters": {
                "length": {
                    "key": "length",
                    "name": "周期",
                    "type": "int",
                    "default": 20,
                    "min": 5,
                    "max": 200,
                    "required": True,
                    "description": "移动平均周期"
                },
                "std_dev": {
                    "key": "std_dev",
                    "name": "标准差倍数",
                    "type": "float",
                    "default": 2.0,
                    "min": 1.0,
                    "max": 5.0,
                    "step": 0.1,
                    "required": True,
                    "description": "标准差倍数，控制带宽"
                },
                "source": {
                    "key": "source",
                    "name": "数据源",
                    "type": "select",
                    "default": "close",
                    "options": [
                        {"label": "收盘价", "value": "close"},
                        {"label": "开盘价", "value": "open"},
                        {"label": "最高价", "value": "high"},
                        {"label": "最低价", "value": "low"}
                    ],
                    "required": True
                },
                "color": {
                    "key": "color",
                    "name": "颜色",
                    "type": "color",
                    "default": "#2962FF",
                    "required": False
                }
            }
        },
        "ATR": {
            "id": "ATR",
            "name": "平均真实波幅",
            "description": "衡量价格波动性的指标",
            "category": IndicatorCategory.VOLATILITY.value,
            "type": IndicatorType.LINE.value,
            "chart": "sub",
            "parameters": {
                "length": {
                    "key": "length",
                    "name": "周期",
                    "type": "int",
                    "default": 14,
                    "min": 1,
                    "max": 50,
                    "required": True
                },
                "smoothing": {
                    "key": "smoothing",
                    "name": "平滑类型",
                    "type": "select",
                    "default": "RMA",
                    "options": ["RMA", "SMA", "EMA", "WMA"],
                    "required": True
                }
            }
        },
        "IchimokuCloud": {
            "id": "IchimokuCloud",
            "name": "一目均衡表",
            "description": "日本技术分析指标，显示支撑阻力",
            "category": IndicatorCategory.TREND.value,
            "type": IndicatorType.LINE.value,
            "chart": "main",
            "parameters": {
                "tenkan_sen": {
                    "key": "tenkan_sen",
                    "name": "转换线周期",
                    "type": "int",
                    "default": 9,
                    "min": 1,
                    "max": 100,
                    "required": True
                },
                "kijun_sen": {
                    "key": "kijun_sen",
                    "name": "基准线周期",
                    "type": "int",
                    "default": 26,
                    "min": 1,
                    "max": 100,
                    "required": True
                },
                "senkou_span_b": {
                    "key": "senkou_span_b",
                    "name": "先行带B周期",
                    "type": "int",
                    "default": 52,
                    "min": 1,
                    "max": 200,
                    "required": True
                }
            }
        },
        "Stochastic": {
            "id": "Stochastic",
            "name": "随机指标",
            "description": "动量振荡器，显示超买超卖",
            "category": IndicatorCategory.OSCILLATORS.value,
            "type": IndicatorType.LINE.value,
            "chart": "sub",
            "parameters": {
                "k_period": {
                    "key": "k_period",
                    "name": "%K周期",
                    "type": "int",
                    "default": 14,
                    "min": 1,
                    "max": 50,
                    "required": True
                },
                "d_period": {
                    "key": "d_period",
                    "name": "%D周期",
                    "type": "int",
                    "default": 3,
                    "min": 1,
                    "max": 20,
                    "required": True
                },
                "slowing": {
                    "key": "slowing",
                    "name": "平滑周期",
                    "type": "int",
                    "default": 3,
                    "min": 1,
                    "max": 20,
                    "required": True
                }
            }
        }
    }