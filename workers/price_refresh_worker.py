"""
持仓价格批量刷新 Worker
定期从 OpenBB 获取持仓股票的最新报价，更新 UI
"""
from __future__ import annotations

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger


class PriceRefreshSignals(QObject):
    prices_updated = pyqtSignal(dict)   # {symbol: {price, change_pct, ...}}
    error          = pyqtSignal(str)


class PriceRefreshWorker(QRunnable):
    """批量刷新持仓股票最新价格"""

    def __init__(self, tickers: list[str]):
        super().__init__()
        self.tickers = tickers
        self.signals = PriceRefreshSignals()
        self.setAutoDelete(True)

    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        
        参数:
            signal_name: 信号名称，如 'prices_updated', 'error'
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
            logger.debug(f"[PriceRefreshWorker] 信号 {signal_name} 发射失败：对象已删除")
            return False
        except Exception as e:
            logger.debug(f"[PriceRefreshWorker] 信号 {signal_name} 发射失败：{e}")
            return False
        return False
    
    def _prices_updated(self, data: dict) -> None:
        """使用安全方法更新价格"""
        self.safe_emit_signal('prices_updated', data)
    
    def _error(self, msg: str) -> None:
        """使用安全方法记录错误"""
        self.safe_emit_signal('error', msg)

    @pyqtSlot()
    def run(self) -> None:
        if not self.tickers:
            self._prices_updated({})
            return

        try:
            from data.openbb_client import get_batch_quotes
            quotes = get_batch_quotes(self.tickers)
            # 过滤掉 None
            result = {k: v for k, v in quotes.items() if v is not None}
            logger.debug(f"价格刷新完成：{len(result)}/{len(self.tickers)} 支有数据")
            self._prices_updated(result)
        except Exception as e:
            logger.warning(f"价格刷新失败：{e}")
            self._error(str(e))
            self._prices_updated({})
