# optimization/walkforward.py
"""Walk-Forward 分析 — 滚动窗口训练/测试验证参数稳健性"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from optimization.config import OptimizationConfig
from optimization.optimizer import GridSearchOptimizer
from optimization.backtester import EnhancedBacktester
from optimization.objective import ObjectiveFunction
from optimization.strategy_executor import StrategyExecutor


class WalkForwardAnalyzer:
    """Walk-Forward 滚动窗口分析"""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.grid_optimizer = GridSearchOptimizer(config)
        self.backtester = EnhancedBacktester(
            initial_capital=config.initial_capital,
            stop_loss_config={"fixed": config.stop_loss_pct},
        )

    def analyze(
        self,
        prices: pd.DataFrame,
        universe: list[str],
        market_regime: str = "expansion",
        progress_cb=None,
    ) -> dict:
        """执行 Walk-Forward，返回窗口结果和统计"""
        dates = prices.index
        tw = self.config.wf_train_window
        tsw = self.config.wf_test_window
        step = self.config.wf_step

        windows = []
        i = 0

        while i + tw + tsw <= len(dates):
            train_start = dates[i]
            train_end = dates[i + tw - 1]
            test_start = dates[i + tw]
            test_end = dates[i + tw + tsw - 1]

            train_data = prices.loc[train_start:train_end]
            test_data = prices.loc[test_start:test_end]

            if progress_cb:
                pct = int(i / len(dates) * 90)
                progress_cb(pct, f"Walk-Forward 窗口 {len(windows)+1}...")

            try:
                grid_result = self.grid_optimizer.search(
                    train_data, universe, market_regime
                )
                best_params = grid_result["best_params"]
                bt_result = self.backtester.run_signal_backtest(
                    self._get_topk(best_params, universe), test_data
                )
                obj_fn = ObjectiveFunction(market_regime=market_regime)
                ts = obj_fn.calculate(bt_result["metrics"], bt_result.get("enhanced"))

                windows.append({
                    "train_period": (str(train_start.date()), str(train_end.date())),
                    "test_period": (str(test_start.date()), str(test_end.date())),
                    "best_params": best_params,
                    "train_score": grid_result["best_score"],
                    "test_score": ts,
                    "test_sharpe": bt_result["metrics"].sharpe_ratio,
                })
            except Exception as e:
                logger.warning(f"[WalkForward] 窗口失败：{e}")

            i += step

        if not windows:
            raise RuntimeError("Walk-Forward 无有效窗口")

        train_scores = [w["train_score"] for w in windows]
        test_scores = [w["test_score"] for w in windows]

        return {
            "windows": windows,
            "n_windows": len(windows),
            "avg_train_score": float(np.mean(train_scores)),
            "avg_test_score": float(np.mean(test_scores)),
            "test_score_std": float(np.std(test_scores)),
            "param_stability": self._param_stability(windows),
        }

    def _get_topk(self, params: dict, universe: list[str]) -> list[str]:
        s = StrategyExecutor.create_strategy(self.config.strategy_key, **params)
        return s.run(universe).topk_tickers

    def _param_stability(self, windows: list[dict]) -> dict:
        if not windows:
            return {}
        param_names = list(windows[0]["best_params"].keys())
        stability = {}
        for name in param_names:
            vals = []
            for w in windows:
                v = w["best_params"].get(name)
                if isinstance(v, (int, float)):
                    vals.append(float(v))
            if vals:
                mu = np.mean(vals)
                sd = np.std(vals)
                stability[name] = {
                    "mean": float(mu),
                    "std": float(sd),
                    "cv": float(sd / abs(mu)) if mu != 0 else 0,
                }
        return stability
