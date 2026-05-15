"""
策略回测后台 Worker
在 QThreadPool 中运行 BacktestEngine
"""
from __future__ import annotations

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger

from backtesting.backtest_engine import BacktestConfig


class BacktestSignals(QObject):
    progress  = pyqtSignal(int, str)       # pct, message
    completed = pyqtSignal(object)         # BacktestReport
    failed    = pyqtSignal(str)            # error message


class BacktestWorker(QRunnable):
    """回测 Worker"""

    def __init__(self, config: BacktestConfig):
        super().__init__()
        from core.app_state import get_state
        if get_state().reg == "bt" and config.benchmark == "SPY":
            config.benchmark = "BTCUSDT"

        self.config  = config
        self.signals = BacktestSignals()
        self.setAutoDelete(True)

    @pyqtSlot()
    def run(self) -> None:
        logger.info(
            f"BacktestWorker 开始：strategy={self.config.strategy_key}，"
            f"{self.config.start_date} → {self.config.end_date}"
        )

        def progress_cb(pct: int, msg: str):
            self.signals.progress.emit(pct, msg)

        try:
            from backtesting.backtest_engine import BacktestEngine
            engine = BacktestEngine()
            report = engine.run(self.config, progress_cb=progress_cb)

            self.signals.completed.emit(report)

            # 通知事件总线
            try:
                from core.event_bus import get_event_bus
                get_event_bus().backtest_completed.emit(report)
            except Exception:
                pass

            logger.info(
                f"BacktestWorker 完成：年化={report.metrics.annual_return}，"
                f"Sharpe={report.metrics.sharpe_ratio}"
            )

        except Exception as e:
            logger.error(f"BacktestWorker 异常：{e}")
            self.signals.failed.emit(str(e))
            try:
                from core.event_bus import get_event_bus
                get_event_bus().backtest_failed.emit(str(e))
            except Exception:
                pass
