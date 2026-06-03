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

    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        
        参数:
            signal_name: 信号名称，如 'progress', 'completed', 'failed'
            *args: 信号参数
            
        返回:
            bool: 是否成功发射
        """
        try:
            signal = getattr(self.signals, signal_name, None)
            if signal is not None and hasattr(signal, 'emit'):
                signal.emit(*args)
                return True
        except RuntimeError:
            # PyQt对象已被删除
            logger.debug(f"[BacktestWorker] 信号 {signal_name} 发射失败：对象已删除")
            return False
        except Exception as e:
            logger.debug(f"[BacktestWorker] 信号 {signal_name} 发射失败：{e}")
            return False
        return False
    
    def _progress(self, pct: int, msg: str) -> None:
        """使用安全方法更新进度"""
        self.safe_emit_signal('progress', pct, msg)
    
    def _completed(self, report) -> None:
        """使用安全方法记录完成"""
        self.safe_emit_signal('completed', report)
    
    def _failed(self, msg: str) -> None:
        """使用安全方法记录失败"""
        self.safe_emit_signal('failed', msg)

    @pyqtSlot()
    def run(self) -> None:
        logger.info(
            f"BacktestWorker 开始：strategy={self.config.strategy_key}，"
            f"{self.config.start_date} → {self.config.end_date}"
        )

        def progress_cb(pct: int, msg: str):
            self._progress(pct, msg)

        try:
            from backtesting.backtest_engine import BacktestEngine
            engine = BacktestEngine()
            report = engine.run(self.config, progress_cb=progress_cb)

            self._completed(report)

            # 通知事件总线
            try:
                from core.event_bus import get_event_bus
                get_event_bus().backtest_completed.emit(report)
            except RuntimeError:
                logger.debug(f"[BacktestWorker] 事件总线对象已删除")
            except Exception as e:
                logger.debug(f"[BacktestWorker] 事件总线发射失败：{e}")

            logger.info(
                f"BacktestWorker 完成：年化={report.metrics.annual_return}，"
                f"Sharpe={report.metrics.sharpe_ratio}"
            )

        except Exception as e:
            logger.error(f"BacktestWorker 异常：{e}")
            self._failed(str(e))
            try:
                from core.event_bus import get_event_bus
                get_event_bus().backtest_failed.emit(str(e))
            except Exception:
                pass
