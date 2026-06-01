"""
TradingViewAdvanceWidget - 基于 PyQt6 QWebEngineView 的技术分析图表组件。
集成 lightweight-charts 5.2 + 446 技术指标 + 3-Tab 面板。
"""
import json
from pathlib import Path

import pandas as pd
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtCore import Qt, QTimer

from .bridge import ChartBridge
from .indicator_engine import PythonIndicatorEngine
from .state_manager import StateManager


_HERE = Path(__file__).parent


class TradingViewAdvanceWidget(QWidget):
    """
    PyQt6 技术分析图表组件。

    用法:
        widget = TradingViewAdvanceWidget()
        widget.update_chart_data(df)     # 传入 OHLCV DataFrame
        widget.save_state('/path.json')   # 导出状态
        widget.load_state('/path.json')   # 恢复状态
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.browser: QWebEngineView | None = None
        self._channel: QWebChannel | None = None
        self._bridge: ChartBridge | None = None
        self._indicator_engine = PythonIndicatorEngine()
        self._state_manager = StateManager()
        self._original_df: pd.DataFrame | None = None
        self._current_df: pd.DataFrame | None = None
        self._pending_data: list[dict] | None = None
        self._ready = False
        self._init_ui()
        self._init_channel()
        self._load_page()
        self._start_ready_poll()
        self._setup_dev_tools()

    def showEvent(self, event):
        super().showEvent(event)
        self._trigger_chart_resize()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._trigger_chart_resize()

    def _trigger_chart_resize(self):
        if self._ready and self._bridge:
            self.browser.page().runJavaScript("""
                (function() {
                    if (window.chartManager && window.chartManager.mainChart && window.chartManager.mainContainer) {
                        var w = window.chartManager.mainContainer.clientWidth;
                        var h = window.chartManager.mainContainer.clientHeight;
                        console.log('[Widget resize] triggering resize:', w, 'x', h);
                        if (w > 0 && h > 0) {
                            window.chartManager.mainChart.resize(w, h);
                            window.chartManager.fitContent();
                        } else if (w === 0) {
                            // 宽度为0，尝试使用父容器宽度
                            var parent = window.chartManager.mainContainer.parentElement;
                            if (parent) {
                                w = parent.clientWidth || parent.offsetWidth || 800;
                                h = parent.clientHeight || parent.offsetHeight || 600;
                                console.log('[Widget resize] using parent size:', w, 'x', h);
                                if (w > 0 && h > 0) {
                                    window.chartManager.mainChart.resize(w, h);
                                    window.chartManager.fitContent();
                                }
                            }
                        }
                    }
                })();
            """)
        elif self._ready:
            # bridge未就绪但页面已加载，延迟重试
            QTimer.singleShot(200, self._trigger_chart_resize)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.browser = QWebEngineView(self)
        layout.addWidget(self.browser)
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        settings = self.browser.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        # 设置持久化存储路径（localStorage 等数据跨 session 保留）
        from pathlib import Path
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        storage_dir = str(Path.home() / '.tradingview_widget' / 'storage')
        profile = QWebEngineProfile.defaultProfile()
        profile.setPersistentStoragePath(storage_dir)
        profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
        from PyQt6.QtWebEngineCore import QWebEngineProfile as ProfileEnum
        profile.setPersistentCookiesPolicy(ProfileEnum.PersistentCookiesPolicy.ForcePersistentCookies)
        # 添加页面加载完成信号处理
        self.browser.loadFinished.connect(self._on_page_load_finished)

    def _init_channel(self):
        self._channel = QWebChannel()
        self._bridge = ChartBridge()
        self._bridge.bind_widget(self)
        self._channel.registerObject('bridge', self._bridge)
        self.browser.page().setWebChannel(self._channel)
        self._bridge.chart_ready.connect(self._on_chart_ready)

    def _load_page(self):
        html_path = _HERE / 'html' / 'template.html'
        from PyQt6.QtCore import QUrl
        url = QUrl(html_path.resolve().as_uri())
        print(f"[Widget] Loading URL: {url.toString()}")
        self.browser.setUrl(url)

    def _start_ready_poll(self):
        QTimer.singleShot(500, self._check_chart_ready)

    def _check_chart_ready(self):
        if self._bridge and not self._ready:
            self.browser.page().runJavaScript(
                """
                (function() {
                    console.log('[PYTHON CHECK] Checking chart ready state...');
                    console.log('[PYTHON CHECK] window.isChartInitialized:', window.isChartInitialized);
                    console.log('[PYTHON CHECK] typeof window.chartManager:', typeof window.chartManager);
                    console.log('[PYTHON CHECK] typeof window.indicatorEngine:', typeof window.indicatorEngine);
                    console.log('[PYTHON CHECK] typeof window.bridgeClient:', typeof window.bridgeClient);
                    console.log('[PYTHON CHECK] typeof QWebChannel:', typeof QWebChannel);
                    console.log('[PYTHON CHECK] typeof window.LightweightCharts:', typeof window.LightweightCharts);
                    return {
                        isChartInitialized: window.isChartInitialized === true,
                        hasChartManager: typeof window.chartManager !== 'undefined',
                        hasIndicatorEngine: typeof window.indicatorEngine !== 'undefined',
                        hasBridgeClient: typeof window.bridgeClient !== 'undefined',
                        hasQWebChannel: typeof QWebChannel !== 'undefined',
                        hasLightweightCharts: typeof window.LightweightCharts !== 'undefined'
                    };
                })();
                """,
                self._on_ready_check
            )

    def _on_ready_check(self, result):
        print(f"[Widget] _on_ready_check: result={result}")
        if result and result.get('isChartInitialized'):
            self._ready = True
            print("[Widget] Chart ready via poll check")
            self._flush_pending()
        else:
            QTimer.singleShot(300, self._check_chart_ready)

    def _setup_dev_tools(self):
        """QShortcut 方式绑定 F12 开发者工具快捷键"""
        from PyQt6.QtGui import QShortcut, QKeySequence
        self._dev_shortcut = QShortcut(QKeySequence(Qt.Key.Key_F12), self)
        self._dev_shortcut.activated.connect(self.open_dev_tools_window)

        # Ctrl+Shift+I 备用
        self._dev_shortcut2 = QShortcut(QKeySequence("Ctrl+Shift+I"), self)
        self._dev_shortcut2.activated.connect(self.open_dev_tools_window)

        # 捕获 JS 控制台消息和错误
        self.browser.page().javaScriptConsoleMessage = self._on_js_console

    def _on_js_console(self, level, message, line, source):
        """捕获 JS 控制台消息"""
        levels = {0: "INFO", 1: "WARN", 2: "ERROR"}
        prefix = levels.get(level, "LOG")
        print(f"[JS {prefix}] {message} (at {source}:{line})")

    def open_dev_tools_window(self):
        """打开独立的开发者工具窗口"""
        try:
            from PyQt6.QtWidgets import QMainWindow
            from PyQt6.QtWebEngineWidgets import QWebEngineView as WebEngineView

            self.dev_tools_window = QMainWindow()
            self.dev_tools_window.setWindowTitle("Developer Tools - TradingView Advance")
            self.dev_tools_window.setGeometry(100, 100, 900, 700)

            dev_browser = WebEngineView()
            self.dev_tools_window.setCentralWidget(dev_browser)

            self.browser.page().setDevToolsPage(dev_browser.page())
            self.dev_tools_window.show()
            print("Developer tools window opened")
        except Exception as e:
            print(f"Failed to open developer tools window: {e}")
            import traceback
            traceback.print_exc()

    def _on_page_load_finished(self, ok):
        """页面加载完成回调"""
        print(f"[Widget] Page load finished: ok={ok}")
        if ok:
            print("[Widget] Page loaded successfully, checking JavaScript...")
            # 立即执行一个简单的 JS 来验证
            self.browser.page().runJavaScript(
                """
                console.log('=== PAGE LOADED ===');
                console.log('Document readyState:', document.readyState);
                console.log('window object:', typeof window);
                'Page loaded successfully'
                """,
                lambda result: print(f"[Widget] JS execution result: {result}")
            )
            # 延迟开始就绪检查
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1000, self._start_ready_poll)
        else:
            print("[Widget] Page load failed!")
            # 检查页面错误
            self.browser.page().runJavaScript(
                "document.body ? document.body.innerHTML.substring(0, 500) : 'No body'",
                lambda result: print(f"[Widget] Page content on fail: {result}")
            )
            # 检查加载的 URL
            print(f"[Widget] Loaded URL: {self.browser.url().toString()}")

    def _on_chart_ready(self):
        print("[Widget] _on_chart_ready called from JS bridge")
        self._ready = True
        self._flush_pending()
        # 推送收藏数据到 JS 端
        try:
            fav_json = self._load_favorites()
            if fav_json and fav_json != '{}':
                # fav_json 已经是 JSON 字符串，直接转义为 JS 字符串字面量
                import json as _json
                js = f"window.Favorites?.loadFromPython?.({_json.dumps(fav_json)})"
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(200, lambda: self.browser.page().runJavaScript(js))
        except Exception as e:
            print(f"[Widget] push favorites error: {e}")

    def _flush_pending(self):
        print(f"[Widget] _flush_pending: pending={self._pending_data is not None}, ready={self._ready}, bridge={self._bridge is not None}")
        if self._pending_data and self._bridge:
            print(f"[Widget] flushing {len(self._pending_data)} bars to bridge")
            self._bridge.set_chart_data(self._pending_data)
            self._pending_data = None
            # 强制延迟检查并设置成交量数据
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(1000, self._force_volume_check)

    def _force_volume_check(self):
        """强制检查成交量系列并设置数据"""
        if not self._bridge or self._current_df is None:
            return
        
        print("[Widget] _force_volume_check: starting...")
        
        # 检查成交量系列是否存在
        js = """
        (function() {
            console.log('[FORCE CHECK] Checking volume series...');
            var cm = window.chartManager;
            if (!cm) {
                console.log('[FORCE CHECK] chartManager not found');
                return { hasChartManager: false };
            }
            console.log('[FORCE CHECK] volumeSeries:', !!cm.volumeSeries);
            console.log('[FORCE CHECK] candleSeries:', !!cm.candleSeries);
            
            if (cm.volumeSeries && cm.volumeSeries.data) {
                var volData = cm.volumeSeries.data();
                console.log('[FORCE CHECK] volume data points:', volData.length);
                if (volData.length > 0) {
                    console.log('[FORCE CHECK] first volume value:', volData[0].value);
                    var hasNonZero = volData.some(function(d) { return d.value > 0; });
                    console.log('[FORCE CHECK] has non-zero volume:', hasNonZero);
                }
            }
            
            return {
                hasChartManager: true,
                hasVolumeSeries: !!cm.volumeSeries,
                hasCandleSeries: !!cm.candleSeries
            };
        })();
        """
        
        def on_check(result):
            print(f"[Widget] _force_volume_check result: {result}")
            if result and result.get('hasChartManager') and not result.get('hasVolumeSeries'):
                print("[Widget] volumeSeries not found, attempting to create...")
                # 尝试重新创建成交量系列
                create_js = """
                var cm = window.chartManager;
                var lc = cm._GetLC();
                if (cm && lc && !cm.volumeSeries) {
                    console.log('[FORCE CHECK] Creating volume series...');
                    cm.volumeSeries = cm.mainChart.addSeries(lc.HistogramSeries, {
                        color: '#0ecb81',
                        priceFormat: { type: 'volume' },
                        priceScaleId: '',
                        scaleMargins: { top: 0.85, bottom: 0 }
                    });
                    cm.seriesMap.set('VOLUME', { 
                        series: cm.volumeSeries, 
                        chartId: 'main', 
                        visible: true, 
                        type: 'histogram' 
                    });
                    console.log('[FORCE CHECK] volumeSeries created:', !!cm.volumeSeries);
                }
                """
                self.browser.page().runJavaScript(create_js)
        
        self.browser.page().runJavaScript(js, on_check)

    # ==================== 新增: 双引擎控制 + 调试 ====================

    def set_compute_source(self, source: str):
        """
        设置计算源
        'js' — 仅 JS 端计算 (默认)
        'python' — 仅 Python 端计算
        'auto' — 优先 JS，找不到则回退 Python
        """
        if self._ready and self._bridge:
            self._bridge.call_js('setComputeSource', source)

    def debug_engine(self) -> str:
        """JS 引擎自检 — 返回调试信息到 Python 终端"""
        if not self._ready or not self._bridge:
            return "Chart not ready"
        self.browser.page().runJavaScript(
            """
            (function() {
                var info = window.indicatorEngine ? window.indicatorEngine.debug() : {};
                return JSON.stringify(info, null, 2);
            })();
            """,
            lambda result: print(f"[Debug Engine Info]\n{result}" if result else "[Debug] No result")
        )
        customs = self._indicator_engine.list_custom()
        print(f"[Python Custom Indicators] ({len(customs)}):")
        for c in customs:
            print(f"  - {c['key']}: {c.get('description', {}).get('description', '')}")
        return "Debug sent to console"

    def run_js_diagnose(self):
        """JS 全面诊断 — 检查初始化状态和各组件健康度"""
        if not self._ready or not self._bridge:
            print("[Diagnose] Chart not ready yet")
            return
        js_code = """
        (function() {
            var r = {
                isInitialized: !!window.isChartInitialized,
                hasCM: !!window.chartManager,
                hasIE: !!window.indicatorEngine,
                hasBC: !!window.bridgeClient,
                hasPanel: !!window.indicatorPanel,
                hasCP: !!window.combinedPresets,
                hasPrimitives: !!(window.Primitives && window.Primitives.LineBrPrimitive),
                hasLC: !!window.LightweightCharts,
                hasLCI: !!window.LightweightChartsIndicators,
                cm: null,
                ie: null,
                errors: [],
            };
            if (window.chartManager) {
                r.cm = {
                    hasMainChart: !!window.chartManager.mainChart,
                    hasCandleSeries: !!window.chartManager.candleSeries,
                    subChartCount: window.chartManager.subCharts ? window.chartManager.subCharts.size : 0,
                    seriesMapSize: window.chartManager.seriesMap ? window.chartManager.seriesMap.size : 0,
                    primitiveMapSize: window.chartManager.primitiveMap ? window.chartManager.primitiveMap.size : 0,
                };
            }
            if (window.indicatorEngine) {
                r.ie = {
                    catalogSize: window.indicatorEngine._catalog ? window.indicatorEngine._catalog.length : 0,
                    activeCount: window.indicatorEngine._activeMap ? window.indicatorEngine._activeMap.size : 0,
                    visibleCount: window.indicatorEngine._visibleMap ? window.indicatorEngine._visibleMap.size : 0,
                    barDataLen: window.indicatorEngine.barData ? window.indicatorEngine.barData.length : 0,
                    computeSource: window.indicatorEngine._computeSource,
                    showDataCount: window.indicatorEngine._showData ? window.indicatorEngine._showData.size : 0,
                };
            }
            return JSON.stringify(r);
        })();
        """
        self.browser.page().runJavaScript(
            js_code,
            lambda result: print(f"[JS Diagnosis]\n{result}" if result else "[Diagnose] No result")
        )
        print("[Diagnose] Run 'JS诊断' button after loading data")

    def update_chart_data(self, df: pd.DataFrame):
        if df.empty:
            print("[Widget] update_chart_data: df is empty")
            return
        cols = self._map_columns(df)
        print(f"[Widget] Column mapping: {cols}")
        print(f"[Widget] DataFrame columns: {list(df.columns)}")
        if not cols.get('date') or not all(
            cols.get(k) for k in ['open', 'high', 'low', 'close']
        ):
            print(f"[Widget] Missing required columns. Found: {list(df.columns)}")
            return
        
        # 检查成交量数据
        volume_col = cols.get('volume')
        if volume_col:
            vol_stats = df[volume_col].describe()
            print(f"[Widget] Volume stats - min:{vol_stats['min']}, max:{vol_stats['max']}, mean:{vol_stats['mean']}")
        else:
            print("[Widget] No volume column found")

        self._original_df = df.copy()
        self._current_df = df.copy()
        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        
        candle_data = []
        volume_col = cols.get('volume')
        for i in range(len(df)):
            candle_data.append({
                'time': str(dates[i]),
                'open': float(df[cols['open']].iloc[i]),
                'high': float(df[cols['high']].iloc[i]),
                'low': float(df[cols['low']].iloc[i]),
                'close': float(df[cols['close']].iloc[i]),
                'volume': int(float(df[volume_col].iloc[i])) if volume_col else 0,
            })
        
        print(f"[Widget] First candle: {candle_data[0]}")

        print(f"[Widget] update_chart_data: ready={self._ready}, bridge={self._bridge is not None}, bars={len(candle_data)}")
        if self._ready and self._bridge:
            self._bridge.set_chart_data(candle_data)
            print("[Widget] set_chart_data called via bridge")
        else:
            self._pending_data = candle_data
            print(f"[Widget] data stored in pending, ready={self._ready}")

    def set_current_data(self, data_json: str):
        """由 JS 端在时间框架切换时调用，更新 Python 侧的当前数据"""
        import json
        try:
            bars = json.loads(data_json)
            if not bars:
                return
            rows = []
            for b in bars:
                rows.append({
                    'date': b['time'],
                    'open': float(b['open']),
                    'high': float(b['high']),
                    'low': float(b['low']),
                    'close': float(b['close']),
                    'volume': float(b.get('volume', 0)),
                })
            self._current_df = pd.DataFrame(rows)
            print(f"[Widget] Current data updated: {len(self._current_df)} bars")
        except Exception as e:
            print(f"[Widget] set_current_data error: {e}")

    def clear_all(self):
        if self._ready and self._bridge:
            self._bridge.call_js('clearAllIndicators')

    _FAVORITES_PATH = Path.home() / '.tradingview_widget' / 'favorites.json'

    def _save_favorites(self, json_str: str):
        try:
            self._FAVORITES_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._FAVORITES_PATH.write_text(json_str, encoding='utf-8')
        except Exception as e:
            print(f"[Widget] save_favorites error: {e}")

    def _load_favorites(self) -> str:
        try:
            if self._FAVORITES_PATH.exists():
                return self._FAVORITES_PATH.read_text(encoding='utf-8')
        except Exception as e:
            print(f"[Widget] load_favorites error: {e}")
        return "{}"

    def save_state(self, path: str):
        if not self._ready or not self._bridge:
            return
        self._bridge.notify_export_state()

    def load_state(self, path: str):
        try:
            state = self._state_manager.load(path)
            if self._ready and self._bridge:
                self._bridge.load_state(json.dumps(state))
        except Exception as e:
            print(f"Failed to load state: {e}")

    def save_screenshot(self, path: str):
        if self.browser:
            self.browser.grab().save(path)

    def _map_columns(self, df: pd.DataFrame) -> dict:
        targets = ['open', 'high', 'low', 'close', 'volume', 'date']
        result = {}
        lower_cols = {str(c).lower(): c for c in df.columns}
        for t in targets:
            if t in lower_cols:
                result[t] = lower_cols[t]
            elif t == 'date' and 'datetime' in lower_cols:
                result[t] = lower_cols['datetime']
            else:
                found = False
                for col in lower_cols:
                    if t in col:
                        result[t] = lower_cols[col]
                        found = True
                        break
                if not found:
                    result[t] = None
        return result
