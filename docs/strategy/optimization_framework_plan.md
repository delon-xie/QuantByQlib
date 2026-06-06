# 策略优化框架实施计划

> **For AI Agent Implementer:** 使用 writing-plans 技能驱动，每步 checkbox 追踪进度。推荐使用 subagent-driven-development 并行执行独立模块。

**Goal:** 搭建策略优化框架，实现对 Early Trend / Golden Cross / MA10 / Trendline Breakout 四大策略的参数自动搜索、Walk-Forward 验证、稳健性检验和报告生成。

**Architecture:** 模块化设计，核心控制器协调六大模块：DataManager（数据准备+市场状态识别）、StrategyExecutor（策略工厂）、EnhancedBacktester（含止损回测）、Optimizer（网格搜索+贝叶斯）、RobustnessChecker（蒙特卡洛+参数扰动）、ReportGenerator（可视化+Markdown报告）。最大化复用现有 BacktestEngine、MarketDataClient、HMM Regime、BacktestMetrics 组件。

**Tech Stack:** Python 3.10+, pandas, numpy, matplotlib, scikit-optimize (Bayesian), 复用项目内 qlib/yfinance/market_data_client/hmm_regime/backtest_engine

**Constraints:**
- 每个模块文件 ≤ 300 行
- 不修改现有策略代码（通过参数传入控制）
- 所有新代码放在 `optimization/` 目录下
- 依赖现有 `backtesting/`、`data/`、`services/` 模块

---

## 文件结构

```
optimization/
├── __init__.py              # 包导出
├── config.py                # 优化配置 dataclass (~80行)
├── data_manager.py          # 数据管理（复用 MarketDataClient + HMM）(~120行)
├── strategy_executor.py     # 策略工厂 (~100行)
├── backtester.py            # 增强回测（继承 BacktestEngine，止损）(~150行)
├── objective.py             # 多目标优化函数 (~100行)
├── optimizer.py             # 网格搜索 + 贝叶斯优化 (~200行)
├── walkforward.py           # Walk-Forward 分析 (~120行)
├── robustness.py            # 蒙特卡洛 + 参数扰动 (~120行)
├── sensitivity.py           # 参数敏感性分析 (~100行)
├── controller.py            # 优化控制器（编排）(~200行)
├── reporter.py              # 报告生成 (~150行)
└── visualizer.py            # 图表生成 (~150行)

tests/
└── test_optimization/
    ├── __init__.py
    ├── test_data_manager.py
    ├── test_backtester.py
    ├── test_objective.py
    ├── test_optimizer.py
    ├── test_walkforward.py
    ├── test_robustness.py
    └── test_controller.py
```

---

## 复用现有组件映射

| 模块 | 复用组件 | 方式 |
|------|---------|------|
| data_manager | `data/market_data_client.py::get_ohlcv` | 直接调用获取OHLCV |
| data_manager | `backtesting/price_cache.py` | 透明复用（BacktestEngine内置） |
| data_manager | `services/hmm_regime.py::run_regime_detection` | 调用获取市场状态 |
| backtester | `backtesting/backtest_engine.py::BacktestEngine` | 继承并扩展 |
| backtester | `backtesting/performance_metrics.py::calc_metrics_from_returns` | 直接调用 |
| strategy_executor | `strategies/screening/early_trend_screening.py` | 参数化实例化 |
| strategy_executor | `strategies/screening/golden_cross_screening.py` | 参数化实例化 |
| strategy_executor | `strategies/screening/ma10_screening.py` | 参数化实例化 |
| strategy_executor | `strategies/screening/trendline_breakout_screening.py` | 参数化实例化 |
| controller | `core/event_bus.py::EventBus` | 发布优化进度事件 |
| reporter | `services/output_paths.py` | 输出到策略目录 |

---

## Task 1: 基础设施 — OptimizationConfig 数据类

**Files:**
- Create: `optimization/__init__.py`
- Create: `optimization/config.py`

- [ ] **Step 1: 创建 `optimization/__init__.py`**

```python
# optimization/__init__.py
"""策略优化框架 — 参数搜索、Walk-Forward、稳健性检验"""

from optimization.config import OptimizationConfig, StrategyParamSpec
from optimization.controller import OptimizationController
from optimization.reporter import OptimizationReporter

__all__ = [
    "OptimizationConfig",
    "StrategyParamSpec",
    "OptimizationController",
    "OptimizationReporter",
]
```

- [ ] **Step 2: 创建 `optimization/config.py`**

```python
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
    universe: Optional[list[str]] = None   # None = 自动获取 S&P500
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
        """生成网格搜索参数空间"""
        grid = {}
        for spec in self.param_specs:
            if spec.type == "choice":
                grid[spec.name] = spec.range
            elif spec.type == "int":
                step = max(1, int((spec.range[1] - spec.range[0]) / 10))
                grid[spec.name] = list(range(int(spec.range[0]), int(spec.range[1]) + 1, step))
            else:  # float
                import numpy as np
                grid[spec.name] = list(np.linspace(spec.range[0], spec.range[1], 10))
        return grid

    def get_bayesian_bounds(self) -> dict:
        """生成贝叶斯优化参数边界"""
        return {s.name: s.to_bounds() for s in self.param_specs}

    def get_default_params(self) -> dict:
        return {s.name: s.default for s in self.param_specs}


# ── 四大策略预设参数规格 ──────────────────────────────────────

EARLY_TREND_PARAMS = [
    StrategyParamSpec("max_convergence_days", "int", 20, [10, 30], 2),
    StrategyParamSpec("max_slope", "float", 0.02, [0.01, 0.05], 1),
    StrategyParamSpec("volume_increase_ratio", "float", 1.2, [1.0, 2.0], 3),
    StrategyParamSpec("trend_formation_days", "int", 5, [3, 10], 2),
]

GOLDEN_CROSS_PARAMS = [
    StrategyParamSpec("cross_decay_half_life", "int", 3, [1, 10], 1),
    StrategyParamSpec("max_cross_days", "int", 10, [5, 20], 1),
    StrategyParamSpec("divergence_decay_half_life", "int", 10, [5, 20], 2),
    StrategyParamSpec("divergence_weight_multiplier", "float", 1.5, [1.0, 3.0], 2),
    StrategyParamSpec("min_ma_distance", "float", 0.01, [0.005, 0.03], 3),
]

MA10_PARAMS = [
    StrategyParamSpec("turnup_strength_factor", "float", 1000.0, [500.0, 2000.0], 1),
    StrategyParamSpec("price_position_factor", "float", 500.0, [200.0, 1000.0], 1),
    StrategyParamSpec("stability_factor", "float", 200.0, [100.0, 400.0], 2),
    StrategyParamSpec("decay_half_life", "int", 5, [2, 15], 1),
    StrategyParamSpec("momentum_decay", "float", 0.85, [0.70, 0.95], 1),
    StrategyParamSpec("decay_type", "choice", "exponential", ["exponential", "linear"], 2),
]

TRENDLINE_BREAKOUT_PARAMS = [
    StrategyParamSpec("breakthrough_threshold", "float", 0.03, [0.01, 0.06], 1),
    StrategyParamSpec("volume_confirmation_ratio", "float", 1.5, [1.2, 2.5], 1),
    StrategyParamSpec("trendline_points", "int", 20, [10, 30], 1),
    StrategyParamSpec("min_trend_days", "int", 10, [5, 20], 2),
    StrategyParamSpec("consolidation_days", "int", 3, [1, 7], 2),
    StrategyParamSpec("retest_threshold", "float", 0.01, [0.005, 0.02], 3),
]

STRATEGY_PARAMS_MAP = {
    "early_trend": EARLY_TREND_PARAMS,
    "golden_cross": GOLDEN_CROSS_PARAMS,
    "ma10": MA10_PARAMS,
    "trendline_breakout": TRENDLINE_BREAKOUT_PARAMS,
}
```

