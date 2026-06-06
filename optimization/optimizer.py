# optimization/optimizer.py
"""参数优化器 — spawn 进程隔离防 conda 环境 segfault"""
from __future__ import annotations

import json
import multiprocessing
import sys
from itertools import product
from pathlib import Path
from typing import Optional
import pandas as pd
from loguru import logger

from optimization.config import OptimizationConfig
from optimization.objective import ObjectiveFunction


class GridSearchOptimizer:
    """网格搜索 — spawn 子进程隔离策略执行"""

    def __init__(self, config: OptimizationConfig):
        self.config = config

    def search(
        self,
        prices: pd.DataFrame,
        universe: list[str],
        market_regime: str = "expansion",
        progress_cb=None,
    ) -> dict:
        param_grid = self.config.get_param_grid()
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))
        total = len(combinations)
        logger.info(f"[GridSearch] {self.config.strategy_key} 共 {total} 组参数")

        # 保存共享数据
        tmpdir = Path("/tmp/qlib_opt")
        tmpdir.mkdir(exist_ok=True)
        prices_file = tmpdir / f"prices_{self.config.strategy_key}.csv"
        universe_file = tmpdir / f"universe_{self.config.strategy_key}.json"
        prices.to_csv(prices_file)
        universe_file.write_text(json.dumps(universe))
        project_root = str(Path.cwd())

        obj_fn = ObjectiveFunction(market_regime=market_regime)
        all_results = []

        for idx, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))
            if progress_cb:
                pct = 10 + int(idx / total * 80)
                progress_cb(pct, f"网格搜索 {idx+1}/{total}...")

            data = _eval_in_spawn({
                "strategy_key": self.config.strategy_key,
                "params": params,
                "prices_file": str(prices_file),
                "universe_file": str(universe_file),
                "initial_capital": self.config.initial_capital,
                "stop_loss_pct": self.config.stop_loss_pct,
                "project_root": project_root,
            })
            if data and data.get("error") is None:
                score = obj_fn.calculate(data["metrics"], data.get("enhanced"))
                all_results.append({
                    "params": params, "score": score,
                    "metrics": data["metrics"],
                    "enhanced": data.get("enhanced", {}),
                })
            else:
                err = (data or {}).get("error", "failed")
                logger.debug(f"[GridSearch] {params} 失败：{err}")
                all_results.append({"params": params, "score": -999.0, "error": err})

        valid = [r for r in all_results if r["score"] > -998]
        if not valid:
            raise RuntimeError("网格搜索无有效结果")

        best = max(valid, key=lambda r: r["score"])
        logger.info(f"[GridSearch] 最优: score={best['score']:.4f}, params={best['params']}")
        return {
            "best_params": best["params"], "best_score": best["score"],
            "best_metrics": best["metrics"],
            "best_enhanced": best.get("enhanced", {}),
            "all_results": all_results,
        }


