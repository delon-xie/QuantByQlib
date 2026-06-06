# optimization/robustness.py
"""稳健性检验 — 蒙特卡洛模拟 + 参数扰动测试"""
from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from optimization.config import OptimizationConfig
from optimization.backtester import EnhancedBacktester
from optimization.objective import ObjectiveFunction
from optimization.strategy_executor import StrategyExecutor


class RobustnessChecker:
    """策略稳健性检验器"""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.backtester = EnhancedBacktester(
            initial_capital=config.initial_capital,
            stop_loss_config={"fixed": config.stop_loss_pct},
        )

    def monte_carlo(
        self,
        best_params: dict,
        prices: pd.DataFrame,
        universe: list[str],
        market_regime: str = "expansion",
        progress_cb=None,
    ) -> dict:
        """蒙特卡洛模拟：价格加噪，观察得分分布"""
        n_sim = self.config.monte_carlo_n_sim
        noise = self.config.monte_carlo_noise
        obj_fn = ObjectiveFunction(market_regime=market_regime)

        topk = self._get_topk(best_params, universe)
        scores = []

        for i in range(n_sim):
            if progress_cb and i % 50 == 0:
                progress_cb(int(i / n_sim * 50), f"MC {i+1}/{n_sim}")
            noisy = self._add_noise(prices, noise)
            result = self.backtester.run_signal_backtest(topk, noisy)
            scores.append(obj_fn.calculate(result["metrics"], result.get("enhanced")))

        s = np.array(scores)
        return {
            "n_simulations": n_sim,
            "scores": s.tolist(),
            "score_mean": float(s.mean()),
            "score_std": float(s.std()),
            "score_p5": float(np.percentile(s, 5)),
            "score_p95": float(np.percentile(s, 95)),
            "pass_threshold": s.mean() > 0.3,
        }

    def parameter_perturbation(
        self,
        best_params: dict,
        prices: pd.DataFrame,
        universe: list[str],
        market_regime: str = "expansion",
        progress_cb=None,
    ) -> dict:
        """参数扰动：±factor，观察得分敏感度"""
        obj_fn = ObjectiveFunction(market_regime=market_regime)
        factor = self.config.perturbation_factor

        base_bt = self.backtester.run_signal_backtest(
            self._get_topk(best_params, universe), prices
        )
        base_score = obj_fn.calculate(base_bt["metrics"], base_bt.get("enhanced"))

        results = {}
        for pname, pval in best_params.items():
            if not isinstance(pval, (int, float)):
                continue
            param_scores = {}
            for direction, label in [(1 + factor, "up"), (1 - factor, "down")]:
                pert = dict(best_params)
                pert[pname] = type(pval)(pval * direction)
                try:
                    bt = self.backtester.run_signal_backtest(
                        self._get_topk(pert, universe), prices
                    )
                    sc = obj_fn.calculate(bt["metrics"], bt.get("enhanced"))
                    param_scores[label] = {
                        "value": pert[pname],
                        "score": sc,
                        "delta": round(sc - base_score, 6),
                    }
                except Exception as e:
                    param_scores[label] = {"error": str(e)}
            results[pname] = {
                "base_value": pval,
                "base_score": base_score,
                "perturbations": param_scores,
                "sensitivity": abs(param_scores.get("up", {}).get("delta", 0))
                + abs(param_scores.get("down", {}).get("delta", 0)),
            }
            if progress_cb:
                progress_cb(50, f"参数扰动: {pname}")

        sorted_p = sorted(results.items(), key=lambda x: x[1]["sensitivity"], reverse=True)
        return {
            "base_score": base_score,
            "parameters": dict(sorted_p),
            "most_sensitive": sorted_p[0][0] if sorted_p else None,
            "least_sensitive": sorted_p[-1][0] if sorted_p else None,
        }

    def _add_noise(self, prices: pd.DataFrame, noise: float) -> pd.DataFrame:
        n = prices.copy()
        for col in n.columns:
            n[col] = n[col] * (1 + np.random.normal(0, noise, len(n)))
        return n

    def _get_topk(self, params: dict, universe: list[str]) -> list[str]:
        s = StrategyExecutor.create_strategy(self.config.strategy_key, **params)
        return s.run(universe).topk_tickers