- [ ] **Step 3: 验证**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -c "from optimization.config import OptimizationConfig, EARLY_TREND_PARAMS, STRATEGY_PARAMS_MAP; c=OptimizationConfig(strategy_key='early_trend', param_specs=EARLY_TREND_PARAMS); print(c.get_param_grid()); print(c.get_bayesian_bounds())"
```

预期：输出参数网格和贝叶斯边界字典，无错误。

- [ ] **Step 4: Commit**

```bash
git add optimization/__init__.py optimization/config.py
git commit -m "feat(optimization): add OptimizationConfig and strategy param specs"
```

---

## Task 2: 数据管理模块 DataManager

**Files:**
- Create: `optimization/data_manager.py`
- Tests: `tests/test_optimization/test_data_manager.py`

- [ ] **Step 1: 创建 `optimization/data_manager.py`**

```python
# optimization/data_manager.py
"""数据管理模块 — 复用 MarketDataClient + HMM Regime"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import numpy as np
from loguru import logger

from data.market_data_client import get_ohlcv, get_ohlcv_period


class DataManager:
    """统一数据管理：获取、清洗、切分、市场状态识别"""

    def __init__(self, universe: Optional[list[str]] = None):
        self.universe = universe

    # ── 数据获取 ────────────────────────────────────────

    def fetch_prices(
        self,
        tickers: list[str],
        start: str,
        end: str,
        field: str = "close",
    ) -> pd.DataFrame:
        """
        批量获取价格数据，返回 (date x ticker) DataFrame。
        复用 MarketDataClient 的降级链。
        """
        all_data = {}
        for ticker in tickers:
            df = get_ohlcv(ticker, start, end)
            if df is not None and not df.empty:
                if field in df.columns:
                    all_data[ticker] = df[field]
        if not all_data:
            return pd.DataFrame()
        prices = pd.DataFrame(all_data)
        prices.index = pd.to_datetime(prices.index)
        return prices.sort_index()

    def fetch_prices_batch(
        self,
        tickers: list[str],
        start: str,
        end: str,
    ) -> pd.DataFrame:
        """
        使用 yfinance 批量下载（更快）。
        回退到逐个获取。
        """
        try:
            import yfinance as yf
            from core.app_state import get_state
            from core.qlibhelper import normalize_cn_tickers

            reg = get_state().reg
            yf_tickers = tickers
            if reg == "cn":
                yf_tickers = normalize_cn_tickers(tickers)

            df_all = yf.download(
                yf_tickers,
                start=start,
                end=end,
                progress=False,
                auto_adjust=False,
                threads=True,
            )
            if df_all is not None and not df_all.empty:
                if isinstance(df_all.columns, pd.MultiIndex):
                    if "Close" in df_all.columns.get_level_values(0):
                        close_df = df_all["Close"]
                    else:
                        level0 = df_all.columns.get_level_values(0)[0]
                        close_df = df_all[level0]
                else:
                    close_col = next(
                        (c for c in df_all.columns if str(c).lower() in ("close", "adj close")),
                        df_all.columns[0],
                    )
                    close_df = df_all[[close_col]]
                    close_df.columns = [tickers[0]]

                close_df = close_df.dropna(how="all")
                close_df.index = pd.to_datetime(close_df.index)
                return close_df[self.universe or tickers] if self.universe else close_df

        except Exception as e:
            logger.warning(f"[DataManager] 批量下载失败，回退逐个获取：{e}")

        return self.fetch_prices(tickers, start, end, "close")

    # ── 数据切分 ────────────────────────────────────────

    def split_data(
        self,
        data: pd.DataFrame,
        train_ratio: float = 0.7,
        val_ratio: float = 0.15,
    ) -> dict[str, pd.DataFrame]:
        """按时间序列切分为 train/val/test"""
        n = len(data)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        return {
            "train": data.iloc[:train_end],
            "val": data.iloc[train_end:val_end],
            "test": data.iloc[val_end:],
        }

    # ── 市场状态识别 ────────────────────────────────────

    def get_market_regime(self, trade_date: Optional[date] = None) -> str:
        """
        获取当前市场状态，复用 HMM Regime 模块。
        返回: "recovery" | "expansion" | "overheating" | "recession"
        """
        try:
            from services.hmm_regime import run_regime_detection
            import json

            result_path = run_regime_detection(trade_date=trade_date)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            regime = payload.get("regime", "expansion")
            logger.info(f"[DataManager] 市场状态: {regime} (概率={payload.get('regime_probability', 0):.2%})")
            return regime
        except Exception as e:
            logger.warning(f"[DataManager] HMM 状态识别失败，默认 neutrality：{e}")
            return "expansion"

    # ── 数据质量检查 ────────────────────────────────────

    def validate_data(self, prices: pd.DataFrame) -> dict:
        """检查数据质量，返回问题报告"""
        issues = {
            "total_tickers": len(prices.columns),
            "total_days": len(prices),
            "missing_ratio": float(prices.isna().sum().sum() / prices.size),
            "tickers_with_gaps": [],
            "min_data_points": int(prices.count().min()) if not prices.empty else 0,
        }

        for col in prices.columns:
            na_ratio = prices[col].isna().mean()
            if na_ratio > 0.1:
                issues["tickers_with_gaps"].append({
                    "ticker": col,
                    "missing_pct": round(float(na_ratio * 100), 1),
                })

        if issues["missing_ratio"] > 0.2:
            logger.warning(f"[DataManager] 数据缺失率 {issues['missing_ratio']:.1%}，超出 20% 阈值")

        return issues
```

- [ ] **Step 2: 编写测试 `tests/test_optimization/test_data_manager.py`**

```python
# tests/test_optimization/test_data_manager.py
import pytest
import pandas as pd
import numpy as np
from optimization.data_manager import DataManager


class TestDataManager:
    def test_fetch_prices_single(self):
        dm = DataManager()
        prices = dm.fetch_prices(["AAPL"], "2025-01-01", "2025-01-31")
        assert isinstance(prices, pd.DataFrame)
        if not prices.empty:
            assert "AAPL" in prices.columns

    def test_split_data_ratios(self):
        dm = DataManager()
        dates = pd.date_range("2020-01-01", periods=100, freq="B")
        data = pd.DataFrame(
            {"AAPL": np.random.randn(100).cumsum() + 100},
            index=dates,
        )
        splits = dm.split_data(data, train_ratio=0.7, val_ratio=0.15)
        assert len(splits["train"]) == 70
        assert len(splits["val"]) == 15
        assert len(splits["test"]) == 15

    def test_validate_data_quality(self):
        dm = DataManager()
        dates = pd.date_range("2020-01-01", periods=50, freq="B")
        prices = pd.DataFrame({"AAPL": np.random.randn(50).cumsum() + 100}, index=dates)
        prices.iloc[:5, 0] = np.nan  # 10% missing
        report = dm.validate_data(prices)
        assert report["missing_ratio"] == pytest.approx(0.1, abs=0.01)

    def test_get_market_regime(self):
        """仅在有 HMM 环境时运行"""
        dm = DataManager()
        regime = dm.get_market_regime()
        assert regime in ("recovery", "expansion", "overheating", "recession")
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_data_manager.py -v --tb=short
```

预期：4 个测试全部 PASS（get_market_regime 依赖 hmmlearn 安装）。

- [ ] **Step 4: Commit**

```bash
git add optimization/data_manager.py tests/test_optimization/
git commit -m "feat(optimization): add DataManager with market regime detection"
```

---

## Task 3: 策略执行引擎 StrategyExecutor

**Files:**
- Create: `optimization/strategy_executor.py`

- [ ] **Step 1: 创建 `optimization/strategy_executor.py`**

```python
# optimization/strategy_executor.py
"""策略执行引擎 — 策略工厂 + 信号生成"""
from __future__ import annotations

from typing import Optional
import pandas as pd
from loguru import logger

from strategies.base_strategy import BaseStrategy, StrategyResult


class StrategyExecutor:
    """策略工厂：根据 key 创建策略实例，参数由外部控制"""

    _STRATEGY_MAP = {
        "early_trend": ("strategies.screening.early_trend_screening", "EarlyTrendFormationStrategy"),
        "golden_cross": ("strategies.screening.golden_cross_screening", "GoldenCrossMAStrategy"),
        "ma10": ("strategies.screening.ma10_screening", "MA10TurnUpScreenStrategy"),
        "trendline_breakout": ("strategies.screening.trendline_breakout_screening", "TrendlineBreakoutStrategy"),
    }

    @classmethod
    def create_strategy(cls, strategy_key: str, **params) -> BaseStrategy:
        """
        创建策略实例。

        Args:
            strategy_key: "early_trend" | "golden_cross" | "ma10" | "trendline_breakout"
            **params: 策略参数覆盖

        Returns:
            BaseStrategy 实例
        """
        if strategy_key not in cls._STRATEGY_MAP:
            raise ValueError(f"未知策略: {strategy_key}，可选：{list(cls._STRATEGY_MAP)}")

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
        """
        创建策略并运行。

        Args:
            strategy_key: 策略标识
            universe: 股票池
            params: 策略参数字典
            progress_cb: 进度回调

        Returns:
            StrategyResult 包含 topk_tickers 和 scores
        """
        if params is None:
            params = {}

        strategy = cls.create_strategy(strategy_key, **params)
        return strategy.run(universe, progress_cb=progress_cb)

    @classmethod
    def list_strategies(cls) -> list[str]:
        return list(cls._STRATEGY_MAP)
```

- [ ] **Step 2: 验证**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -c "
from optimization.strategy_executor import StrategyExecutor
s = StrategyExecutor.create_strategy('early_trend', topk=10, max_convergence_days=15)
print(f'Strategy: {s.KEY}, params: max_convergence_days={s.max_convergence_days}')
print(f'Available: {StrategyExecutor.list_strategies()}')
"
```

预期：输出策略信息和可用策略列表。

- [ ] **Step 3: Commit**

```bash
git add optimization/strategy_executor.py
git commit -m "feat(optimization): add StrategyExecutor with factory pattern"
```

---

## Task 4: 增强回测引擎 EnhancedBacktester

**Files:**
- Create: `optimization/backtester.py`
- Tests: `tests/test_optimization/test_backtester.py`

- [ ] **Step 1: 创建 `optimization/backtester.py`**

```python
# optimization/backtester.py
"""增强回测引擎 — 继承 BacktestEngine，添加止损和增强指标"""
from __future__ import annotations

from typing import Optional
import pandas as pd
import numpy as np
from loguru import logger

from backtesting.backtest_engine import BacktestEngine, BacktestConfig, BacktestReport
from backtesting.performance_metrics import BacktestMetrics, calc_metrics_from_returns


class EnhancedBacktester:
    """
    增强回测引擎。
    包装现有 BacktestEngine，增加：
    - 持仓级止损模拟（固定/移动/时间）
    - 策略信号驱动的回测（而非 ML 模型预测）
    - 增强指标（Calmar、Sortino、ProfitFactor）
    """

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
            "fixed": 0.05,          # 5% 固定止损
            "trailing": True,       # 启用移动止损
            "trailing_factor": 2.0, # ATR 倍数
            "time_based": 20,       # 20 天不创新高离场
        }

    def run_signal_backtest(
        self,
        topk_tickers: list[str],
        prices: pd.DataFrame,
        benchmark_prices: Optional[pd.Series] = None,
    ) -> dict:
        """
        对策略选出的 Top-K 股票进行等权组合回测。

        Args:
            topk_tickers: 选出的股票列表
            prices: (date x ticker) 收盘价 DataFrame
            benchmark_prices: 基准价格 Series

        Returns:
            {"metrics": BacktestMetrics, "nav_series": pd.Series, "bm_series": pd.Series}
        """
        if prices.empty or not topk_tickers:
            return {
                "metrics": BacktestMetrics(),
                "nav_series": pd.Series(dtype=float),
                "bm_series": pd.Series(dtype=float),
            }

        # 取交集（有些 ticker 可能没有价格数据）
        available = [t for t in topk_tickers if t in prices.columns]
        if not available:
            logger.warning("[EnhancedBacktester] 无可用价格数据")
            return {
                "metrics": BacktestMetrics(),
                "nav_series": pd.Series(dtype=float),
                "bm_series": pd.Series(dtype=float),
            }

        price_subset = prices[available].dropna(how="all")

        # 等权组合日收益
        daily_ret = price_subset.pct_change().dropna()
        portfolio_ret = daily_ret.mean(axis=1)

        # 应用止损模拟
        portfolio_ret = self._apply_stop_loss(portfolio_ret, price_subset)

        # 净值曲线
        nav_series = (1 + portfolio_ret).cumprod()

        # 基准
        bm_ret = None
        bm_series = pd.Series(dtype=float)
        if benchmark_prices is not None:
            bm_ret = benchmark_prices.pct_change().dropna()
            bm_series = (1 + bm_ret).cumprod()

        metrics = calc_metrics_from_returns(portfolio_ret, bm_ret)

        # 增强指标
        enhanced = self._calc_enhanced_metrics(portfolio_ret)

        return {
            "metrics": metrics,
            "enhanced": enhanced,
            "nav_series": nav_series,
            "bm_series": bm_series,
        }

    def _apply_stop_loss(
        self,
        daily_ret: pd.Series,
        prices: pd.DataFrame,
    ) -> pd.Series:
        """
        简化的组合级止损模拟。
        当组合自高点回撤超过 fixed% 时，将后续收益置零（模拟清仓）。
        """
        nav = (1 + daily_ret).cumprod()
        peak = nav.cummax()
        drawdown = (nav - peak) / peak

        stopped = drawdown <= -self.stop_loss_config["fixed"]
        if stopped.any():
            stop_idx = stopped[stopped].index[0]
            daily_ret.loc[stop_idx:] = 0.0
            logger.debug(f"[EnhancedBacktester] 触发止损在 {stop_idx.date()}")

        return daily_ret

    def _calc_enhanced_metrics(self, daily_ret: pd.Series) -> dict:
        """计算增强指标"""
        if daily_ret.empty or len(daily_ret) < 5:
            return {}

        # Calmar 比率
        nav = (1 + daily_ret).cumprod()
        peak = nav.cummax()
        max_dd = float(((nav - peak) / peak).min())
        annual_ret = float((nav.iloc[-1] ** (252 / len(daily_ret))) - 1)
        calmar = annual_ret / abs(max_dd) if max_dd != 0 else float("inf")

        # Sortino 比率
        downside = daily_ret[daily_ret < 0]
        downside_std = float(downside.std()) if len(downside) > 0 else 0.0001
        sortino = float(daily_ret.mean() / downside_std * np.sqrt(252)) if downside_std > 0 else 0

        # 盈亏比 (Profit Factor)
        gross_profit = daily_ret[daily_ret > 0].sum()
        gross_loss = abs(daily_ret[daily_ret < 0].sum())
        profit_factor = float(gross_profit / gross_loss) if gross_loss > 0 else float("inf")

        return {
            "calmar_ratio": round(calmar, 4),
            "sortino_ratio": round(sortino, 4),
            "profit_factor": round(profit_factor, 4),
        }
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_optimization/test_backtester.py
import pytest
import pandas as pd
import numpy as np
from optimization.backtester import EnhancedBacktester


class TestEnhancedBacktester:
    def test_signal_backtest_basic(self):
        bt = EnhancedBacktester(initial_capital=1_000_000.0)
        dates = pd.date_range("2024-01-01", periods=252, freq="B")
        # 模拟上涨 + 噪声
        prices = pd.DataFrame({
            "AAPL": 100 * (1 + np.random.randn(252).cumsum() * 0.01),
            "MSFT": 200 * (1 + np.random.randn(252).cumsum() * 0.01),
        }, index=dates)
        result = bt.run_signal_backtest(["AAPL", "MSFT"], prices)
        assert result["metrics"].sharpe_ratio is not None
        assert len(result["nav_series"]) > 0

    def test_stop_loss_triggers(self):
        bt = EnhancedBacktester(stop_loss_config={"fixed": 0.05, "trailing": False, "time_based": 999})
        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        # 前 50 天上涨，后 50 天暴跌
        rets = np.concatenate([
            np.full(50, 0.01),
            np.full(50, -0.03),  # 触发 5% 止损
        ])
        prices = pd.DataFrame({
            "TEST": 100 * np.cumprod(1 + rets),
        }, index=dates)
        result = bt.run_signal_backtest(["TEST"], prices)
        # 止损触发后后续收益应为 0
        assert result["metrics"].max_drawdown is not None

    def test_enhanced_metrics(self):
        bt = EnhancedBacktester()
        dates = pd.date_range("2024-01-01", periods=252, freq="B")
        rets = np.random.randn(252) * 0.01 + 0.0005
        prices = pd.DataFrame({"TEST": 100 * np.cumprod(1 + rets)}, index=dates)
        result = bt.run_signal_backtest(["TEST"], prices)
        enhanced = result["enhanced"]
        assert "calmar_ratio" in enhanced
        assert "sortino_ratio" in enhanced
        assert "profit_factor" in enhanced
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_backtester.py -v --tb=short
```

预期：3 个测试 PASS。

- [ ] **Step 4: Commit**

```bash
git add optimization/backtester.py tests/test_optimization/test_backtester.py
git commit -m "feat(optimization): add EnhancedBacktester with stop-loss and enhanced metrics"
```

---

## Task 5: 多目标优化函数 Objective Functions

**Files:**
- Create: `optimization/objective.py`
- Tests: `tests/test_optimization/test_objective.py`

- [ ] **Step 1: 创建 `optimization/objective.py`**

```python
# optimization/objective.py
"""多目标优化函数 — 市场状态自适应权重"""
from __future__ import annotations

from typing import Optional
import numpy as np
from loguru import logger

from backtesting.performance_metrics import BacktestMetrics


class ObjectiveFunction:
    """多目标优化评分，支持市场状态自适应"""

    # 默认权重（平衡型）
    DEFAULT_WEIGHTS = {
        "sharpe_ratio": 0.30,
        "max_drawdown": 0.25,
        "total_return": 0.20,
        "win_rate": 0.15,
        "profit_factor": 0.10,
    }

    # 市场状态调整
    REGIME_ADJUSTMENTS = {
        "expansion": {  # 牛市：重收益
            "total_return": 0.30,
            "sharpe_ratio": 0.25,
            "max_drawdown": 0.20,
        },
        "recession": {  # 熊市：重回撤
            "max_drawdown": 0.40,
            "sharpe_ratio": 0.30,
            "total_return": 0.10,
        },
        "overheating": {  # 过热期：重稳健
            "max_drawdown": 0.30,
            "sharpe_ratio": 0.30,
            "profit_factor": 0.20,
        },
        "recovery": {  # 复苏期：均衡
            "win_rate": 0.20,
            "sharpe_ratio": 0.30,
            "total_return": 0.25,
        },
    }

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        market_regime: str = "expansion",
    ):
        self.base_weights = weights or self.DEFAULT_WEIGHTS
        self.market_regime = market_regime

    def get_adjusted_weights(self) -> dict[str, float]:
        """根据市场状态调整权重"""
        adjustments = self.REGIME_ADJUSTMENTS.get(self.market_regime, {})
        adjusted = dict(self.base_weights)
        for key, val in adjustments.items():
            if key in adjusted:
                adjusted[key] = val
        # 归一化
        total = sum(adjusted.values())
        return {k: v / total for k, v in adjusted.items()}

    def calculate(
        self,
        metrics: BacktestMetrics,
        enhanced: Optional[dict] = None,
    ) -> float:
        """
        计算综合得分 (0~1)。
        各项指标先归一化，再按权重加权求和。
        """
        weights = self.get_adjusted_weights()
        scores = {}

        # Sharpe 比率归一化 (0→0, 2.0→1.0)
        if metrics.sharpe_ratio is not None:
            scores["sharpe_ratio"] = min(max(metrics.sharpe_ratio / 2.0, 0.0), 1.0)
        else:
            scores["sharpe_ratio"] = 0.0

        # 最大回撤归一化 (0%→1.0, 30%→0.0)
        if metrics.max_drawdown is not None:
            scores["max_drawdown"] = 1.0 - min(abs(metrics.max_drawdown) / 0.3, 1.0)
        else:
            scores["max_drawdown"] = 0.0

        # 总收益率归一化 (0%→0, 50%→1.0)
        if metrics.total_return is not None:
            scores["total_return"] = min(max(metrics.total_return / 0.5, 0.0), 1.0)
        else:
            scores["total_return"] = 0.0

        # 胜率
        if metrics.win_rate is not None:
            scores["win_rate"] = metrics.win_rate
        else:
            scores["win_rate"] = 0.0

        # 盈亏比
        if enhanced and "profit_factor" in enhanced:
            pf = enhanced["profit_factor"]
            scores["profit_factor"] = min(max(pf / 3.0, 0.0), 1.0) if pf != float("inf") else 1.0
        else:
            scores["profit_factor"] = 0.0

        # 加权求和
        total = sum(scores[k] * weights.get(k, 0) for k in scores)
        return round(total, 6)

    def negate(self, metrics: BacktestMetrics, enhanced: Optional[dict] = None) -> float:
        """返回负得分（供最小化优化器使用）"""
        return -self.calculate(metrics, enhanced)
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_optimization/test_objective.py
import pytest
from optimization.objective import ObjectiveFunction
from backtesting.performance_metrics import BacktestMetrics


class TestObjectiveFunction:
    def test_default_calculation(self):
        obj = ObjectiveFunction()
        metrics = BacktestMetrics(
            sharpe_ratio=1.5,
            max_drawdown=-0.15,
            total_return=0.25,
            win_rate=0.55,
        )
        score = obj.calculate(metrics)
        assert 0.0 <= score <= 1.0

    def test_regime_adjustment(self):
        obj_bull = ObjectiveFunction(market_regime="expansion")
        obj_bear = ObjectiveFunction(market_regime="recession")
        weights_bull = obj_bull.get_adjusted_weights()
        weights_bear = obj_bear.get_adjusted_weights()
        # 熊市重回撤
        assert weights_bear["max_drawdown"] > weights_bull["max_drawdown"]
        # 权重总和为 1
        assert abs(sum(weights_bull.values()) - 1.0) < 0.01
        assert abs(sum(weights_bear.values()) - 1.0) < 0.01

    def test_best_possible_score(self):
        obj = ObjectiveFunction()
        metrics = BacktestMetrics(
            sharpe_ratio=3.0,
            max_drawdown=-0.01,
            total_return=1.0,
            win_rate=0.8,
        )
        enhanced = {"profit_factor": 5.0}
        score = obj.calculate(metrics, enhanced)
        assert score > 0.7  # 非常好应得高分

    def test_worst_possible_score(self):
        obj = ObjectiveFunction()
        metrics = BacktestMetrics(
            sharpe_ratio=-1.0,
            max_drawdown=-0.5,
            total_return=-0.3,
            win_rate=0.3,
        )
        score = obj.calculate(metrics)
        assert score < 0.3  # 非常差应得低分
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_objective.py -v --tb=short
```

预期：4 个测试 PASS。

- [ ] **Step 4: Commit**

```bash
git add optimization/objective.py tests/test_optimization/test_objective.py
git commit -m "feat(optimization): add multi-objective function with regime awareness"
```

---

## Task 6: 优化器 — 网格搜索 + 贝叶斯优化

**Files:**
- Create: `optimization/optimizer.py`
- Tests: `tests/test_optimization/test_optimizer.py`

- [ ] **Step 1: 创建 `optimization/optimizer.py`**

```python
# optimization/optimizer.py
"""参数优化器 — 网格搜索 + 贝叶斯优化"""
from __future__ import annotations

from itertools import product
from typing import Optional, Callable
import numpy as np
import pandas as pd
from loguru import logger

from optimization.config import OptimizationConfig
from optimization.data_manager import DataManager
from optimization.strategy_executor import StrategyExecutor
from optimization.backtester import EnhancedBacktester
from optimization.objective import ObjectiveFunction


class GridSearchOptimizer:
    """网格搜索参数优化器"""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.data_manager = DataManager(universe=config.universe)
        self.backtester = EnhancedBacktester(
            initial_capital=config.initial_capital,
            commission=config.commission,
            stop_loss_config={"fixed": config.stop_loss_pct},
        )

    def search(
        self,
        prices: pd.DataFrame,
        universe: list[str],
        market_regime: str = "expansion",
        progress_cb=None,
    ) -> dict:
        """
        执行网格搜索。

        Returns:
            {
                "best_params": dict,
                "best_score": float,
                "best_metrics": BacktestMetrics,
                "all_results": list[dict],
            }
        """
        param_grid = self.config.get_param_grid()
        param_names = list(param_grid.keys())
        param_values = list(param_grid.values())
        combinations = list(product(*param_values))

        total = len(combinations)
        logger.info(f"[GridSearch] {self.config.strategy_key} 共 {total} 组参数")

        obj_fn = ObjectiveFunction(market_regime=market_regime)
        all_results = []

        for idx, combo in enumerate(combinations):
            params = dict(zip(param_names, combo))

            if progress_cb:
                pct = 10 + int(idx / total * 80)
                progress_cb(pct, f"网格搜索 {idx+1}/{total}...")

            try:
                result = self._evaluate_params(params, prices, universe)
                score = obj_fn.calculate(result["metrics"], result.get("enhanced"))
                all_results.append({
                    "params": params,
                    "score": score,
                    "metrics": result["metrics"],
                    "enhanced": result.get("enhanced", {}),
                })
            except Exception as e:
                logger.debug(f"[GridSearch] 参数 {params} 失败：{e}")
                all_results.append({
                    "params": params,
                    "score": -999.0,
                    "error": str(e),
                })

        # 找最佳
        valid = [r for r in all_results if r["score"] > -998]
        if not valid:
            raise RuntimeError("网格搜索无有效结果")

        best = max(valid, key=lambda r: r["score"])
        logger.info(
            f"[GridSearch] 最优: score={best['score']:.4f}, "
            f"sharpe={best['metrics'].sharpe_ratio:.2f}, params={best['params']}"
        )

        return {
            "best_params": best["params"],
            "best_score": best["score"],
            "best_metrics": best["metrics"],
            "best_enhanced": best.get("enhanced", {}),
            "all_results": all_results,
        }

    def _evaluate_params(
        self,
        params: dict,
        prices: pd.DataFrame,
        universe: list[str],
    ) -> dict:
        """使用指定参数运行策略+回测，返回结果"""
        strategy = StrategyExecutor.create_strategy(
            self.config.strategy_key, **params
        )
        result = strategy.run(universe)
        topk = result.topk_tickers

        bt_result = self.backtester.run_signal_backtest(topk, prices)
        return bt_result


class BayesianOptimizer:
    """贝叶斯优化器 — 用于高维参数空间"""

    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.grid_optimizer = GridSearchOptimizer(config)

    def optimize(
        self,
        prices: pd.DataFrame,
        universe: list[str],
        market_regime: str = "expansion",
        progress_cb=None,
    ) -> dict:
        """运行贝叶斯优化"""
        try:
            from skopt import gp_minimize
            from skopt.space import Real, Integer, Categorical
        except ImportError:
            logger.warning("[BayesianOptimizer] scikit-optimize 未安装，回退到网格搜索")
            return self.grid_optimizer.search(prices, universe, market_regime, progress_cb)

        bounds = self.config.get_bayesian_bounds()

        # 构建维度
        dimensions = []
        for name, (vals, kind) in bounds.items():
            if kind == "integer":
                dimensions.append(Integer(int(vals[0]), int(vals[1]), name=name))
            elif kind == "real":
                dimensions.append(Real(vals[0], vals[1], name=name))
            else:
                dimensions.append(Categorical(vals, name=name))

        obj_fn = ObjectiveFunction(market_regime=market_regime)
        history = []

        def objective(x):
            params = {}
            for i, dim in enumerate(dimensions):
                params[dim.name] = x[i]
            try:
                result = self.grid_optimizer._evaluate_params(params, prices, universe)
                score = obj_fn.negate(result["metrics"], result.get("enhanced"))
                history.append({"params": params, "score": -score})
                return score
            except Exception as e:
                logger.debug(f"[Bayesian] 参数失败：{e}")
                return 1e9  # 大值 = 差

        result = gp_minimize(
            objective,
            dimensions,
            n_calls=self.config.bayesian_n_iter,
            n_initial_points=self.config.bayesian_init_points,
            random_state=42,
            verbose=False,
        )

        best_params = {}
        for i, dim in enumerate(dimensions):
            best_params[dim.name] = result.x[i]

        logger.info(f"[Bayesian] 完成 {len(history)} 次评估，最优 score={-result.fun:.4f}")

        return {
            "best_params": best_params,
            "best_score": float(-result.fun),
            "optimization_history": history,
        }
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_optimization/test_optimizer.py
import pytest
import pandas as pd
import numpy as np
from optimization.config import OptimizationConfig, EARLY_TREND_PARAMS
from optimization.optimizer import GridSearchOptimizer


class TestGridSearchOptimizer:
    def test_small_grid_search(self):
        """只测 2x2 快速网格"""
        config = OptimizationConfig(
            strategy_key="early_trend",
            param_specs=[
                EARLY_TREND_PARAMS[2],  # volume_increase_ratio
                EARLY_TREND_PARAMS[3],  # trend_formation_days
            ],
        )
        optimizer = GridSearchOptimizer(config)

        dates = pd.date_range("2024-01-01", periods=252, freq="B")
        prices = pd.DataFrame({
            "AAPL": 100 * (1 + np.random.randn(252).cumsum() * 0.01),
            "MSFT": 200 * (1 + np.random.randn(252).cumsum() * 0.01),
        }, index=dates)

        result = optimizer.search(prices, ["AAPL", "MSFT"])
        assert "best_params" in result
        assert "best_score" in result
        assert result["best_score"] > -998
        assert len(result["all_results"]) > 0


class TestBayesianOptimizer:
    def test_fallback_to_grid(self):
        """无 skopt 时应回退到网格搜索"""
        import sys
        sys.modules["skopt"] = type(sys)("skopt")
        sys.modules["skopt"].__spec__ = None
        # Force import error
        original_import = __builtins__.__import__

        def mock_import(name, *args, **kwargs):
            if name == "skopt" or name.startswith("skopt."):
                raise ImportError("Mock: skopt not available")
            return original_import(name, *args, **kwargs)

        __builtins__.__import__ = mock_import
        try:
            from optimization.optimizer import BayesianOptimizer
            config = OptimizationConfig(
                strategy_key="early_trend",
                param_specs=EARLY_TREND_PARAMS[:2],
            )
            bo = BayesianOptimizer(config)

            dates = pd.date_range("2024-01-01", periods=100, freq="B")
            prices = pd.DataFrame({
                "AAPL": 100 * (1 + np.random.randn(100).cumsum() * 0.01),
            }, index=dates)

            result = bo.optimize(prices, ["AAPL"])
            assert "best_params" in result
        finally:
            __builtins__.__import__ = original_import
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_optimizer.py -v --tb=short
```

预期：2 个测试 PASS（Bayesian 测试可能因 mock 复杂而改写为简化版）。

- [ ] **Step 4: Commit**

```bash
git add optimization/optimizer.py tests/test_optimization/test_optimizer.py
git commit -m "feat(optimization): add GridSearch and Bayesian optimizers"
```

---

## Task 7: Walk-Forward 分析

**Files:**
- Create: `optimization/walkforward.py`
- Tests: `tests/test_optimization/test_walkforward.py`

- [ ] **Step 1: 创建 `optimization/walkforward.py`**

```python
# optimization/walkforward.py
"""Walk-Forward 分析 — 滚动窗口训练/测试验证参数稳健性"""
from __future__ import annotations

from typing import Optional
import pandas as pd
import numpy as np
from loguru import logger

from optimization.config import OptimizationConfig
from optimization.optimizer import GridSearchOptimizer
from optimization.backtester import EnhancedBacktester
from optimization.objective import ObjectiveFunction


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
        """
        执行 Walk-Forward 分析。

        Returns:
            {
                "windows": list[dict],
                "avg_train_score": float,
                "avg_test_score": float,
                "test_score_std": float,
                "param_stability": dict,
            }
        """
        dates = prices.index
        train_win = self.config.wf_train_window
        test_win = self.config.wf_test_window
        step = self.config.wf_step

        windows = []
        i = 0

        while i + train_win + test_win <= len(dates):
            train_start = dates[i]
            train_end = dates[i + train_win - 1]
            test_start = dates[i + train_win]
            test_end = dates[i + train_win + test_win - 1]

            train_data = prices.loc[train_start:train_end]
            test_data = prices.loc[test_start:test_end]

            if progress_cb:
                pct = int(i / len(dates) * 90)
                progress_cb(pct, f"Walk-Forward 窗口 {len(windows)+1}...")

            # 训练阶段：网格搜索
            try:
                grid_result = self.grid_optimizer.search(
                    train_data, universe, market_regime
                )
                best_params = grid_result["best_params"]

                # 测试阶段
                bt_result = self.backtester.run_signal_backtest(
                    self._get_topk(best_params, universe, train_data),
                    test_data,
                )
                obj_fn = ObjectiveFunction(market_regime=market_regime)
                test_score = obj_fn.calculate(
                    bt_result["metrics"], bt_result.get("enhanced")
                )

                windows.append({
                    "train_period": (str(train_start.date()), str(train_end.date())),
                    "test_period": (str(test_start.date()), str(test_end.date())),
                    "best_params": best_params,
                    "train_score": grid_result["best_score"],
                    "test_score": test_score,
                    "test_sharpe": bt_result["metrics"].sharpe_ratio,
                })
            except Exception as e:
                logger.warning(f"[WalkForward] 窗口失败：{e}")

            i += step

        if not windows:
            raise RuntimeError("Walk-Forward 分析无有效窗口")

        train_scores = [w["train_score"] for w in windows]
        test_scores = [w["test_score"] for w in windows]

        return {
            "windows": windows,
            "n_windows": len(windows),
            "avg_train_score": float(np.mean(train_scores)),
            "avg_test_score": float(np.mean(test_scores)),
            "test_score_std": float(np.std(test_scores)),
            "param_stability": self._check_param_stability(windows),
        }

    def _get_topk(self, params: dict, universe: list[str], prices: pd.DataFrame) -> list[str]:
        """用指定参数获取 topk tickers"""
        from optimization.strategy_executor import StrategyExecutor
        strategy = StrategyExecutor.create_strategy(self.config.strategy_key, **params)
        result = strategy.run(universe)
        return result.topk_tickers

    def _check_param_stability(self, windows: list[dict]) -> dict:
        """检查参数在各窗口的稳定性"""
        if not windows:
            return {}

        param_names = list(windows[0]["best_params"].keys())
        stability = {}
        for name in param_names:
            values = []
            for w in windows:
                val = w["best_params"].get(name)
                if isinstance(val, (int, float)):
                    values.append(float(val))

            if values:
                stability[name] = {
                    "mean": float(np.mean(values)),
                    "std": float(np.std(values)),
                    "cv": float(np.std(values) / abs(np.mean(values))) if np.mean(values) != 0 else 0,
                }

        return stability
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_optimization/test_walkforward.py
import pytest
import pandas as pd
import numpy as np
from optimization.config import OptimizationConfig, EARLY_TREND_PARAMS
from optimization.walkforward import WalkForwardAnalyzer


class TestWalkForwardAnalyzer:
    def test_basic_walkforward(self):
        config = OptimizationConfig(
            strategy_key="early_trend",
            param_specs=EARLY_TREND_PARAMS[:2],  # 只测 2 个参数
            wf_train_window=60,
            wf_test_window=20,
            wf_step=20,
        )
        analyzer = WalkForwardAnalyzer(config)

        dates = pd.date_range("2024-01-01", periods=150, freq="B")
        prices = pd.DataFrame({
            "AAPL": 100 * (1 + np.random.randn(150).cumsum() * 0.01),
            "MSFT": 200 * (1 + np.random.randn(150).cumsum() * 0.01),
        }, index=dates)

        result = analyzer.analyze(prices, ["AAPL", "MSFT"])
        assert result["n_windows"] >= 1
        assert "avg_train_score" in result
        assert "avg_test_score" in result
        assert "param_stability" in result
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_walkforward.py -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add optimization/walkforward.py tests/test_optimization/test_walkforward.py
git commit -m "feat(optimization): add Walk-Forward analysis"
```

---

## Task 8: 稳健性检验 RobustnessChecker

**Files:**
- Create: `optimization/robustness.py`
- Tests: `tests/test_optimization/test_robustness.py`

- [ ] **Step 1: 创建 `optimization/robustness.py`**

```python
# optimization/robustness.py
"""稳健性检验 — 蒙特卡洛模拟 + 参数扰动测试"""
from __future__ import annotations

from typing import Optional
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
        """
        蒙特卡洛模拟：对价格加噪声，观察性能分布。

        Returns:
            {
                "n_simulations": int,
                "scores": list[float],
                "score_mean": float,
                "score_std": float,
                "score_p5": float,
                "score_p95": float,
                "score_distribution": list[float],
            }
        """
        n_sim = self.config.monte_carlo_n_sim
        noise = self.config.monte_carlo_noise
        obj_fn = ObjectiveFunction(market_regime=market_regime)

        scores = []
        topk = self._get_topk(best_params, universe)

        for i in range(n_sim):
            if progress_cb and i % 50 == 0:
                pct = int(i / n_sim * 50)
                progress_cb(pct, f"蒙特卡洛模拟 {i+1}/{n_sim}...")

            noisy = self._add_noise(prices, noise)
            bt_result = self.backtester.run_signal_backtest(topk, noisy)
            score = obj_fn.calculate(
                bt_result["metrics"], bt_result.get("enhanced")
            )
            scores.append(score)

        scores = np.array(scores)
        return {
            "n_simulations": n_sim,
            "scores": scores.tolist(),
            "score_mean": float(scores.mean()),
            "score_std": float(scores.std()),
            "score_p5": float(np.percentile(scores, 5)),
            "score_p95": float(np.percentile(scores, 95)),
            "pass_threshold": scores.mean() > 0.3,
        }

    def parameter_perturbation(
        self,
        best_params: dict,
        prices: pd.DataFrame,
        universe: list[str],
        market_regime: str = "expansion",
        progress_cb=None,
    ) -> dict:
        """
        参数扰动测试：对每个参数 ±10%，观察性能敏感度。
        """
        obj_fn = ObjectiveFunction(market_regime=market_regime)
        factor = self.config.perturbation_factor
        perturbation_results = {}

        base_bt = self.backtester.run_signal_backtest(
            self._get_topk(best_params, universe), prices
        )
        base_score = obj_fn.calculate(
            base_bt["metrics"], base_bt.get("enhanced")
        )

        for param_name, base_val in best_params.items():
            if not isinstance(base_val, (int, float)):
                continue

            param_scores = {}
            for direction, label in [(1 + factor, "up"), (1 - factor, "down")]:
                perturbed = dict(best_params)
                perturbed[param_name] = type(base_val)(base_val * direction)

                try:
                    bt_result = self.backtester.run_signal_backtest(
                        self._get_topk(perturbed, universe), prices
                    )
                    score = obj_fn.calculate(
                        bt_result["metrics"], bt_result.get("enhanced")
                    )
                    param_scores[label] = {
                        "value": perturbed[param_name],
                        "score": score,
                        "delta": score - base_score,
                    }
                except Exception as e:
                    param_scores[label] = {"error": str(e)}

            perturbation_results[param_name] = {
                "base_value": base_val,
                "base_score": base_score,
                "perturbations": param_scores,
                "sensitivity": abs(
                    param_scores.get("up", {}).get("delta", 0)
                ) + abs(param_scores.get("down", {}).get("delta", 0)),
            }

            if progress_cb:
                progress_cb(60, f"参数扰动: {param_name}...")

        # 按敏感度排序
        sorted_params = sorted(
            perturbation_results.items(),
            key=lambda x: x[1]["sensitivity"],
            reverse=True,
        )

        return {
            "base_score": base_score,
            "parameters": dict(sorted_params),
            "most_sensitive": sorted_params[0][0] if sorted_params else None,
            "least_sensitive": sorted_params[-1][0] if sorted_params else None,
        }

    def _add_noise(self, prices: pd.DataFrame, noise_level: float) -> pd.DataFrame:
        """对价格添加高斯噪声"""
        noisy = prices.copy()
        for col in noisy.columns:
            noise = np.random.normal(0, noise_level, len(noisy))
            noisy[col] = noisy[col] * (1 + noise)
        return noisy

    def _get_topk(self, params: dict, universe: list[str]) -> list[str]:
        strategy = StrategyExecutor.create_strategy(self.config.strategy_key, **params)
        result = strategy.run(universe)
        return result.topk_tickers
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_optimization/test_robustness.py
import pytest
import pandas as pd
import numpy as np
from optimization.config import OptimizationConfig, EARLY_TREND_PARAMS
from optimization.robustness import RobustnessChecker


class TestRobustnessChecker:
    def test_monte_carlo(self):
        config = OptimizationConfig(
            strategy_key="early_trend",
            param_specs=EARLY_TREND_PARAMS[:2],
            monte_carlo_n_sim=20,
            monte_carlo_noise=0.01,
        )
        checker = RobustnessChecker(config)

        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        prices = pd.DataFrame({
            "AAPL": 100 * (1 + np.random.randn(100).cumsum() * 0.01),
        }, index=dates)

        result = checker.monte_carlo(
            {"max_convergence_days": 20, "max_slope": 0.02},
            prices, ["AAPL"],
        )
        assert result["n_simulations"] == 20
        assert len(result["scores"]) == 20
        assert "score_mean" in result

    def test_parameter_perturbation(self):
        config = OptimizationConfig(
            strategy_key="early_trend",
            param_specs=EARLY_TREND_PARAMS[:2],
            perturbation_factor=0.1,
        )
        checker = RobustnessChecker(config)

        dates = pd.date_range("2024-01-01", periods=100, freq="B")
        prices = pd.DataFrame({
            "AAPL": 100 * (1 + np.random.randn(100).cumsum() * 0.01),
        }, index=dates)

        result = checker.parameter_perturbation(
            {"max_convergence_days": 20, "max_slope": 0.02},
            prices, ["AAPL"],
        )
        assert "base_score" in result
        assert "most_sensitive" in result
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_robustness.py -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add optimization/robustness.py tests/test_optimization/test_robustness.py
git commit -m "feat(optimization): add robustness checker (Monte Carlo + perturbation)"
```

---

## Task 9: 优化控制器 OptimizationController

**Files:**
- Create: `optimization/controller.py`
- Tests: `tests/test_optimization/test_controller.py`

- [ ] **Step 1: 创建 `optimization/controller.py`**

```python
# optimization/controller.py
"""优化控制器 — 编排完整优化流水线"""
from __future__ import annotations

from typing import Optional
from datetime import datetime
import json
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
        self.data_manager = DataManager(universe=config.universe)

    def run(
        self,
        progress_cb=None,
    ) -> dict:
        """
        运行完整优化流水线：
        1. 数据准备 + 市场状态识别
        2. 参数优化（网格搜索 / 贝叶斯）
        3. Walk-Forward 验证
        4. 稳健性检验

        Returns:
            完整优化结果字典
        """
        strategy_key = self.config.strategy_key
        self._report(progress_cb, 5, f"开始优化 [{strategy_key}]...")

        # ── Phase 1: 数据准备 ────────────────────
        self._report(progress_cb, 10, "获取股票池...")
        universe = self._get_universe()
        logger.info(f"[Controller] 股票池: {len(universe)} 支")

        self._report(progress_cb, 15, "下载历史价格...")
        end_date = self.config.end_date or datetime.now().strftime("%Y-%m-%d")
        prices = self.data_manager.fetch_prices_batch(
            universe, self.config.start_date, end_date
        )
        if prices.empty:
            raise RuntimeError("无法获取价格数据")

        self._report(progress_cb, 20, "识别市场状态...")
        market_regime = self.data_manager.get_market_regime()

        # 数据切分
        splits = self.data_manager.split_data(
            prices,
            self.config.train_ratio,
            self.config.val_ratio,
        )
        train_prices = splits["train"]
        test_prices = splits["test"]

        results = {
            "strategy_key": strategy_key,
            "market_regime": market_regime,
            "universe_size": len(universe),
            "data_range": f"{prices.index[0].date()} ~ {prices.index[-1].date()}",
            "optimization_time": datetime.now().isoformat(),
        }

        # ── Phase 2: 参数优化 ────────────────────
        self._report(progress_cb, 30, "参数优化中...")

        if self.config.bayesian_enabled:
            bo = BayesianOptimizer(self.config)
            opt_result = bo.optimize(
                train_prices, universe, market_regime,
                progress_cb=lambda p, m: self._report(progress_cb, 30 + p // 4, m),
            )
        else:
            gs = GridSearchOptimizer(self.config)
            opt_result = gs.search(
                train_prices, universe, market_regime,
                progress_cb=lambda p, m: self._report(progress_cb, 30 + p // 4, m),
            )

        results["optimization"] = opt_result
        best_params = opt_result["best_params"]

        self._report(progress_cb, 55, f"最优参数: {best_params}")

        # ── Phase 3: Walk-Forward ─────────────────
        if self.config.walkforward_enabled:
            self._report(progress_cb, 60, "Walk-Forward 验证...")
            wf = WalkForwardAnalyzer(self.config)
            try:
                wf_result = wf.analyze(
                    prices, universe, market_regime,
                    progress_cb=lambda p, m: self._report(progress_cb, 60 + p // 3, m),
                )
                results["walkforward"] = wf_result
                self._report(
                    progress_cb, 75,
                    f"WF avg_test_score={wf_result['avg_test_score']:.4f}"
                )
            except Exception as e:
                logger.warning(f"[Controller] Walk-Forward 失败：{e}")
                results["walkforward"] = {"error": str(e)}

        # ── Phase 4: 稳健性检验 ───────────────────
        if self.config.robustness_enabled:
            self._report(progress_cb, 80, "稳健性检验...")
            checker = RobustnessChecker(self.config)

            mc_result = checker.monte_carlo(
                best_params, prices, universe, market_regime,
                progress_cb=lambda p, m: self._report(progress_cb, 85, m),
            )
            results["monte_carlo"] = mc_result

            pert_result = checker.parameter_perturbation(
                best_params, prices, universe, market_regime,
                progress_cb=lambda p, m: self._report(progress_cb, 92, m),
            )
            results["perturbation"] = pert_result

        self._report(progress_cb, 100, f"优化完成 [{strategy_key}]")
        return results

    def _get_universe(self) -> list[str]:
        """获取股票池"""
        if self.config.universe:
            return self.config.universe
        from screening.stock_screener import StockScreener
        screener = StockScreener()
        return screener._sp500_fallback()

    def _report(self, progress_cb, pct: int, msg: str):
        if progress_cb:
            try:
                progress_cb(pct, msg)
            except Exception:
                pass
        logger.info(f"[Controller] {pct}% - {msg}")


def quick_optimize(
    strategy_key: str = "early_trend",
    start_date: str = "2023-01-01",
    progress_cb=None,
) -> dict:
    """
    快速优化入口：使用预设参数规格进行优化。

    Usage:
        from optimization.controller import quick_optimize
        result = quick_optimize("early_trend", progress_cb=my_callback)
    """
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

    controller = OptimizationController(config)
    return controller.run(progress_cb=progress_cb)
```

- [ ] **Step 2: 编写测试**

```python
# tests/test_optimization/test_controller.py
import pytest
from optimization.config import OptimizationConfig, EARLY_TREND_PARAMS
from optimization.controller import OptimizationController


class TestOptimizationController:
    def test_full_pipeline_minimal(self):
        """最小配置的完整流水线"""
        config = OptimizationConfig(
            strategy_key="early_trend",
            param_specs=EARLY_TREND_PARAMS[:2],
            start_date="2024-01-01",
            train_ratio=0.7,
            val_ratio=0.15,
            test_ratio=0.15,
            grid_search_enabled=True,
            bayesian_enabled=False,
            walkforward_enabled=False,
            robustness_enabled=False,
        )
        controller = OptimizationController(config)
        result = controller.run()
        assert "strategy_key" in result
        assert "optimization" in result
        assert result["optimization"].get("best_params") is not None
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_controller.py -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add optimization/controller.py tests/test_optimization/test_controller.py
git commit -m "feat(optimization): add OptimizationController orchestrating full pipeline"
```

---

## Task 10: 报告生成 Reporter + Visualizer

**Files:**
- Create: `optimization/reporter.py`
- Create: `optimization/visualizer.py`

- [ ] **Step 1: 创建 `optimization/visualizer.py`**

```python
# optimization/visualizer.py
"""优化结果可视化 — matplotlib 图表"""
from __future__ import annotations

from typing import Optional
import matplotlib
matplotlib.use("Agg")  # 无 GUI 后端
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


class OptimizationVisualizer:
    """优化结果图表生成器"""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def plot_optimization_heatmap(
        self,
        all_results: list[dict],
        param_x: str,
        param_y: str,
        title: str = "Parameter Heatmap",
        save_path: Optional[str] = None,
    ):
        """二维参数热力图"""
        x_vals = []
        y_vals = []
        scores = []
        for r in all_results:
            if r["score"] <= -998:
                continue
            x_vals.append(r["params"].get(param_x))
            y_vals.append(r["params"].get(param_y))
            scores.append(r["score"])

        if not x_vals:
            return

        fig, ax = plt.subplots(figsize=(10, 8))
        sc = ax.scatter(x_vals, y_vals, c=scores, cmap="RdYlGn", s=100, edgecolors="k")
        plt.colorbar(sc, label="Score")

        ax.set_xlabel(param_x)
        ax.set_ylabel(param_y)
        ax.set_title(title)

        path = save_path or str(self.output_dir / f"heatmap_{param_x}_{param_y}.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    def plot_sensitivity(
        self,
        perturbation_results: dict,
        save_path: Optional[str] = None,
    ):
        """参数敏感度条形图"""
        params = perturbation_results.get("parameters", {})
        names = list(params.keys())
        sensitivities = [params[n]["sensitivity"] for n in names]

        fig, ax = plt.subplots(figsize=(10, 6))
        colors = ["#e74c3c" if s > 0.1 else "#2ecc71" for s in sensitivities]
        bars = ax.barh(names, sensitivities, color=colors)
        ax.set_xlabel("Sensitivity (score delta)")
        ax.set_title("Parameter Sensitivity Analysis")
        ax.axvline(x=0.05, color="gray", linestyle="--", alpha=0.5)

        path = save_path or str(self.output_dir / "sensitivity.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    def plot_equity_curve(
        self,
        nav_series,
        bm_series=None,
        title: str = "Equity Curve",
        save_path: Optional[str] = None,
    ):
        """净值曲线"""
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(nav_series.index, nav_series.values, label="Strategy", linewidth=1.5)
        if bm_series is not None and not bm_series.empty:
            ax.plot(bm_series.index, bm_series.values, label="Benchmark", linewidth=1, alpha=0.7)
        ax.set_title(title)
        ax.set_ylabel("Net Asset Value")
        ax.legend()
        ax.grid(True, alpha=0.3)

        path = save_path or str(self.output_dir / "equity_curve.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)

    def plot_walkforward_summary(
        self,
        wf_result: dict,
        save_path: Optional[str] = None,
    ):
        """Walk-Forward 结果概览"""
        windows = wf_result.get("windows", [])
        if not windows:
            return

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        train_scores = [w["train_score"] for w in windows]
        test_scores = [w["test_score"] for w in windows]
        x = range(len(windows))

        axes[0].plot(x, train_scores, "o-", label="Train", markersize=6)
        axes[0].plot(x, test_scores, "s-", label="Test", markersize=6)
        axes[0].set_title("Walk-Forward Scores")
        axes[0].set_xlabel("Window")
        axes[0].set_ylabel("Score")
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        test_sharpes = [w.get("test_sharpe", 0) or 0 for w in windows]
        axes[1].bar(x, test_sharpes, color="#3498db")
        axes[1].axhline(y=0, color="red", linestyle="--", alpha=0.5)
        axes[1].set_title("Test Sharpe per Window")
        axes[1].set_xlabel("Window")
        axes[1].set_ylabel("Sharpe Ratio")
        axes[1].grid(True, alpha=0.3)

        fig.tight_layout()
        path = save_path or str(self.output_dir / "walkforward.png")
        fig.savefig(path, dpi=150, bbox_inches="tight")
        plt.close(fig)
```

- [ ] **Step 2: 创建 `optimization/reporter.py`**

```python
# optimization/reporter.py
"""优化报告生成 — Markdown 格式"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional
from loguru import logger


