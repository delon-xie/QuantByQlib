# optimization/__init__.py
"""策略优化框架 — 参数搜索、Walk-Forward、稳健性检验"""

from optimization.config import OptimizationConfig, StrategyParamSpec, STRATEGY_PARAMS_MAP
from optimization.data_manager import DataManager
from optimization.strategy_executor import StrategyExecutor
from optimization.backtester import EnhancedBacktester
from optimization.objective import ObjectiveFunction
from optimization.optimizer import GridSearchOptimizer, BayesianOptimizer
from optimization.walkforward import WalkForwardAnalyzer
from optimization.robustness import RobustnessChecker
from optimization.controller import OptimizationController, quick_optimize
from optimization.reporter import OptimizationReporter

# Lazy: visualizer requires matplotlib (optional)
# from optimization.visualizer import OptimizationVisualizer

__all__ = [
    "OptimizationConfig",
    "StrategyParamSpec",
    "STRATEGY_PARAMS_MAP",
    "DataManager",
    "StrategyExecutor",
    "EnhancedBacktester",
    "ObjectiveFunction",
    "GridSearchOptimizer",
    "BayesianOptimizer",
    "WalkForwardAnalyzer",
    "RobustnessChecker",
    "OptimizationController",
    "quick_optimize",
    "OptimizationReporter",
]
