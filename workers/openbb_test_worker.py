"""
OpenBB 连接测试 Worker
在后台线程逐项测试各数据源，通过信号实时更新 UI
"""
from __future__ import annotations

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger


class TestSignals(QObject):
    provider_result = pyqtSignal(str, bool, str)   # (provider名, 是否成功, 详情)
    completed       = pyqtSignal(dict)              # {provider: bool}
    error           = pyqtSignal(str)


class OpenBBTestWorker(QRunnable):
    """测试 OpenBB 各数据源连通性"""

    def __init__(self):
        super().__init__()
        self.signals = TestSignals()
        self.setAutoDelete(True)

    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        
        参数:
            signal_name: 信号名称，如 'provider_result', 'completed', 'error'
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
            logger.debug(f"[OpenBBTestWorker] 信号 {signal_name} 发射失败：对象已删除")
            return False
        except Exception as e:
            logger.debug(f"[OpenBBTestWorker] 信号 {signal_name} 发射失败：{e}")
            return False
        return False
    
    def _provider_result(self, provider: str, ok: bool, detail: str) -> None:
        """使用安全方法记录提供商结果"""
        self.safe_emit_signal('provider_result', provider, ok, detail)
    
    def _completed(self, results: dict) -> None:
        """使用安全方法记录完成"""
        self.safe_emit_signal('completed', results)
    
    def _error(self, msg: str) -> None:
        """使用安全方法记录错误"""
        self.safe_emit_signal('error', msg)

    @pyqtSlot()
    def run(self) -> None:
        results = {}
        test_ticker = "AAPL"

        # yfinance（无需 Key）
        self._provider_result("yfinance", False, "测试中...")
        try:
            from data.openbb_client import get_price_history
            r = get_price_history(test_ticker, "2024-01-02", "2024-01-05", ["yfinance"])
            ok = r is not None
            detail = "✅ 连接正常" if ok else "❌ 无数据返回"
        except Exception as e:
            ok = False
            detail = f"❌ {e}"
        results["yfinance"] = ok
        self._provider_result("yfinance", ok, detail)

        # FMP（需要 Key）
        self._provider_result("fmp", False, "测试中...")
        try:
            import os
            if not os.environ.get("FMP_API_KEY"):
                ok = False
                detail = "⚠️ 未配置 FMP_API_KEY"
            else:
                from data.openbb_client import get_company_profile
                r = get_company_profile(test_ticker)
                ok = r is not None and r.get("name") is not None
                detail = f"✅ {r.get('name', 'AAPL')}" if ok else "❌ 无数据（Key 可能无效）"
        except Exception as e:
            ok = False
            detail = f"❌ {e}"
        results["fmp"] = ok
        self._provider_result("fmp", ok, detail)

        # Finnhub（需要 Key）
        self._provider_result("finnhub", False, "测试中...")
        try:
            import os
            if not os.environ.get("FINNHUB_API_KEY"):
                ok = False
                detail = "⚠️ 未配置 FINNHUB_API_KEY"
            else:
                from data.openbb_client import get_news
                news = get_news(test_ticker, limit=1)
                ok = len(news) > 0
                detail = f"✅ 获取到 {len(news)} 条新闻" if ok else "❌ 无新闻（Key 可能无效）"
        except Exception as e:
            ok = False
            detail = f"❌ {e}"
        results["finnhub"] = ok
        self._provider_result("finnhub", ok, detail)

        # Alpha Vantage（需要 Key）
        self._provider_result("alpha_vantage", False, "测试中...")
        try:
            import os
            if not os.environ.get("ALPHA_VANTAGE_API_KEY"):
                ok = False
                detail = "⚠️ 未配置 ALPHA_VANTAGE_API_KEY"
            else:
                from data.openbb_client import get_price_history
                r = get_price_history(test_ticker, "2024-01-02", "2024-01-05", ["alpha_vantage"])
                ok = r is not None
                detail = "✅ 连接正常" if ok else "❌ 无数据（Key 可能无效或每日限额已用完）"
        except Exception as e:
            ok = False
            detail = f"❌ {e}"
        results["alpha_vantage"] = ok
        self._provider_result("alpha_vantage", ok, detail)

        self._completed(results)
        logger.info(f"OpenBB 连接测试完成：{results}")
