# optimization/config.py
"""优化配置与参数规格定义"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StrategyParamSpec:
    """单个策略参数的优化规格"""
    name: str                          # 参数名
    type: str                          # "int" | "float" | "choice"
    default: float | int | str
    range: list                        # [min, max] for int/float, [choices...] for choice
    priority: int = 3                  # 1=★★★, 2=★★☆, 3=★☆☆

    def to_bounds(self):
        """转为 scikit-optimize 的维度定义"""
        if self.type == "int":
            return (self.range[0], self.range[1], "integer")
        elif self.type == "float":
            return (self.range[0], self.range[1], "real")
        else:
            return (self.range, "categorical")


@dataclass
class OptimizationConfig:
    """一次优化运行的完整配置"""
    # 策略
    strategy_key: str                  # "early_trend" | "golden_cross" | "ma10" | "trendline_breakout"
    param_specs: list[StrategyParamSpec] = field(default_factory=list)

    # 数据
    reg: str = "cn"
    scope: str = "top200"
    start_date: str = "2020-01-01"
    end_date: str = ""                     # "" = 今天

    # 数据切分
    train_ratio: float = 0.7
    val_ratio: float = 0.15
    test_ratio: float = 0.15

    # 回测
    initial_capital: float = 1_000_000.0
    commission: float = 0.0015
    slippage: float = 0.001
    position_size: float = 0.1
    stop_loss_pct: float = 0.05       # 固定止损 5%

    # 网格搜索
    grid_search_enabled: bool = True
    grid_metric: str = "sharpe_ratio"  # 优化目标

    # 贝叶斯优化
    bayesian_enabled: bool = False
    bayesian_n_iter: int = 50
    bayesian_init_points: int = 10

    # Walk-Forward
    walkforward_enabled: bool = True
    wf_train_window: int = 252
    wf_test_window: int = 63
    wf_step: int = 21

    # 稳健性检验
    robustness_enabled: bool = True
    monte_carlo_n_sim: int = 500
    monte_carlo_noise: float = 0.01
    perturbation_factor: float = 0.1

    # 输出
    output_dir: str = ""               # "" = 自动生成

    def get_param_grid(self) -> dict[str, list]:
        """生成网格搜索参数空间（每参数约5步，控制组合数）"""
        grid = {}
        for spec in self.param_specs:
            if spec.type == "choice":
                grid[spec.name] = spec.range
            elif spec.type == "int":
                span = spec.range[1] - spec.range[0]
                # 至少2步，最多生成约4个取值点
                step = max(2, int(span / 4))
                grid[spec.name] = list(range(int(spec.range[0]), int(spec.range[1]) + 1, step))
            else:  # float
                import numpy as np
                grid[spec.name] = list(np.linspace(spec.range[0], spec.range[1], 5))
        return grid

    def get_bayesian_bounds(self) -> dict:
        return {s.name: s.to_bounds() for s in self.param_specs}

    def get_default_params(self) -> dict:
        return {s.name: s.default for s in self.param_specs}


# ── 四大策略预设参数规格（名称对齐实际策略 __init__）───────────

EARLY_TREND_PARAMS = [
    StrategyParamSpec("max_convergence_days", "int", 20, [10, 30], 2),
    StrategyParamSpec("max_slope", "float", 0.02, [0.01, 0.05], 1),
    StrategyParamSpec("volume_increase_ratio", "float", 1.2, [1.0, 2.0], 3),
    StrategyParamSpec("trend_formation_days", "int", 5, [3, 10], 2),
]

GOLDEN_CROSS_PARAMS = [
    StrategyParamSpec("max_cross_days", "int", 10, [5, 20], 1),
    StrategyParamSpec("cross_decay_half_life", "int", 3, [1, 8], 1),
    StrategyParamSpec("divergence_weight", "float", 1.5, [1.0, 3.0], 2),
    StrategyParamSpec("divergence_start_days", "int", 5, [3, 12], 2),
    StrategyParamSpec("min_ma_distance", "float", 0.01, [0.005, 0.03], 3),
]

MA10_PARAMS = [
    StrategyParamSpec("decay_half_life", "int", 5, [2, 15], 1),
    StrategyParamSpec("decay_type", "choice", "exponential", ["exponential", "linear"], 2),
    StrategyParamSpec("min_turn_up_weeks", "int", 1, [1, 3], 2),
    StrategyParamSpec("max_turn_up_weeks", "int", 4, [2, 8], 2),
    StrategyParamSpec("turn_up_mode", "choice", "relaxed", ["strict", "relaxed", "trend"], 3),
]

TRENDLINE_BREAKOUT_PARAMS = [
    StrategyParamSpec("breakthrough_threshold", "float", 0.03, [0.01, 0.06], 1),
    StrategyParamSpec("volume_confirmation_ratio", "float", 1.5, [1.2, 2.5], 1),
    StrategyParamSpec("trendline_points", "int", 20, [10, 30], 1),
    StrategyParamSpec("min_trend_duration", "int", 10, [5, 20], 2),
    StrategyParamSpec("consolidation_days", "int", 3, [1, 7], 2),
    StrategyParamSpec("retest_confirmation", "choice", True, [True, False], 3),
]

STRATEGY_PARAMS_MAP = {
    "early_trend": EARLY_TREND_PARAMS,
    "golden_cross": GOLDEN_CROSS_PARAMS,
    "ma10": MA10_PARAMS,
    "trendline_breakout": TRENDLINE_BREAKOUT_PARAMS,
}
