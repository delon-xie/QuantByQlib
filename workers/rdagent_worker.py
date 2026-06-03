"""
RD-Agent 后台 Worker
在 QRunnable 中启动 RDAgentRunner，通过事件总线向 UI 推送进度
"""
from __future__ import annotations

from PyQt6.QtCore import QRunnable, QObject, pyqtSignal, pyqtSlot
from loguru import logger


class RDAgentSignals(QObject):
    log       = pyqtSignal(str)    # 日志行
    completed = pyqtSignal(list)   # list[dict] 发现的因子
    failed    = pyqtSignal(str)    # 错误信息
    stopped   = pyqtSignal()       # 用户主动停止


class RDAgentWorker(QRunnable):
    """
    RD-Agent 启动 Worker。
    注意：日志流式读取在 RDAgentRunner._stream_loop 的子线程中运行，
    本 Worker 仅负责启动并在主线程安全地中继信号。
    """

    def __init__(self):
        super().__init__()
        self.signals = RDAgentSignals()
        self._runner = None
        self.setAutoDelete(True)

    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        
        参数:
            signal_name: 信号名称，如 'log', 'completed', 'failed', 'stopped'
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
            logger.debug(f"[RDAgentWorker] 信号 {signal_name} 发射失败：对象已删除")
            return False
        except Exception as e:
            logger.debug(f"[RDAgentWorker] 信号 {signal_name} 发射失败：{e}")
            return False
        return False
    
    def _log(self, line: str) -> None:
        """使用安全方法记录日志"""
        self.safe_emit_signal('log', line)
    
    def _completed(self, factors: list) -> None:
        """使用安全方法记录完成"""
        self.safe_emit_signal('completed', factors)
    
    def _failed(self, err: str) -> None:
        """使用安全方法记录失败"""
        self.safe_emit_signal('failed', err)
    
    def _stopped(self) -> None:
        """使用安全方法记录停止"""
        self.safe_emit_signal('stopped')

    def cancel(self) -> None:
        """请求停止（UI 线程调用）"""
        if self._runner:
            self._runner.stop()
        logger.info("RDAgentWorker 收到取消请求")

    @pyqtSlot()
    def run(self) -> None:
        logger.info("RDAgentWorker 开始")

        try:
            from rdagent_integration.rdagent_runner import RDAgentRunner

            def on_log(line: str) -> None:
                self._log(line)
                # 同步到事件总线
                try:
                    from core.event_bus import get_event_bus
                    get_event_bus().rdagent_log.emit(line)
                except RuntimeError:
                    logger.debug(f"[RDAgentWorker] 事件总线对象已删除")
                except Exception:
                    pass

            def on_done(factors: list) -> None:
                self._completed(factors)
                try:
                    from core.event_bus import get_event_bus
                    get_event_bus().rdagent_completed.emit(factors)
                except RuntimeError:
                    logger.debug(f"[RDAgentWorker] 事件总线对象已删除")
                except Exception:
                    pass

            def on_error(err: str) -> None:
                self._failed(err)
                try:
                    from core.event_bus import get_event_bus
                    get_event_bus().rdagent_failed.emit(err)
                except RuntimeError:
                    logger.debug(f"[RDAgentWorker] 事件总线对象已删除")
                except Exception:
                    pass

            self._runner = RDAgentRunner(
                log_cb=on_log,
                done_cb=on_done,
                error_cb=on_error,
            )

            # 通知已启动
            try:
                from core.event_bus import get_event_bus
                get_event_bus().rdagent_started.emit()
            except RuntimeError:
                logger.debug(f"[RDAgentWorker] 事件总线对象已删除")
            except Exception:
                pass

            ok = self._runner.start()
            if not ok:
                # start() 内部已通过 error_cb 通知，这里静默退出
                return

            # 等待日志流子线程完成
            if self._runner._thread:
                self._runner._thread.join()

            # 判断是否是用户主动停止
            if self._runner._stop_event.is_set():
                self._stopped()
                try:
                    from core.event_bus import get_event_bus
                    get_event_bus().rdagent_stopped.emit()
                except RuntimeError:
                    logger.debug(f"[RDAgentWorker] 事件总线对象已删除")
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"RDAgentWorker 异常：{e}")
            self._failed(str(e))
            try:
                from core.event_bus import get_event_bus
                get_event_bus().rdagent_failed.emit(str(e))
            except RuntimeError:
                logger.debug(f"[RDAgentWorker] 事件总线对象已删除")
            except Exception:
                pass