class BayesianOptimizer:
    """贝叶斯优化器"""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.grid_optimizer = GridSearchOptimizer(config)

    def optimize(self, prices, universe, market_regime="expansion", progress_cb=None):
        try:
            from skopt import gp_minimize
            from skopt.space import Real, Integer, Categorical
        except ImportError:
            return self.grid_optimizer.search(prices, universe, market_regime, progress_cb)

        bounds = self.config.get_bayesian_bounds()
        dimensions = []
        for name, bound in bounds.items():
            # 处理不同类型的边界格式
            if bound[-1] in ("integer", "real"):
                vals = (bound[0], bound[1])
                kind = bound[2]
            else:
                vals, kind = bound

            if kind == "integer":
                dimensions.append(Integer(int(vals[0]), int(vals[1]), name=name))
            elif kind == "real":
                dimensions.append(Real(vals[0], vals[1], name=name))
            else:
                dimensions.append(Categorical(vals, name=name))

        obj_fn = ObjectiveFunction(market_regime=market_regime)
        eval_count = [0]

        tmpdir = Path("/tmp/qlib_opt"); tmpdir.mkdir(exist_ok=True)
        prices_file = tmpdir / f"prices_{self.config.strategy_key}_bayes.csv"
        universe_file = tmpdir / f"universe_{self.config.strategy_key}_bayes.json"
        prices.to_csv(prices_file)
        universe_file.write_text(json.dumps(universe))
        project_root = str(Path.cwd())

        def objective(x):
            params = {dim.name: x[i] for i, dim in enumerate(dimensions)}
            data = _eval_in_spawn({
                "strategy_key": self.config.strategy_key,
                "params": params,
                "prices_file": str(prices_file),
                "universe_file": str(universe_file),
                "initial_capital": self.config.initial_capital,
                "stop_loss_pct": self.config.stop_loss_pct,
                "project_root": project_root,
            })
            eval_count[0] += 1
            if data and data.get("error") is None:
                s = obj_fn.negate(data["metrics"], data.get("enhanced"))
                if progress_cb and eval_count[0] % 5 == 0:
                    progress_cb(
                        30 + min(int(eval_count[0] / self.config.bayesian_n_iter * 60), 60),
                        f"Bayesian {eval_count[0]}/{self.config.bayesian_n_iter}",
                    )
                return float(s)
            return 1e9

        result = gp_minimize(objective, dimensions,
                             n_calls=self.config.bayesian_n_iter,
                             n_initial_points=self.config.bayesian_init_points,
                             random_state=42, verbose=False)
        bp = {dim.name: result.x[i] for i, dim in enumerate(dimensions)}
        logger.info(f"[Bayesian] 完成 {eval_count[0]} 次，score={-result.fun:.4f}")
        return {"best_params": bp, "best_score": float(-result.fun)}


def _eval_in_spawn(task: dict) -> Optional[dict]:
    """通过 multiprocessing.Process (spawn) 运行评估，彻底避免 fork"""
    ctx = multiprocessing.get_context('spawn')
    result_queue = ctx.Queue()

    p = ctx.Process(target=_spawn_runner, args=(result_queue, task))
    p.start()
    p.join(timeout=120)
    if p.is_alive():
        p.terminate()
        p.join()
        return {"error": "timeout (120s)"}
    if not result_queue.empty():
        return result_queue.get()
    return {"error": f"exit code {p.exitcode}"}


def _spawn_runner(q, t):
    """模块级函数，可被 pickle"""
    try:
        out = _run_worker(t)
        q.put(out if out else {"error": "empty result"})
    except Exception as e:
        q.put({"error": str(e)[:300]})


def _run_worker(task: dict) -> Optional[dict]:
    """在子进程中执行：初始化 qlib → 运行策略 → 回测"""
    import json as _json
    import os as _os
    import warnings as _w
    from pathlib import Path as _Path
    _w.filterwarnings('ignore')

    _os.chdir(task.get('project_root', str(_Path.cwd())))

    import pandas as _pd
    prices = _pd.read_csv(task['prices_file'], index_col=0, parse_dates=True)
    universe = _json.loads(_Path(task['universe_file']).read_text())

    try:
        from core.app_state import get_state as _gs
        from core.qlibhelper import qlib_safeinit as _qsi
        state = _gs()
        dp = _Path(f"{_Path.home()}/.qlib/qlib_data/{state.reg}_data")
        _qsi(str(dp))
    except Exception:
        pass

    from optimization.strategy_executor import StrategyExecutor as _SE
    from optimization.backtester import EnhancedBacktester as _EBT

    strategy = _SE.create_strategy(task['strategy_key'], **task['params'])
    result = strategy.run(universe, prices=prices)

    bt = _EBT(
        initial_capital=task['initial_capital'],
        stop_loss_config={'fixed': task['stop_loss_pct']},
    )
    bt_result = bt.run_signal_backtest(result.topk_tickers, prices)

    def _sv(v):
        if v is None: return None
        if isinstance(v, (int, float, str, bool)): return v
        if hasattr(v, 'item'): return float(v)
        return None

    m = bt_result['metrics']
    e = bt_result.get('enhanced', {})
    return {
        'metrics': {
            'sharpe_ratio': _sv(m.sharpe_ratio),
            'max_drawdown': _sv(m.max_drawdown),
            'total_return': _sv(m.total_return),
            'annual_return': _sv(m.annual_return),
            'volatility': _sv(m.volatility),
            'win_rate': _sv(m.win_rate),
            'alpha': _sv(m.alpha),
            'beta': _sv(m.beta),
        },
        'enhanced': {k: _sv(v) for k, v in e.items()},
    }