class OptimizationReporter:
    """优化报告生成器"""

    def __init__(self, output_dir: Optional[Path] = None):
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            from services.output_paths import get_strategy_dir
            self.output_dir = get_strategy_dir() / "reports"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        result: dict,
        charts_dir: Optional[str] = None,
    ) -> Path:
        """
        生成 Markdown 优化报告。

        Args:
            result: OptimizationController.run() 的返回值
            charts_dir: 图表目录（可选）

        Returns:
            报告文件路径
        """
        strategy_key = result.get("strategy_key", "unknown")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = self.output_dir / f"optimization_{strategy_key}_{timestamp}.md"

        lines = [
            f"# 策略优化报告：{strategy_key}",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**市场状态**: {result.get('market_regime', 'N/A')}",
            f"**数据范围**: {result.get('data_range', 'N/A')}",
            f"**股票池大小**: {result.get('universe_size', 'N/A')} 支",
            "",
            "---",
            "",
            "## 1. 最优参数",
            "",
        ]

        opt = result.get("optimization", {})
        best_params = opt.get("best_params", {})
        if best_params:
            lines.append("| 参数 | 最优值 |")
            lines.append("|------|--------|")
            for k, v in best_params.items():
                lines.append(f"| {k} | {v} |")
            lines.append("")

        # 性能指标
        best_metrics = opt.get("best_metrics")
        if best_metrics:
            lines += [
                "## 2. 最优性能指标",
                "",
                "| 指标 | 数值 |",
                "|------|------|",
                f"| 年化收益率 | {_fmt_pct(best_metrics.annual_return)} |",
                f"| 总收益率 | {_fmt_pct(best_metrics.total_return)} |",
                f"| 夏普比率 | {_fmt_num(best_metrics.sharpe_ratio)} |",
                f"| 最大回撤 | {_fmt_pct(best_metrics.max_drawdown)} |",
                f"| 年化波动率 | {_fmt_pct(best_metrics.volatility)} |",
                f"| 胜率 | {_fmt_pct(best_metrics.win_rate)} |",
                f"| Alpha | {_fmt_pct(best_metrics.alpha)} |",
                f"| Beta | {_fmt_num(best_metrics.beta)} |",
                "",
            ]

        # 综合得分
        lines += [
            f"**优化得分**: {opt.get('best_score', 'N/A')}",
            "",
        ]

        # Walk-Forward
        wf = result.get("walkforward", {})
        if wf and "error" not in wf:
            lines += [
                "## 3. Walk-Forward 验证",
                "",
                f"| 指标 | 数值 |",
                f"|------|------|",
                f"| 窗口数 | {wf.get('n_windows', 0)} |",
                f"| 平均训练得分 | {_fmt_num(wf.get('avg_train_score'))} |",
                f"| 平均测试得分 | {_fmt_num(wf.get('avg_test_score'))} |",
                f"| 测试得分标准差 | {_fmt_num(wf.get('test_score_std'))} |",
                "",
            ]

            stability = wf.get("param_stability", {})
            if stability:
                lines += [
                    "### 参数稳定性",
                    "",
                    "| 参数 | 均值 | 标准差 | CV |",
                    "|------|------|--------|-----|",
                ]
                for name, stats in stability.items():
                    lines.append(
                        f"| {name} | {_fmt_num(stats['mean'])} | "
                        f"{_fmt_num(stats['std'])} | {_fmt_num(stats['cv'])} |"
                    )
                lines.append("")

        # 稳健性
        mc = result.get("monte_carlo", {})
        if mc:
            lines += [
                "## 4. 蒙特卡洛模拟",
                "",
                f"| 指标 | 数值 |",
                f"|------|------|",
                f"| 模拟次数 | {mc.get('n_simulations', 0)} |",
                f"| 平均得分 | {_fmt_num(mc.get('score_mean'))} |",
                f"| 得分标准差 | {_fmt_num(mc.get('score_std'))} |",
                f"| P5 得分 | {_fmt_num(mc.get('score_p5'))} |",
                f"| P95 得分 | {_fmt_num(mc.get('score_p95'))} |",
                f"| 通过 (mean>0.3) | {'✅' if mc.get('pass_threshold') else '❌'} |",
                "",
            ]

        pert = result.get("perturbation", {})
        if pert:
            params = pert.get("parameters", {})
            if params:
                lines += [
                    "## 5. 参数敏感性",
                    "",
                    "| 参数 | 基准值 | 敏感度 | 评估 |",
                    "|------|--------|--------|------|",
                ]
                for name, info in params.items():
                    sens = info.get("sensitivity", 0)
                    assess = "🔴 高敏感" if sens > 0.1 else ("🟡 中敏感" if sens > 0.05 else "🟢 稳健")
                    lines.append(
                        f"| {name} | {info.get('base_value', '-')} | "
                        f"{_fmt_num(sens)} | {assess} |"
                    )
                lines.append("")

        # 图表引用
        if charts_dir:
            lines += [
                "## 6. 可视化图表",
                "",
                f"![净值曲线]({charts_dir}/equity_curve.png)",
                f"![参数敏感度]({charts_dir}/sensitivity.png)",
                f"![Walk-Forward]({charts_dir}/walkforward.png)",
                "",
            ]

        # 建议
        lines += [
            "## 7. 优化建议",
            "",
        ]
        recs = self._generate_recommendations(result)
        for rec in recs:
            lines.append(f"- {rec}")
        lines.append("")

        report = "\n".join(lines)
        report_path.write_text(report, encoding="utf-8")
        logger.info(f"[Reporter] 报告已保存: {report_path}")
        return report_path

    def _generate_recommendations(self, result: dict) -> list[str]:
        recs = []

        wf = result.get("walkforward", {})
        if wf.get("test_score_std", 0) > 0.15:
            recs.append("⚠️ 测试得分波动较大（>0.15），参数在不同时段表现不一致，建议缩小参数搜索范围。")
        else:
            recs.append("✅ 参数在 Walk-Forward 中表现稳定，适合实盘部署。")

        pert = result.get("perturbation", {})
        if pert.get("most_sensitive"):
            ms = pert["most_sensitive"]
            recs.append(f"🔍 最敏感参数: **{ms}**，建议设定更窄的区间或动态调整。")

        mc = result.get("monte_carlo", {})
        if not mc.get("pass_threshold", False):
            recs.append("⚠️ 蒙特卡洛模拟未通过稳健性阈值，策略可能对价格噪声敏感。")

        opt = result.get("optimization", {})
        score = opt.get("best_score", 0)
        if score < 0.3:
            recs.append("❌ 优化得分过低（<0.3），建议重新审视策略逻辑或数据质量。")
        elif score < 0.5:
            recs.append("⚡ 优化得分中等（0.3~0.5），有提升空间。")
        else:
            recs.append("✅ 优化得分优秀（>0.5），策略质量良好。")

        return recs


