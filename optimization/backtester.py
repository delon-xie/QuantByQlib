# optimization/backtester.py
"""增强回测引擎 — 封装现有 BacktestEngine，增加止损和增强指标"""
from __future__ import annotations

from typing import Optional
import pandas as pd
import numpy as np
from loguru import logger

from backtesting.performance_metrics import BacktestMetrics, calc_metrics_from_returns


class EnhancedBacktester:
    """增强回测引擎：组合级止损 + Calmar/Sortino/ProfitFactor"""

    def __init__(
        self,
        initial_capital: float = 1_000_000.0,
        commission: float = 0.0015,
        slippage: float = 0.001,
        position_size: float = 0.1,
        stop_loss_config: Optional[dict] = None,
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.position_size = position_size
        self.stop_loss_config = stop_loss_config or {
            "fixed": 0.05,
            "trailing": True,
            "trailing_factor": 2.0,
            "time_based": 20,
        }

    def run_signal_backtest(
        self,
        topk_tickers: list[str],
        prices: pd.DataFrame,
        benchmark_prices: Optional[pd.Series] = None,
    ) -> dict:
        """
        对 Top-K 股票等权组合回测。

        Returns:
            {"metrics": BacktestMetrics, "enhanced": dict,
             "nav_series": Series, "bm_series": Series}
        """
        available = [t for t in topk_tickers if t in prices.columns]
        if not available or prices.empty:
            return self._empty_result()

        price_subset = prices[available].dropna(how="all")
        if price_subset.empty:
            return self._empty_result()

        daily_ret = price_subset.pct_change().dropna()
        portfolio_ret = daily_ret.mean(axis=1)

        # 组合级止损
        portfolio_ret = self._apply_stop_loss(portfolio_ret)

        nav_series = (1 + portfolio_ret).cumprod()

        bm_ret = None
        bm_series = pd.Series(dtype=float)
        if benchmark_prices is not None and not benchmark_prices.empty:
            bm_ret = benchmark_prices.pct_change().dropna()
            bm_series = (1 + bm_ret).cumprod()

        metrics = calc_metrics_from_returns(portfolio_ret, bm_ret)
        enhanced = self._calc_enhanced_metrics(portfolio_ret)

        return {
            "metrics": metrics,
            "enhanced": enhanced,
            "nav_series": nav_series,
            "bm_series": bm_series,
        }

    def _apply_stop_loss(self, daily_ret: pd.Series) -> pd.Series:
        """组合级止损：回撤超 threshold 后清零（模拟清仓）"""
        if daily_ret.empty:
            return daily_ret
        nav = (1 + daily_ret).cumprod()
        peak = nav.cummax()
        drawdown = (nav - peak) / peak
        stopped = drawdown <= -self.stop_loss_config["fixed"]
        if stopped.any():
            stop_idx = stopped[stopped].index[0]
            daily_ret = daily_ret.copy()
            daily_ret.loc[stop_idx:] = 0.0
            logger.debug(f"[EnhancedBacktester] 止损触发 {stop_idx.date()}")
        return daily_ret

    def _calc_enhanced_metrics(self, daily_ret: pd.Series) -> dict:
        """Calmar / Sortino / ProfitFactor"""
        if daily_ret.empty or len(daily_ret) < 5:
            return {}
        nav = (1 + daily_ret).cumprod()
        peak = nav.cummax()
        max_dd = float(((nav - peak) / peak).min())

        annual_ret = float(nav.iloc[-1] ** (252 / max(len(daily_ret), 1)) - 1)
        calmar = annual_ret / abs(max_dd) if max_dd != 0 else float("inf")

        downside = daily_ret[daily_ret < 0]
        dstd = float(downside.std()) if len(downside) > 0 else 0.0001
        mr = float(daily_ret.mean())
        sortino = mr / dstd * np.sqrt(252) if dstd > 0 else 0.0

        gp = daily_ret[daily_ret > 0].sum()
        gl = abs(daily_ret[daily_ret < 0].sum())
        pf = float(gp / gl) if gl > 0 else float("inf")

        return {
            "calmar_ratio": round(calmar, 4),
            "sortino_ratio": round(sortino, 4),
            "profit_factor": round(pf, 4),
        }

    def _empty_result(self) -> dict:
        return {
            "metrics": BacktestMetrics(),
            "enhanced": {},
            "nav_series": pd.Series(dtype=float),
            "bm_series": pd.Series(dtype=float),
        }
