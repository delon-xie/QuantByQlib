"""
QLib Instruments 更新 Worker
更新股票基础信息（A股），支持进度反馈
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal, pyqtSlot


class InstrumentsUpdaterSignals(QObject):
    """Worker 信号（必须继承 QObject）"""
    progress  = pyqtSignal(int, str)    # (0-100, 状态描述)
    log_line  = pyqtSignal(str)         # 实时日志行
    completed = pyqtSignal(bool, str)   # (成功?, 最终消息)
    error     = pyqtSignal(str)         # 错误消息


class QLibInstrumentsUpdaterWorker(QRunnable):
    """
    QLib Instruments 更新 Worker
    
    更新股票基础信息，包括：
    1. 从东方财富获取完整A股列表
    2. 批量更新所有 instruments CSV 文件
    """

    def __init__(self):
        super().__init__()
        self.signals = InstrumentsUpdaterSignals()
        self._cancelled = False
        
    def safe_emit_signal(self, signal_name: str, *args) -> bool:
        """
        安全发射信号，避免 RuntimeError: wrapped C/C++ object has been deleted
        """
        try:
            if not self.signals:
                return False
                
            signal = getattr(self.signals, signal_name, None)
            if signal and hasattr(signal, 'emit'):
                signal.emit(*args)
                return True
        except RuntimeError:
            return False
        except Exception:
            return False
        return False
    
    def _log(self, msg: str) -> None:
        """使用安全方法记录日志"""
        self.safe_emit_signal('log_line', msg)
    
    def _progress(self, pct: int, msg: str) -> None:
        """使用安全方法更新进度"""
        self.safe_emit_signal('progress', pct, msg)
    
    def _error(self, msg: str) -> None:
        """使用安全方法记录错误"""
        self.safe_emit_signal('error', msg)
    
    def _completed(self, is_completed: bool, msg: str) -> None:
        """使用安全方法记录完成"""
        self.safe_emit_signal('completed', is_completed, msg)
    
    def cancel(self) -> None:
        self._cancelled = True

    @pyqtSlot()
    def run(self) -> None:
        try:
            self._run_update()
        except Exception as e:
            self._log(f"Instruments 更新 Worker 异常：{e}")
            self._error(str(e))

    def _run_update(self) -> None:
        """执行更新流程"""
        from services.qlib_instruments_updater import QLibInstrumentsUpdater

        self._progress(5, "初始化...")
        
        try:
            updater = QLibInstrumentsUpdater()
            
            # 1. 获取基础信息（最耗时的步骤）
            self._progress(10, "获取A股完整列表...")
            self._log("[INFO] 正在从东方财富获取A股实时行情数据...")
            
            def progress_callback(pct: int, msg: str):
                if self._cancelled:
                    raise RuntimeError("用户取消")
                adjusted_pct = 10 + int(pct * 0.7)
                self._progress(adjusted_pct, msg)
                self._log(f"[INFO] {msg}")
            
            results = updater.batch_update_instruments_csv(progress_callback=progress_callback)
            
            if self._cancelled:
                self._log("[INFO] 用户取消")
                self._completed(False, "用户取消")
                return
                
            self._log(f"[INFO] 获取成功，共 {results['golobal_total']['股票数']} 条记录")
            
            # 2. 批量更新 CSV
            self._progress(85, "更新 instruments CSV...")
            self._log("[INFO] 批量更新 instruments CSV 文件...")
            
            
            
            if self._cancelled:
                self._log("[INFO] 用户取消")
                self._completed(False, "用户取消")
                return
            
            # 3. 完成
            self._progress(95, "整理结果...")
            
            # 整理结果
            summary_lines = ["更新完成:"]
            total_count = 0
            for csv_name, csv_info in results.items():
                if csv_name != 'golobal_total':
                    continue
                # csv_info 是字典 {'股票数': xxx, '文件路径': xxx}
                total_count = csv_info.get('股票数', 0)
                summary_lines.append(f"总共更新: {total_count} 支股票")
            
            self._log("[INFO] " + "\n[INFO] ".join(summary_lines))
            
            self._progress(100, "完成")
            self._completed(True, f"更新完成，共 {total_count} 支股票")
            
        except RuntimeError as e:
            if str(e) == "用户取消":
                self._completed(False, "用户取消")
            else:
                self._error(str(e))
                self._completed(False, str(e))
        except Exception as e:
            import traceback
            import sys
            exc_type, exc_obj, exc_tb = sys.exc_info()
            line_num = exc_tb.tb_lineno if exc_tb else "unknown"
            stack_trace = traceback.format_exc()
            error_msg = f"更新失败：{type(e).__name__}: {e}"
            self._log(f"[ERROR] {error_msg}")
            self._log(f"[ERROR] 错误发生在第 {line_num} 行")
            self._log(f"[ERROR] 完整堆栈跟踪:\n{stack_trace}")
            self._error(error_msg)
            self._completed(False, f"{error_msg}（详见日志）")