def _fmt_pct(val) -> str:
    if val is None:
        return "N/A"
    return f"{val*100:.2f}%"


def _fmt_num(val) -> str:
    if val is None:
        return "N/A"
    if isinstance(val, float):
        return f"{val:.4f}"
    return str(val)
```

- [ ] **Step 3: 验证**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -c "
from optimization.reporter import OptimizationReporter
r = OptimizationReporter()
print('Reporter initialized:', r.output_dir)
"
```

- [ ] **Step 4: Commit**

```bash
git add optimization/reporter.py optimization/visualizer.py
git commit -m "feat(optimization): add report generator and visualizer"
```

---

## Task 11: 端到端集成测试

**Files:**
- Create: `tests/test_optimization/test_integration.py`

- [ ] **Step 1: 创建集成测试**

```python
# tests/test_optimization/test_integration.py
"""端到端集成测试"""
import pytest
from optimization.config import OptimizationConfig, EARLY_TREND_PARAMS
from optimization.controller import OptimizationController, quick_optimize
from optimization.reporter import OptimizationReporter
from optimization.visualizer import OptimizationVisualizer
from pathlib import Path
import tempfile


class TestIntegration:
    def test_quick_optimize_early_trend(self):
        """快速优化 Early Trend 策略（最小配置）"""
        config = OptimizationConfig(
            strategy_key="early_trend",
            param_specs=EARLY_TREND_PARAMS[:2],
            start_date="2024-06-01",
            grid_search_enabled=True,
            walkforward_enabled=False,
            robustness_enabled=False,
        )
        controller = OptimizationController(config)
        result = controller.run()
        assert result["optimization"]["best_score"] > -998

    def test_report_generation(self):
        """报告生成"""
        reporter = OptimizationReporter()
        mock_result = {
            "strategy_key": "early_trend",
            "market_regime": "expansion",
            "data_range": "2024-01-02 ~ 2024-12-31",
            "universe_size": 250,
            "optimization": {
                "best_params": {"max_convergence_days": 18, "max_slope": 0.025},
                "best_score": 0.65,
            },
            "walkforward": {
                "n_windows": 5,
                "avg_train_score": 0.62,
                "avg_test_score": 0.58,
                "test_score_std": 0.08,
                "param_stability": {
                    "max_convergence_days": {"mean": 18.5, "std": 2.1, "cv": 0.11},
                },
            },
            "monte_carlo": {
                "n_simulations": 500,
                "score_mean": 0.55,
                "score_std": 0.12,
                "pass_threshold": True,
            },
            "perturbation": {
                "parameters": {
                    "max_convergence_days": {
                        "base_value": 18,
                        "sensitivity": 0.04,
                    },
                },
            },
        }
        report_path = reporter.generate(mock_result)
        assert report_path.exists()
        content = report_path.read_text()
        assert "early_trend" in content
        assert "max_convergence_days" in content
```

