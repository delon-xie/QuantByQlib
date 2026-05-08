"""
QuantByQlib 全局应用状态（单例）
集中管理运行时状态，避免组件间直接耦合
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class AppState:
    """全局应用状态容器（单例）"""

    # ── Qlib 初始化状态 ─────────────────────────────────────
    qlib_initialized: bool = False
    qlib_data_path: str = ""
    qlib_last_update: Optional[str] = None   # ISO 日期字符串
    reg:str = "us"
    reg_name:str = "美股"

    # ── OpenBB API Key 状态 ─────────────────────────────────
    fmp_key_configured: bool = False
    finnhub_key_configured: bool = False
    alpha_vantage_key_configured: bool = False

    # ── 量化选股状态 ─────────────────────────────────────────
    last_screening_strategy: Optional[str] = None
    last_screening_time: Optional[str] = None
    screening_results: list = field(default_factory=list)
    is_screening_running: bool = False

    # ── 回测状态 ─────────────────────────────────────────────
    is_backtest_running: bool = False
    last_backtest_result: Optional[dict] = None

    # ── RD-Agent 状态 ───────────────────────────────────────
    rdagent_container_id: Optional[str] = None
    rdagent_running: bool = False

    # ── 当前浏览的个股 ───────────────────────────────────────
    current_ticker: Optional[str] = None

    # ── 配置路径 ─────────────────────────────────────────────
    config_dir: Path = field(default_factory=lambda: Path("config"))
    data_dir: Path = field(default_factory=lambda: Path.home() / ".quantbyqlib")


# 模块级单例
_state: Optional[AppState] = None


def get_state() -> AppState:
    """获取全局应用状态单例"""
    global _state
    if _state is None:
        _state = AppState()
    return _state


def reset_state() -> None:
    """重置状态（仅用于测试）"""
    global _state
    _state = None
