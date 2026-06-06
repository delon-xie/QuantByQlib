# optimization/strategy_executor.py
"""策略执行引擎 — 策略工厂 + 信号生成"""
from __future__ import annotations

from typing import Optional
from loguru import logger

from strategies.base_strategy import BaseStrategy, StrategyResult


class StrategyExecutor:
    """策略工厂：根据 key 创建策略实例，参数由外部控制"""

    _STRATEGY_MAP = {
        "early_trend": (
            "strategies.screening.early_trend_screening",
            "EarlyTrendFormationStrategy",
        ),
        "golden_cross": (
            "strategies.screening.golden_cross_screening",
            "GoldenCrossMAStrategy",
        ),
        "ma10": (
            "strategies.screening.ma10_screening",
            "MA10TurnUpScreenStrategy",
        ),
        "trendline_breakout": (
            "strategies.screening.trendline_breakout_screening",
            "TrendlineBreakoutStrategy",
        ),
    }

    @classmethod
    def create_strategy(cls, strategy_key: str, **params) -> BaseStrategy:
        """
        Args:
            strategy_key: "early_trend"|"golden_cross"|"ma10"|"trendline_breakout"
            **params: 策略参数（与各策略 __init__ 参数名一致）
        Returns:
            BaseStrategy 实例
        """
        if strategy_key not in cls._STRATEGY_MAP:
            raise ValueError(
                f"未知策略: {strategy_key}，可选：{list(cls._STRATEGY_MAP)}"
            )

        module_path, class_name = cls._STRATEGY_MAP[strategy_key]
        import importlib
        module = importlib.import_module(module_path)
        strategy_class = getattr(module, class_name)
        return strategy_class(**params)

    @classmethod
    def run_strategy(
        cls,
        strategy_key: str,
        universe: list[str],
        params: Optional[dict] = None,
        progress_cb=None,
    ) -> StrategyResult:
        """创建策略并运行，返回 StrategyResult"""
        if params is None:
            params = {}
        strategy = cls.create_strategy(strategy_key, **params)
        return strategy.run(universe, progress_cb=progress_cb)

    @classmethod
    def list_strategies(cls) -> list[str]:
        return list(cls._STRATEGY_MAP)