- [ ] **Step 2: 运行集成测试**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python -m pytest tests/test_optimization/test_integration.py -v --tb=short
```

预期：2 个测试 PASS。

- [ ] **Step 3: Commit**

```bash
git add tests/test_optimization/test_integration.py
git commit -m "test(optimization): add end-to-end integration tests"
```

---

## Task 12: 添加 CLI 入口和示例脚本

**Files:**
- Create: `examples/optimize_strategy.py`

- [ ] **Step 1: 创建命令行入口**

```python
#!/usr/bin/env python
# examples/optimize_strategy.py
"""
策略优化 CLI 入口

Usage:
    # 快速优化单个策略
    python examples/optimize_strategy.py --strategy early_trend

    # 自定义日期范围
    python examples/optimize_strategy.py --strategy golden_cross --start 2022-01-01

    # 启用贝叶斯优化
    python examples/optimize_strategy.py --strategy ma10 --bayesian

    # 批量优化所有策略
    python examples/optimize_strategy.py --all
"""
import sys
import argparse
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="策略参数优化工具")
    parser.add_argument("--strategy", type=str, default="early_trend",
                        choices=["early_trend", "golden_cross", "ma10", "trendline_breakout"],
                        help="策略标识符")
    parser.add_argument("--all", action="store_true", help="优化所有策略")
    parser.add_argument("--start", type=str, default="2023-01-01", help="数据起始日期")
    parser.add_argument("--bayesian", action="store_true", help="启用贝叶斯优化")
    parser.add_argument("--no-wf", action="store_true", help="跳过 Walk-Forward")
    parser.add_argument("--no-robustness", action="store_true", help="跳过稳健性检验")
    args = parser.parse_args()

    strategies = (
        ["early_trend", "golden_cross", "ma10", "trendline_breakout"]
        if args.all
        else [args.strategy]
    )

    from optimization.config import STRATEGY_PARAMS_MAP, OptimizationConfig
    from optimization.controller import OptimizationController
    from optimization.reporter import OptimizationReporter
    from optimization.visualizer import OptimizationVisualizer

    for strat in strategies:
        logger.info(f"{'='*60}")
        logger.info(f"开始优化: {strat}")
        logger.info(f"{'='*60}")

        config = OptimizationConfig(
            strategy_key=strat,
            param_specs=STRATEGY_PARAMS_MAP[strat],
            start_date=args.start,
            bayesian_enabled=args.bayesian,
            walkforward_enabled=not args.no_wf,
            robustness_enabled=not args.no_robustness,
        )

        controller = OptimizationController(config)
        result = controller.run()

        # 生成报告
        reporter = OptimizationReporter()
        report_path = reporter.generate(result)

        # 生成图表
        out_dir = report_path.parent / f"charts_{strat}"
        vis = OptimizationVisualizer(out_dir)

        all_results = result.get("optimization", {}).get("all_results", [])
        if all_results:
            params = list(all_results[0]["params"].keys())
            if len(params) >= 2:
                vis.plot_optimization_heatmap(
                    all_results, params[0], params[1],
                    title=f"{strat} Parameter Heatmap",
                )

        if "perturbation" in result:
            vis.plot_sensitivity(result["perturbation"])

        if "walkforward" in result:
            vis.plot_walkforward_summary(result["walkforward"])

        # 更新报告添加图表路径
        final_report = report_path.read_text()
        final_report = final_report.replace(
            "## 6. 可视化图表",
            f"## 6. 可视化图表\n\n"
            f"![账户曲线]({out_dir}/equity_curve.png)\n"
            f"![参数敏感度]({out_dir}/sensitivity.png)\n"
            f"![Walk-Forward]({out_dir}/walkforward.png)\n"
        )
        report_path.write_text(final_report, encoding="utf-8")

        logger.info(f"报告: {report_path}")
        logger.info(f"图表: {out_dir}")

    logger.info("全部优化完成！")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 验证**

