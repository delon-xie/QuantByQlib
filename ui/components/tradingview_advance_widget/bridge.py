"""ChartBridge - QWebChannel 桥接对象。
JS 端通过 QWebChannel 直接调用其 @pyqtSlot 方法。
Python 端通过 call_js() 统一调用 JS 端方法。

增强: Python 回退计算, 双引擎支持, 调试自检
"""
import json
from PyQt6.QtCore import QObject, pyqtSlot, pyqtSignal
from typing import Any


class ChartBridge(QObject):
    """QWebChannel 桥接对象。注册到 channel 后 JS 端可直接调用其槽方法。"""

    chart_ready = pyqtSignal()
    indicator_toggled = pyqtSignal(str, bool, str)
    state_exported = pyqtSignal(str)
    # 新信号: Python 回退计算完成
    python_calc_done = pyqtSignal(str, str, str)

    _PENDING_CALLBACKS: dict[str, callable] = {}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widget: Any = None

    def bind_widget(self, widget):
        self._widget = widget

    @pyqtSlot()
    def on_chart_ready(self):
        self.chart_ready.emit()

    @pyqtSlot(str, str)
    def request_indicator_calc(self, key: str, params_json: str):
        """自定义指标计算 (已有的 Python 指标路径)"""
        if self._widget is None:
            return
        engine = getattr(self._widget, '_indicator_engine', None)
        original_df = getattr(self._widget, '_current_df', None)
        if engine is None or original_df is None:
            return
        params = json.loads(params_json) if params_json else {}
        try:
            result = engine.calculate(key, original_df, params)
            for series_name, data_list in result.items():
                opts = {
                    'group': 'PYTHON',
                    'indicatorKey': key,
                    'visible': True,
                    'subChart': True,
                }
                data_str = json.dumps(data_list)
                opts_str = json.dumps(opts)
                self.add_indicator_result(series_name, data_str, opts_str)
        except Exception as e:
            print(f"Python indicator calc failed: {key} - {e}")

    # ==================== 新: Python 回退计算 (双引擎) ====================

    @pyqtSlot(str, str)
    def request_python_calc(self, key: str, params_json: str):
        """Python 回退计算 — 由 JS 的 auto-fallback 或 python-only 模式调用。
        用于 JS catalog 中不存在的指标, 或强制 Python 计算的指标。
        params_json 可选包含 _bars 字段内联传递当前周期 OHLCV 数据。
        """
        if self._widget is None:
            return
        engine = getattr(self._widget, '_indicator_engine', None)
        if engine is None:
            return

        params = json.loads(params_json) if params_json else {}

        # 如果请求中内联了 _bars 数据，用它覆盖当前数据（避免异步竞争）
        bars_data = params.pop('_bars', None) if isinstance(params, dict) else None
        if bars_data is not None:
            self._widget.set_current_data(json.dumps(bars_data))
            print(f"[Bridge] Inline bars ({len(bars_data)}) for {key}")

        original_df = getattr(self._widget, '_current_df', None)
        if original_df is None:
            print(f"[Bridge] No current data for {key}")
            return

        actual_params = params.get('params', params) if isinstance(params, dict) else {}
        print(f"[Bridge] Python fallback calc requested: {key}")

        try:
            if engine.can_handle(key):
                result = engine.calculate(key, original_df, actual_params)
                for series_name, data_list in result.items():
                    opts = {
                        'group': 'PYTHON',
                        'indicatorKey': key,
                        'visible': True,
                        'subChart': True,
                        'params': actual_params,
                    }
                    data_str = json.dumps(data_list)
                    opts_str = json.dumps(opts)
                    self.add_indicator_result(series_name, data_str, opts_str)
                print(f"[Bridge] Python calc completed for {key}")
            else:
                print(f"[Bridge] No Python handler for {key}, trying dynamic lookup...")
                # 动态方法查找: 尝试 engine 的 _calc_{key} 方法
                result = engine.dynamic_calculate(key, original_df, actual_params)
                if result:
                    for series_name, data_list in result.items():
                        opts = {
                            'group': 'PYTHON',
                            'indicatorKey': key,
                            'visible': True,
                            'subChart': True,
                            'params': actual_params,
                        }
                        data_str = json.dumps(data_list)
                        opts_str = json.dumps(opts)
                        self.add_indicator_result(series_name, data_str, opts_str)
                    print(f"[Bridge] Dynamic Python calc completed for {key}")
                else:
                    print(f"[Bridge] No Python handler found for {key}")
        except Exception as e:
            print(f"[Bridge] Python fallback error: {key} - {e}")
            import traceback
            traceback.print_exc()

    @pyqtSlot()
    def request_python_inspect(self):
        """Python 端自检 — 返回可用的自定义指标列表到 JS 控制台"""
        if self._widget is None:
            return
        engine = getattr(self._widget, '_indicator_engine', None)
        if engine is None:
            return
        customs = engine.list_custom()
        print(f"[Bridge] Python custom indicators ({len(customs)}):")
        for c in customs:
            print(f"  - {c['key']}: {c.get('description', {}).get('description', 'No description')}")

    # ==================== 原有方法 ====================

    @pyqtSlot(str, bool, str)
    def on_indicator_toggle(self, key: str, state: bool, group: str):
        self.indicator_toggled.emit(key, state, group)

    @pyqtSlot(str)
    def on_state_exported(self, state_json: str):
        self.state_exported.emit(state_json)

    @pyqtSlot(str)
    def set_timeframe_data(self, data_json: str):
        """JS 端在时间框架切换时调用，同步 Python 端使用的 OHLCV 数据"""
        if self._widget is not None:
            self._widget.set_current_data(data_json)

    @pyqtSlot(str)
    def on_console_log(self, message: str):
        """接收 JS 端控制台日志"""
        print(f"[JS Console] {message}")

    @pyqtSlot(str)
    def save_favorites(self, json_str: str):
        """由 JS 端在收藏变化时调用，持久化到磁盘文件"""
        if self._widget is not None:
            self._widget._save_favorites(json_str)

    @pyqtSlot(result=str)
    def load_favorites(self):
        """JS 端初始化时调用，返回上次保存的收藏数据"""
        if self._widget is not None:
            return self._widget._load_favorites()
        return "{}"

    def call_js(self, method: str, *args):
        if self._widget is None:
            return
        browser = getattr(self._widget, 'browser', None)
        if browser is None:
            return
        serialized = json.dumps(args)
        js = f"window.bridgeClient?.callMethod?.('{method}', {serialized})"
        browser.page().runJavaScript(js)

    def set_chart_data(self, data: list[dict]):
        if self._widget is None:
            print("[Bridge] set_chart_data: widget is None")
            return
        browser = getattr(self._widget, 'browser', None)
        if browser is None:
            print("[Bridge] set_chart_data: browser is None")
            return
        data_json = json.dumps(data)
        print(f"[Bridge] set_chart_data: {len(data)} bars, json_len={len(data_json)}")
        js = f"window.bridgeClient?.setChartData?.({data_json})"
        browser.page().runJavaScript(js)

    def add_indicator_result(self, key: str, data_json: str, opts_json: str):
        if self._widget is None:
            return
        browser = getattr(self._widget, 'browser', None)
        if browser is None:
            return
        js = (
            f"window.bridgeClient?.addIndicatorResult?.("
            f"'{key}', {data_json}, {opts_json})"
        )
        browser.page().runJavaScript(js)

    def load_state(self, state_json: str):
        if self._widget is None:
            return
        browser = getattr(self._widget, 'browser', None)
        if browser is None:
            return
        js = f"window.bridgeClient?.loadState?.({state_json})"
        browser.page().runJavaScript(js)

    def notify_export_state(self):
        self.call_js('exportState')
