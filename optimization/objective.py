# optimization/objective.py
"""多目标优化函数 — 市场状态自适应权重"""
from __future__ import annotations

from typing import Optional
from loguru import logger

from backtesting.performance_metrics import BacktestMetrics


class ObjectiveFunction:
    """多目标优化评分，支持市场状态自适应"""

    DEFAULT_WEIGHTS = {
        "sharpe_ratio": 0.30,
        "max_drawdown": 0.25,
        "total_return": 0.20,
        "win_rate": 0.15,
        "profit_factor": 0.10,
    }

    REGIME_ADJUSTMENTS = {
        "expansion": {"total_return": 0.30, "sharpe_ratio": 0.25, "max_drawdown": 0.20},
        "recession": {"max_drawdown": 0.40, "sharpe_ratio": 0.30, "total_return": 0.10},
        "overheating": {"max_drawdown": 0.30, "sharpe_ratio": 0.30, "profit_factor": 0.20},
        "recovery": {"win_rate": 0.20, "sharpe_ratio": 0.30, "total_return": 0.25},
    }

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        market_regime: str = "expansion",
    ):
        self.base_weights = dict(weights or self.DEFAULT_WEIGHTS)
        self.market_regime = market_regime

    def get_adjusted_weights(self) -> dict[str, float]:
        """根据市场状态调整权重并归一化"""
        adjustments = self.REGIME_ADJUSTMENTS.get(self.market_regime, {})
        adjusted = dict(self.base_weights)
        for k, v in adjustments.items():
            if k in adjusted:
                adjusted[k] = v
        total = sum(adjusted.values())
        return {k: v / total for k, v in adjusted.items()} if total > 0 else adjusted

    def calculate(
        self,
        metrics,  # BacktestMetrics | dict
        enhanced: Optional[dict] = None,
    ) -> float:
        """计算综合得分 (0~1)。支持 BacktestMetrics 或 dict 输入。"""
        weights = self.get_adjusted_weights()
        enhanced = enhanced or {}

        # 支持 dict（来自子进程）或 BacktestMetrics
        if isinstance(metrics, dict):
            m = metrics
        else:
            m = {
                "sharpe_ratio": metrics.sharpe_ratio,
                "max_drawdown": metrics.max_drawdown,
                "total_return": metrics.total_return,
                "win_rate": metrics.win_rate,
            }

        scores = {
            "sharpe_ratio": self._norm_sharpe(m.get("sharpe_ratio")),
            "max_drawdown": self._norm_drawdown(m.get("max_drawdown")),
            "total_return": self._norm_return(m.get("total_return")),
            "win_rate": m.get("win_rate") or 0.0,
            "profit_factor": self._norm_pf(enhanced.get("profit_factor")),
        }
        total = sum(scores[k] * weights.get(k, 0) for k in scores)
        return round(float(total), 6)

    def negate(self, metrics, enhanced: Optional[dict] = None) -> float:
        return -self.calculate(metrics, enhanced)

    @staticmethod
    def _norm_sharpe(v) -> float:
        if v is None: return 0.0
        return min(max(float(v) / 2.0, 0.0), 1.0)

    @staticmethod
    def _norm_drawdown(v) -> float:
        if v is None: return 0.0
        return 1.0 - min(abs(float(v)) / 0.3, 1.0)

    @staticmethod
    def _norm_return(v) -> float:
        if v is None: return 0.0
        return min(max(float(v) / 0.5, 0.0), 1.0)

    @staticmethod
    def _norm_pf(v) -> float:
        if v is None: return 0.0
        if v == float("inf"): return 1.0
        return min(max(float(v) / 3.0, 0.0), 1.0)
