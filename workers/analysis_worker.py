"""
个股综合分析后台 Worker
在 QThreadPool 中运行 StockAnalyzer，完成后通过信号通知 UI
"""
from __future__ import annotations

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger


class AnalysisSignals(QObject):
    """Worker 信号"""
    started  = pyqtSignal(str)                  # ticker
    result   = pyqtSignal(str, object)           # ticker, StockReport
    error    = pyqtSignal(str, str)              # ticker, error_message
    progress = pyqtSignal(str, int, str)         # ticker, pct(0-100), status_text


class AnalysisWorker(QRunnable):
    """
    个股分析 Worker
    ticker:           股票代码
    use_deep_model:   是否使用 DistilBERT 精准情绪模型（默认 VADER）
    price_period_days:K线数据天数（默认 365）
    """

    def __init__(self, ticker: str,
                 use_deep_model: bool = False,
                 price_period_days: int = 365):
        super().__init__()
        self.ticker           = ticker.upper().strip()
        self.use_deep_model   = use_deep_model
        self.price_period_days = price_period_days
        self.signals          = AnalysisSignals()
        self.setAutoDelete(True)

    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        
        参数:
            signal_name: 信号名称，如 'started', 'result', 'error', 'progress'
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
            logger.debug(f"[AnalysisWorker] 信号 {signal_name} 发射失败：对象已删除")
            return False
        except Exception as e:
            logger.debug(f"[AnalysisWorker] 信号 {signal_name} 发射失败：{e}")
            return False
        return False
    
    def _started(self, ticker: str) -> None:
        """使用安全方法记录开始"""
        self.safe_emit_signal('started', ticker)
    
    def _result(self, ticker: str, report) -> None:
        """使用安全方法记录结果"""
        self.safe_emit_signal('result', ticker, report)
    
    def _error(self, ticker: str, msg: str) -> None:
        """使用安全方法记录错误"""
        self.safe_emit_signal('error', ticker, msg)
    
    def _progress(self, ticker: str, pct: int, msg: str) -> None:
        """使用安全方法更新进度"""
        self.safe_emit_signal('progress', ticker, pct, msg)

    @pyqtSlot()
    def run(self) -> None:
        ticker = self.ticker
        self._started(ticker)

        try:
            self._progress(ticker, 10, "初始化分析模块...")

            from stock_analysis.stock_analyzer import StockAnalyzer
            analyzer = StockAnalyzer()

            self._progress(ticker, 20, "并行获取 Alpha158 + K线 + 基本面 + 情绪...")

            report = analyzer.analyze(
                ticker,
                use_deep_sentiment=self.use_deep_model,
                price_period_days=self.price_period_days,
            )

            self._progress(ticker, 95, "生成综合报告...")
            self._result(ticker, report)
            self._progress(ticker, 100, "分析完成")

            logger.info(
                f"AnalysisWorker [{ticker}] 完成，"
                f"综合评分={report.overall.score}"
            )

        except Exception as e:
            logger.error(f"AnalysisWorker [{ticker}] 异常：{e}")
            self._error(ticker, str(e))
