"""
输出路径管理
统一定义「美股交易日记/」下各子目录的路径，并负责目录创建与旧文件清理。

目录结构：
  美股交易日记/
    pics/          # F1 K线图 PNG
    signals/       # F2 策略信号 CSV
    regime/        # F3 HMM 政体 JSON
    backtest/      # F4 回测绩效 JSON
    skills/        # Claude Skill 定义
    qlib_manifest.json

可通过 .env 中以下变量单独覆盖每个子目录：
  TRADING_JOURNAL_DIR   根目录（默认 ~/美股交易日记）
  EXPORT_PICS_DIR       K线图目录
  EXPORT_SIGNALS_DIR    信号 CSV 目录
  EXPORT_REGIME_DIR     HMM 政体 JSON 目录
  EXPORT_BACKTEST_DIR   回测绩效 JSON 目录
"""
from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path


# ── 根目录（可通过环境变量覆盖）────────────────────────────────────────────
def _resolve_root() -> Path:
    from core.app_state import get_state
    reg_name = get_state().reg_name
    env = os.environ.get("TRADING_JOURNAL_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / f"{reg_name}交易日记"


def _resolve_subdir(env_key: str, default_name: str) -> Path:
    """读取独立目录环境变量；未配置则回退到根目录下的 default_name 子目录。"""
    env = os.environ.get(env_key, "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return _resolve_root() / default_name


def get_root() -> Path:
    """返回「美股交易日记/」根目录（已创建）"""
    root = _resolve_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_pics_dir() -> Path:
    d = _resolve_subdir("EXPORT_PICS_DIR", "pics")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_signals_dir() -> Path:
    d = _resolve_subdir("EXPORT_SIGNALS_DIR", "signals")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_regime_dir() -> Path:
    d = _resolve_subdir("EXPORT_REGIME_DIR", "regime")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_backtest_dir() -> Path:
    d = _resolve_subdir("EXPORT_BACKTEST_DIR", "backtest")
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_reports_dir() -> Path:
    """
    返回 AI 分析报告根目录（默认 ~/Documents/美股交易日记/reports/）
    可通过环境变量 REPORTS_DIR 覆盖。
    """
    from core.app_state import get_state
    reg_name = get_state().reg_name
    env = os.environ.get("REPORTS_DIR", "").strip()
    if env:
        d = Path(env).expanduser().resolve()
    else:
        # 默认：~/Documents/美股交易日记/reports
        d = Path.home() / "Documents" / f"{reg_name}交易日记" / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_skills_dir() -> Path:
    d = get_root() / "skills"
    d.mkdir(exist_ok=True)
    return d


def get_manifest_path() -> Path:
    return get_root() / "qlib_manifest.json"


# ── 文件名生成 ────────────────────────────────────────────────────────────

def chart_filename(ticker: str, chart_type: str, trade_date: date | None = None) -> str:
    """pics/{TICKER}_{type}_{YYYYMMDD}.png"""
    d = trade_date or date.today()
    return f"{ticker}_{chart_type}_{d.strftime('%Y%m%d')}.png"


def signal_filename(strategy_num: int, trade_date: date | None = None) -> str:
    """signals/strategy{N}_{YYYYMMDD}.csv"""
    d = trade_date or date.today()
    return f"strategy{strategy_num}_{d.strftime('%Y%m%d')}.csv"


def regime_filename(trade_date: date | None = None) -> str:
    """regime/hmm_regime_{YYYYMMDD}.json"""
    d = trade_date or date.today()
    return f"hmm_regime_{d.strftime('%Y%m%d')}.json"


def backtest_filename(trade_date: date | None = None) -> str:
    """backtest/performance_{YYYYMMDD}.json"""
    d = trade_date or date.today()
    return f"performance_{d.strftime('%Y%m%d')}.json"


# ── 旧文件清理 ────────────────────────────────────────────────────────────

def _cleanup_dir(directory: Path, pattern: str, keep_days: int) -> int:
    """
    删除 directory 中匹配 pattern 的文件里，修改时间超过 keep_days 天的旧文件。
    返回删除数量。
    """
    cutoff = date.today() - timedelta(days=keep_days)
    removed = 0
    for f in directory.glob(pattern):
        try:
            mtime = date.fromtimestamp(f.stat().st_mtime)
            if mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass
    return removed


def cleanup_old_files() -> dict:
    """按规格书第六节清理过期文件，返回各目录清理数量"""
    result = {}
    result["pics"]    = _cleanup_dir(get_pics_dir(),     "*.png",  keep_days=30 * 1)   # 约30交易日
    result["signals"] = _cleanup_dir(get_signals_dir(),  "*.csv",  keep_days=60 * 1)
    result["regime"]  = _cleanup_dir(get_regime_dir(),   "*.json", keep_days=84)        # 12周
    result["backtest"]= _cleanup_dir(get_backtest_dir(), "*.json", keep_days=366)       # 12个月
    return result
