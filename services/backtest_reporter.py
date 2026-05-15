"""
F4：策略回测绩效报告生成
针对三个策略 + 2+1 组合，运行回测并汇总输出到：
  美股交易日记/backtest/performance_{YYYYMMDD}.json

触发时机：每月最后一个交易日（由 daily_export_worker 判断日期后调用）

输出 JSON Schema 见规格书 §F4。
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional, Callable

import pandas as pd
from loguru import logger


# ── 策略配置 ────────────────────────────────────────────────────────────────

_STRATEGY_CONFIGS = [
    {
        "key":   "deep_learning",
        "num":   1,
        "name":  "LSTM Alpha158 504d",
        "model": "LSTM",
    },
    {
        "key":   "intraday_profit",
        "num":   2,
        "name":  "GRU Top30 126d",
        "model": "GRU",
    },
    {
        "key":   "growth_stocks",
        "num":   3,
        "name":  "LightGBM RD-Agent",
        "model": "LGBModel",
    },
]


def run_backtest_report(
    trade_date: Optional[date] = None,
    universe: Optional[list[str]] = None,
    output_dir: Optional[Path] = None,
    progress_cb: Optional[Callable[[int, str], None]] = None,
) -> Path:
    """
    运行三策略回测，生成绩效 JSON。

    Parameters
    ----------
    trade_date  : 报告日期标签（默认今日）
    universe    : 候选股票列表（None = Qlib 自动获取）
    output_dir  : 输出目录（默认 services.output_paths.get_backtest_dir()）
    progress_cb : 进度回调 (pct, msg)
    """
    from services.output_paths import get_backtest_dir, backtest_filename

    d = trade_date or date.today()
    out_dir = output_dir or get_backtest_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    def _cb(pct, msg):
        logger.info(f"[BacktestReport] {pct}% {msg}")
        if progress_cb:
            progress_cb(pct, msg)

    _cb(5, "开始月度回测绩效报告生成...")

    # 回测时间窗口：近一年
    end_date   = d.isoformat()
    start_date = (d - timedelta(days=365)).isoformat()
    from core.app_state import get_state
    reg = get_state().reg
    benchmark_ticker = "SPY" if reg != "bt" else "BTCUSDT"

    strategies_data = {}
    errors: list[str] = []

    # ── 逐策略回测 ────────────────────────────────────────────────────────
    total = len(_STRATEGY_CONFIGS)
    for i, cfg in enumerate(_STRATEGY_CONFIGS):
        key  = cfg["key"]
        name = cfg["name"]
        num  = cfg["num"]
        pct_base = 10 + int(i / total * 70)

        _cb(pct_base, f"回测策略 {i+1}/{total}: {name}...")

        try:
            metrics = _run_single_strategy_backtest(
                strategy_key=key,
                start_date=start_date,
                end_date=end_date,
                universe=universe,
            )
            s_id = f"strategy{num}"
            strategies_data[s_id] = _format_strategy_entry(name, metrics, key, num)
            _cb(pct_base + int(70 / total) - 2, f"{name} 回测完成")

        except Exception as e:
            err_msg = f"{name} 回测失败：{e}"
            logger.error(f"[BacktestReport] {err_msg}")
            errors.append(err_msg)
            s_id = f"strategy{num}"
            strategies_data[s_id] = _empty_strategy_entry(name)

    # ── 组合绩效（简单加权平均）────────────────────────────────────────────
    _cb(83, "计算三策略 2+1 组合绩效...")
    strategies_data["combined_2plus1"] = _compute_combined(strategies_data)

    # ── 基准数据 ──────────────────────────────────────────────────────────
    _cb(90, "获取基准（SPY）数据...")
    benchmark = _get_benchmark_metrics(benchmark_ticker, start_date, end_date)

    payload = {
        "date":       d.isoformat(),
        "strategies": strategies_data,
        "benchmark":  benchmark,
        "errors":     errors,
    }

    out_path = out_dir / backtest_filename(d)
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _cb(100, f"绩效报告已写入 → {out_path}")
    return out_path


# ── 单策略回测 ────────────────────────────────────────────────────────────────

def _run_single_strategy_backtest(
    strategy_key: str,
    start_date: str,
    end_date: str,
    universe: Optional[list[str]] = None,
) -> dict:
    """
    运行单个策略的 Qlib 回测，返回绩效指标字典。
    若 Qlib 不可用，返回 yfinance 规则打分的近似绩效。
    """
    try:
        from backtesting.backtest_engine import BacktestEngine, BacktestConfig
        config = BacktestConfig(
            strategy_key=strategy_key,
            start_date=start_date,
            end_date=end_date,
            universe=universe,
        )
        
        from core.app_state import get_state
        if get_state().reg == "bt" and config.benchmark == "SPY":
            config.benchmark = "BTCUSDT"
            
        engine = BacktestEngine()
        report = engine.run(config)
        m = report.metrics
        return {
            "sharpe_ratio":              round(m.sharpe_ratio or 0, 3),
            "max_drawdown":              round(m.max_drawdown or 0, 3),
            "annual_return":             round(m.annual_return or 0, 3),
            "win_rate":                  round(m.win_rate or 0, 3),
            "information_coefficient_30d": round(m.ic_mean or 0, 3),
            "recent_30d_return":         _recent_return(report, days=30),
            "recent_30d_alpha":          _recent_alpha(report, days=30),
        }
    except Exception as e:
        logger.warning(f"[BacktestReport] Qlib 回测失败，降级到空值：{e}")
        return {}


def _recent_return(report, days: int = 30) -> float:
    """提取近 N 天累计收益"""
    try:
        rets = report.daily_returns
        if rets is not None and len(rets) >= days:
            return round(float((1 + rets.tail(days)).prod() - 1), 4)
    except Exception:
        pass
    return 0.0


def _recent_alpha(report, days: int = 30) -> float:
    """提取近 N 天相对 SPY 的 Alpha"""
    try:
        alpha = report.metrics.alpha
        return round(float(alpha) / 12, 4) if alpha else 0.0
    except Exception:
        return 0.0


# ── 格式化输出 ────────────────────────────────────────────────────────────────

def _format_strategy_entry(name: str, metrics: dict, key: str, num: int) -> dict:
    entry: dict = {"name": name}
    entry.update(metrics)
    # 策略专属字段
    if num == 2:
        entry["signal_frequency_30d"] = metrics.get("signal_frequency_30d", 0)
    if num == 3:
        # LightGBM：列出活跃因子（从 injected_factors 读取前4个）
        entry["active_factors"] = _get_active_factors()
    return entry


def _empty_strategy_entry(name: str) -> dict:
    return {
        "name":           name,
        "sharpe_ratio":   None,
        "max_drawdown":   None,
        "annual_return":  None,
        "win_rate":       None,
        "recent_30d_return": None,
        "recent_30d_alpha":  None,
        "information_coefficient_30d": None,
    }


def _compute_combined(strategies: dict) -> dict:
    """三策略等权平均绩效"""
    keys = ["strategy1", "strategy2", "strategy3"]
    fields = ["sharpe_ratio", "max_drawdown", "annual_return",
              "win_rate", "recent_30d_return", "recent_30d_alpha"]
    result: dict = {"name": "三策略 2+1 组合"}
    for f in fields:
        vals = [strategies[k].get(f) for k in keys
                if k in strategies and strategies[k].get(f) is not None]
        result[f] = round(sum(vals) / len(vals), 3) if vals else None
    return result


def _get_active_factors() -> list[str]:
    """从已注入因子库读取前 4 个因子名"""
    try:
        import pandas as pd
        from pathlib import Path
        p = Path(__file__).parent.parent / "injected_factors.csv"
        if p.exists():
            df = pd.read_csv(p)
            col = "name" if "name" in df.columns else df.columns[0]
            return df[col].head(4).tolist()
    except Exception:
        pass
    return []


# ── 基准数据 ────────────────────────────────────────────────────────────────

def _get_benchmark_metrics(ticker: str, start_date: str, end_date: str) -> dict:
    try:
        import yfinance as yf
        import numpy as np
        from core.app_state import get_state
        from workers.binance_downloader import binance_download
        reg = get_state().reg
        if reg == "bt":
            raw = binance_download(
                ticker, 
                start=start_date, 
                end=end_date,
                progress=False, 
                auto_adjust=True, 
                threads=True,
            )
        else:
            import yfinance as yf
            # yfinance 一次下载所有 ticker，速度远快于逐一下载
            # tickers_str = " ".join(tickers)
            raw = yf.download(
                ticker, 
                start=start_date, 
                end=end_date,
                progress=False, 
                auto_adjust=True, 
                threads=True,
            )

        if raw is None or raw.empty:
            return {"name": ticker, "recent_30d_return": None, "annual_return": None}
        if hasattr(raw.columns, "levels"):
            raw.columns = raw.columns.get_level_values(0)
        rets = raw["Close"].pct_change().dropna()
        annual = float((1 + rets).prod() ** (252 / len(rets)) - 1)
        recent_30d = float((1 + rets.tail(30)).prod() - 1)
        return {
            "name":             ticker,
            "recent_30d_return": round(recent_30d, 4),
            "annual_return":    round(annual, 4),
        }
    except Exception as e:
        logger.warning(f"[BacktestReport] 基准数据获取失败：{e}")
        return {"name": ticker, "recent_30d_return": None, "annual_return": None}
