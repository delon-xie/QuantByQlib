"""
F2：策略信号 CSV 规范化导出
将选股结果转换为统一 schema 并写入 美股交易日记/signals/strategyN_{YYYYMMDD}.csv

统一 CSV Schema：
  symbol, score, direction, rank, signal_strength, universe_size, strategy_id, date

Direction 阈值：
  score > 0.5  → BUY + strong
  0.2~0.5      → BUY + moderate
  -0.2~0.2     → NEUTRAL + weak（弱）
  -0.5~-0.2    → SELL + moderate
  < -0.5       → SELL + strong

策略编号映射（对应 ScreeningWorker strategy_key）：
  deep_learning       → strategy1  (LSTM 长期选股)
  intraday_profit     → strategy2  (GRU 短期动量)
  growth_stocks       → strategy3  (LightGBM + RD-Agent)
  market_adaptive     → strategy4
  pytorch_full_market → strategy5
"""
from __future__ import annotations

import csv
from datetime import date
from pathlib import Path
from typing import Optional

from loguru import logger
from utils.csvhelper import _write_csv


# ── 策略编号映射 ────────────────────────────────────────────────────────────
STRATEGY_NUM: dict[str, int] = {
    "deep_learning":       1,
    "intraday_profit":     2,
    "growth_stocks":       3,
    "market_adaptive":     4,
    "pytorch_full_market": 5,
}


def _score_to_direction_strength(score: float) -> tuple[str, str]:
    """将分数转为 (direction, signal_strength)"""
    if score > 0.5:
        return "BUY",  "strong"
    elif score > 0.2:
        return "BUY",  "moderate"
    elif score >= -0.2:
        return "NEUTRAL", "weak"
    elif score >= -0.5:
        return "SELL", "moderate"
    else:
        return "SELL", "strong"


def export_signals(
    strategy_key: str,
    results: list[dict],
    trade_date: Optional[date] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    将选股结果写入标准化 CSV 文件。

    Parameters
    ----------
    strategy_key : str
        策略标识符，如 "deep_learning"
    results : list[dict]
        来自 StockScreener.run() 的结果列表，每项包含
        {ticker, score, universe_size, ...}
    trade_date : date, optional
        信号日期；None 时使用今日
    output_dir : Path, optional
        输出目录；None 时使用 services.output_paths.get_signals_dir()

    Returns
    -------
    Path
        写入的 CSV 文件路径
    """
    from services.output_paths import get_signals_dir, signal_filename

    d = trade_date or date.today()
    num = STRATEGY_NUM.get(strategy_key, 0)
    strategy_id = f"strategy{num}" if num else strategy_key

    out_dir = output_dir or get_signals_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    fname = signal_filename(num, d) if num else f"{strategy_key}_{d.strftime('%Y%m%d')}.csv"
    out_path = out_dir / fname

    universe_size = results[0].get("universe_size", len(results)) if results else 0

    rows = []
    for rank, item in enumerate(results, start=1):
        ticker  = str(item.get("ticker", "")).upper()
        score   = float(item.get("score", 0.0))
        direction, strength = _score_to_direction_strength(score)
        rows.append({
            "symbol":          ticker,
            "score":           round(score, 6),
            "direction":       direction,
            "rank":            rank,
            "signal_strength": strength,
            "universe_size":   universe_size,
            "strategy_id":     strategy_id,
            "date":            d.isoformat(),
        })

    _write_csv(out_path, rows)
    logger.info(f"[SignalExporter] {strategy_id} → {out_path}  ({len(rows)} 条)")
    return out_path


def export_signals_empty(
    strategy_key: str,
    trade_date: Optional[date] = None,
    output_dir: Optional[Path] = None,
) -> Path:
    """当策略无输出时，生成仅含 header 的空 CSV（避免消费方报错）"""
    from services.output_paths import get_signals_dir, signal_filename

    d = trade_date or date.today()
    num = STRATEGY_NUM.get(strategy_key, 0)
    out_dir = output_dir or get_signals_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = signal_filename(num, d) if num else f"{strategy_key}_{d.strftime('%Y%m%d')}.csv"
    out_path = out_dir / fname
    _write_csv(out_path, [])
    logger.warning(f"[SignalExporter] {strategy_key} 无信号，写入空 CSV → {out_path}")
    return out_path


# ── 内部工具 ────────────────────────────────────────────────────────────────

_FIELDNAMES = [
    "symbol", "score", "direction", "rank",
    "signal_strength", "universe_size", "strategy_id", "date",
]
