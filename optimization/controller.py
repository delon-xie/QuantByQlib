# optimization/controller.py
"""优化控制器 — 编排完整优化流水线"""
from __future__ import annotations

from typing import Optional
from datetime import datetime
from loguru import logger

from optimization.config import OptimizationConfig
from optimization.data_manager import DataManager
from optimization.optimizer import GridSearchOptimizer, BayesianOptimizer
from optimization.walkforward import WalkForwardAnalyzer
from optimization.robustness import RobustnessChecker


class OptimizationController:
    """完整优化流水线控制器"""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.data_manager = DataManager()

    def run(self, progress_cb=None) -> dict:
        """
        流水线：数据准备 → 参数优化 → Walk-Forward → 稳健性检验
        """
        sk = self.config.strategy_key
        self._cb(progress_cb, 5, f"开始优化 [{sk}]...")

        # ── 1. 数据准备 ──────────────────────────
        self._cb(progress_cb, 10, "获取股票池...")
        universe = self._get_universe()
        logger.info(f"[Controller] 股票池: {len(universe)} 支")

        self._cb(progress_cb, 15, "下载历史价格...")
        end_date = self.config.end_date or datetime.now().strftime("%Y-%m-%d")
        prices = self.data_manager.fetch_prices_batch(
            universe, self.config.start_date, end_date
        )
        if prices.empty:
            raise RuntimeError("无法获取价格数据")

        self._cb(progress_cb, 20, "识别市场状态...")
        market_regime = self.data_manager.get_market_regime()

        splits = self.data_manager.split_data(
            prices, self.config.train_ratio, self.config.val_ratio
        )
        train_prices = splits["train"]

        results = {
            "strategy_key": sk,
            "market_regime": market_regime,
            "universe_size": len(universe),
            "data_range": f"{prices.index[0].date()} ~ {prices.index[-1].date()}",
            "optimization_time": datetime.now().isoformat(),
        }

        # ── 2. 参数优化 ──────────────────────────
        self._cb(progress_cb, 30, "参数优化中...")

        if self.config.bayesian_enabled:
            opt = BayesianOptimizer(self.config)
            opt_result = opt.optimize(
                train_prices, universe, market_regime,
                progress_cb=lambda p, m: self._cb(progress_cb, 30 + p // 4, m),
            )
        else:
            gs = GridSearchOptimizer(self.config)
            opt_result = gs.search(
                train_prices, universe, market_regime,
                progress_cb=lambda p, m: self._cb(progress_cb, 30 + p // 4, m),
            )
        results["optimization"] = opt_result
        best_params = opt_result["best_params"]
        self._cb(progress_cb, 55, f"最优参数: {best_params}")

        # ── 3. Walk-Forward ──────────────────────
        if self.config.walkforward_enabled:
            self._cb(progress_cb, 60, "Walk-Forward 验证...")
            wf = WalkForwardAnalyzer(self.config)
            try:
                wf_result = wf.analyze(
                    prices, universe, market_regime,
                    progress_cb=lambda p, m: self._cb(progress_cb, 60 + p // 3, m),
                )
                results["walkforward"] = wf_result
                self._cb(progress_cb, 75, f"WF avg_test={wf_result['avg_test_score']:.4f}")
            except Exception as e:
                logger.warning(f"[Controller] Walk-Forward 失败：{e}")
                results["walkforward"] = {"error": str(e)}

        # ── 4. 稳健性 ────────────────────────────
        if self.config.robustness_enabled:
            self._cb(progress_cb, 80, "稳健性检验...")
            checker = RobustnessChecker(self.config)
            mc = checker.monte_carlo(
                best_params, prices, universe, market_regime,
                progress_cb=lambda p, m: self._cb(progress_cb, 85, m),
            )
            results["monte_carlo"] = mc
            pert = checker.parameter_perturbation(
                best_params, prices, universe, market_regime,
                progress_cb=lambda p, m: self._cb(progress_cb, 92, m),
            )
            results["perturbation"] = pert

        self._cb(progress_cb, 100, f"优化完成 [{sk}]")
        return results

    def _get_universe(self) -> list[str]:
        """获取股票池：qlib instruments 文件 → S&P500 fallback"""
        inst_tickers = self._read_qlib_instruments()
        if inst_tickers:
            return inst_tickers

        from screening.stock_screener import StockScreener
        return StockScreener()._sp500_fallback()

    def _ensure_qlib_ready(self):
        """预先初始化 Qlib — 使用与策略完全相同的路径构造方式"""
        try:
            from pathlib import Path
            from core.app_state import get_state
            from core.qlibhelper import qlib_safeinit

            state = get_state()
            # 使用与策略完全相同的路径构造：Path.home()/.qlib/qlib_data/{reg}_data
            qlib_data = Path(f"{Path.home()}/.qlib/qlib_data/{state.reg}_data")
            qlib_safeinit(str(qlib_data))
            logger.info(f"[Controller] Qlib 预初始化完成: {qlib_data}")
        except Exception as e:
            logger.warning(f"[Controller] Qlib 预初始化失败: {e}")

    def _read_qlib_instruments(self) -> list[str]:
        """从 qlib instruments/all.txt 读取股票列表（不初始化 qlib）"""
        try:
            from core.qlibhelper import _find_data_dir, _normalize_ticker
            from core.app_state import get_state
            import re

            reg = getattr(self.config, 'reg', 'cn') or 'cn'
            get_state().reg = reg
            data_dir = _find_data_dir()
            # 优先使用 config.scope 指定的范围文件
            scope = getattr(self.config, 'scope', 'top200') or 'top200'
            inst_file = data_dir / "instruments" / f"{scope}.txt"

            if not inst_file.exists():
                # Fallback: 尝试 all.txt 但限制数量
                inst_file = data_dir / "instruments" / "csi300.txt"
                if not inst_file.exists():
                    return []

            tickers = []
            logger.info(f"[Controller] 从 {inst_file} 读取股票列表")
            for line in inst_file.read_text().strip().split("\n"):
                parts = line.split("\t")
                if parts:
                    t = _normalize_ticker(parts[0].strip().upper(), reg)
                    if t and not t.startswith("^"):
                        tickers.append(t)

            # 去重保持顺序
            seen = set()
            unique = [x for x in tickers if not (x in seen or seen.add(x))]
            return unique

        except Exception:
            return []

    def _cb(self, cb, pct: int, msg: str):
        if cb:
            try:
                cb(pct, msg)
            except Exception:
                pass
        logger.info(f"[Controller] {pct}% - {msg}")


def quick_optimize(
    strategy_key: str = "early_trend",
    start_date: str = "2023-01-01",
    progress_cb=None,
) -> dict:
    """快速优化入口"""
    from optimization.config import STRATEGY_PARAMS_MAP
    params = STRATEGY_PARAMS_MAP.get(strategy_key)
    if not params:
        raise ValueError(f"未知策略: {strategy_key}")
    config = OptimizationConfig(
        strategy_key=strategy_key,
        param_specs=params,
        start_date=start_date,
        grid_search_enabled=True,
        walkforward_enabled=True,
        robustness_enabled=True,
    )
    return OptimizationController(config).run(progress_cb=progress_cb)