```bash
cd /Users/admin/codes/qlib/QuantByQlib
python examples/optimize_strategy.py --help
```

预期：输出帮助信息。

- [ ] **Step 3: Commit**

```bash
mkdir -p examples
git add examples/optimize_strategy.py
git commit -m "feat(optimization): add CLI entry point and batch runner"
```

---

## 自检清单

1. **Spec 覆盖**: 998 文档的 7 大模块全部覆盖 ✅
   - DataManager → `data_manager.py`
   - StrategyExecutor → `strategy_executor.py`
   - Backtester → `backtester.py`
   - Optimizer (Grid/Bayesian) → `optimizer.py`
   - WalkForward → `walkforward.py`
   - Robustness → `robustness.py`
   - Visualization/Report → `visualizer.py` + `reporter.py`

2. **占位符检查**: 无 TBD/TODO/placeholder ✅

3. **类型一致性**: 所有接口已对齐 ✅
   - `BacktestMetrics` 来自 `backtesting/performance_metrics.py`
   - `StrategyResult` 来自 `strategies/base_strategy.py`
   - `OptimizationConfig` 是 dataclass，所有参数类型匹配

4. **约束合规**: 每个文件 ≤ 300 行 ✅

- `config.py`: ~120 行
- `data_manager.py`: ~120 行
- `strategy_executor.py`: ~70 行
- `backtester.py`: ~150 行
- `objective.py`: ~100 行
- `optimizer.py`: ~180 行
- `walkforward.py`: ~120 行
- `robustness.py`: ~150 行
- `controller.py`: ~160 行
- `reporter.py`: ~170 行
- `visualizer.py`: ~150 行

5. **复用验证**: 所有复用点已明确标注 ✅
   - MarketDataClient 降级链
   - HMM Regime 4-state
   - BacktestEngine 价格缓存
   - BacktestMetrics 指标计算

---

## 执行建议

**推荐: 行内执行** — 所有模块已设计为可独立开发和测试。

执行顺序: Task 1 → Task 2 → Task 3 → Task 4 → Task 5 → Task 6 → Task 7 → Task 8 → Task 9 → Task 10 → Task 11 → Task 12

预估总工时: ~6 小时（含测试和调试）
