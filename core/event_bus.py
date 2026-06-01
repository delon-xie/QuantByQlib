"""
QuantByQlib 事件总线
基于 PyQt6 信号机制实现模块间解耦通信
"""
from __future__ import annotations
from PyQt6.QtCore import QObject, pyqtSignal


class EventBus(QObject):
    """
    全局事件总线（单例 QObject）
    所有跨模块通信通过此对象的信号进行，避免直接引用依赖
    """

    # ── 数据事件 ─────────────────────────────────────────────
    qlib_initialized = pyqtSignal()                  # Qlib 初始化完成
    qlib_data_downloaded = pyqtSignal()              # Qlib 数据下载完成
    openbb_configured = pyqtSignal()                 # OpenBB API Key 配置完成

    # ── 选股事件 ─────────────────────────────────────────────
    screening_started = pyqtSignal(str)              # 参数: 策略名称
    screening_progress = pyqtSignal(int, str)        # 参数: 进度(0-100), 状态文字
    screening_completed = pyqtSignal(list)           # 参数: 选股结果列表
    screening_failed = pyqtSignal(str)               # 参数: 错误信息

    # ── 个股分析事件 ─────────────────────────────────────────
    analysis_requested = pyqtSignal(str)             # 参数: ticker
    analysis_completed = pyqtSignal(str, object)     # 参数: ticker, StockReport
    analysis_failed = pyqtSignal(str, str)           # 参数: ticker, 错误信息

    # ── 持仓事件 ─────────────────────────────────────────────
    portfolio_updated = pyqtSignal()                 # 持仓数据变更（买入/卖出/删除）
    portfolio_prices_refreshed = pyqtSignal()        # 持仓价格批量刷新完成

    # ── 目标事件 ─────────────────────────────────────────────
    goal_updated = pyqtSignal()                      # 目标设定/修改

    # ── 回测事件 ─────────────────────────────────────────────
    backtest_started = pyqtSignal(str)               # 参数: 策略名称
    backtest_progress = pyqtSignal(int, str)         # 参数: 进度(0-100), 状态文字
    backtest_completed = pyqtSignal(object)          # 参数: BacktestResult
    backtest_failed = pyqtSignal(str)                # 参数: 错误信息
    backtest_ticker_hint = pyqtSignal(str)           # 参数: ticker（选股结果跳转时携带）

    # ── RD-Agent 事件 ────────────────────────────────────────
    rdagent_started = pyqtSignal()
    rdagent_log = pyqtSignal(str)                    # 参数: 日志行
    rdagent_completed = pyqtSignal(list)             # 参数: 发现的因子列表
    rdagent_failed = pyqtSignal(str)                 # 参数: 错误信息
    rdagent_stopped = pyqtSignal()
    rdagent_factors_injected = pyqtSignal(list)      # 参数: 通过验证的因子表达式 list[str]

    # ── 导航事件 ─────────────────────────────────────────────
    navigate_to = pyqtSignal(str)                    # 参数: 页面名称
    show_ticker_detail = pyqtSignal(str, object)     # 参数: ticker, quant_score(可为None)
    stock_chart_requested = pyqtSignal(str)           # 参数: ticker

    # ── 系统事件 ─────────────────────────────────────────────
    log_message = pyqtSignal(str, str)               # 参数: 级别(INFO/WARN/ERROR), 消息
    status_message = pyqtSignal(str)                 # 参数: 状态栏消息
    
    # ── 切换新市场事件 ─────────────────────────────────────────────
    reg_changed = pyqtSignal(str, str)               # 参数: 切换新的注册市场代码（如 "US"）


# 模块级单例
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """获取全局事件总线单例（必须在 QApplication 创建后调用）"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
