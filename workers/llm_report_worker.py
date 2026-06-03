"""
LLM 分析报告后台 Worker
在 QThreadPool 中调用 LLMReportGenerator.generate_stream()，
通过信号将文本块流式推送给 UI。
"""
from __future__ import annotations

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger


class LLMReportSignals(QObject):
    chunk    = pyqtSignal(str, str)   # ticker, text_chunk（流式）
    finished = pyqtSignal(str, str)   # ticker, full_text
    error    = pyqtSignal(str, str)   # ticker, error_message


class LLMReportWorker(QRunnable):
    """
    流式生成 AI 分析报告。
    接收已完成的 StockReport，调用 Claude API，
    通过 chunk 信号实时推送文本块给 UI。
    完成后同步保存 MD 文件（若配置开启）。
    """

    def __init__(self, report):
        super().__init__()
        self._report = report
        self.signals = LLMReportSignals()
        self.setAutoDelete(True)

    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        
        参数:
            signal_name: 信号名称，如 'chunk', 'finished', 'error'
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
            logger.debug(f"[LLMReportWorker] 信号 {signal_name} 发射失败：对象已删除")
            return False
        except Exception as e:
            logger.debug(f"[LLMReportWorker] 信号 {signal_name} 发射失败：{e}")
            return False
        return False
    
    def _chunk(self, ticker: str, text: str) -> None:
        """使用安全方法推送文本块"""
        self.safe_emit_signal('chunk', ticker, text)
    
    def _finished(self, ticker: str, full_text: str) -> None:
        """使用安全方法记录完成"""
        self.safe_emit_signal('finished', ticker, full_text)
    
    def _error(self, ticker: str, msg: str) -> None:
        """使用安全方法记录错误"""
        self.safe_emit_signal('error', ticker, msg)

    @pyqtSlot()
    def run(self) -> None:
        ticker = self._report.ticker
        try:
            from stock_analysis.llm_report_generator import LLMReportGenerator
            generator = LLMReportGenerator()

            full_text = ""
            for chunk in generator.generate_stream(self._report):
                full_text += chunk
                self._chunk(ticker, chunk)

            # 保存 MD 文件
            if full_text:
                try:
                    from services.report_writer import ReportWriter
                    ReportWriter().save_stock_report(ticker, full_text)
                except Exception as e:
                    logger.debug(f"[LLMReportWorker] MD 保存失败 {ticker}：{e}")

            self._finished(ticker, full_text)

        except Exception as e:
            logger.error(f"[LLMReportWorker] {ticker} 最终失败：{e}")
            err_str = str(e)
            if "401" in err_str or "authentication" in err_str.lower():
                msg = "API Key 认证失败，请在「参数配置」中检查 Anthropic / DeepSeek Key。"
            elif "DEEPSEEK_API_KEY 未配置" in err_str:
                msg = "Claude 不可用，且 DEEPSEEK_API_KEY 未配置，无法降级。请在「参数配置」中填写 DeepSeek Key。"
            elif "insufficient_quota" in err_str or "credit" in err_str.lower():
                msg = "API 账户额度不足，请充值后再试。"
            else:
                msg = f"生成失败：{err_str}"
            self._error(ticker, msg)
