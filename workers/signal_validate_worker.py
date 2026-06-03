"""
信号胜率验证 Worker
在 QThreadPool 中运行 SignalValidator，完成后通过信号通知 UI。
"""
from __future__ import annotations

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger


class SignalValidateSignals(QObject):
    progress  = pyqtSignal(int, str)     # pct, message
    result    = pyqtSignal(object)       # ValidationResult
    error     = pyqtSignal(str)          # error_message


class SignalValidateWorker(QRunnable):
    """
    历史信号胜率验证 Worker。
    lookback_days: 向前查看多少天的信号文件（默认 60）
    """

    def __init__(self, lookback_days: int = 60):
        super().__init__()
        self.lookback_days = lookback_days
        self.signals = SignalValidateSignals()
        self.setAutoDelete(True)

    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        
        参数:
            signal_name: 信号名称，如 'progress', 'result', 'error'
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
            logger.debug(f"[SignalValidateWorker] 信号 {signal_name} 发射失败：对象已删除")
            return False
        except Exception as e:
            logger.debug(f"[SignalValidateWorker] 信号 {signal_name} 发射失败：{e}")
            return False
        return False
    
    def _progress(self, pct: int, msg: str) -> None:
        """使用安全方法更新进度"""
        self.safe_emit_signal('progress', pct, msg)
    
    def _result(self, result) -> None:
        """使用安全方法记录结果"""
        self.safe_emit_signal('result', result)
    
    def _error(self, msg: str) -> None:
        """使用安全方法记录错误"""
        self.safe_emit_signal('error', msg)

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._progress(10, "扫描历史信号文件...")
            from backtesting.signal_validator import SignalValidator
            validator = SignalValidator()

            self._progress(30, f"加载过去 {self.lookback_days} 天的买入信号...")
            result = validator.validate(
                lookback_days=self.lookback_days,
                forward_days=[5, 20],
            )

            self._progress(90, f"已验证 {result.validated} 条信号，计算完成")
            self._result(result)

        except Exception as e:
            logger.error(f"[SignalValidateWorker] 失败：{e}")
            self._error(str(e))
