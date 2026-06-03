"""
股票图表页面
集成 TradingViewAdvanceWidget，使用 qlib 数据源填充 K 线数据
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QComboBox, QMessageBox, QSizePolicy, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer

from ui.theme import COLORS
from ui.components.tradingview_advance_widget.widget import TradingViewAdvanceWidget


def _to_qlib_symbol(symbol: str) -> str:
    """
    将 Yahoo Finance 格式转换为 qlib 格式
    例如: 600208.SS → SH600208, 000300.SH → SH000300, AAPL → AAPL
    """
    if symbol.endswith('.SH'):
        return 'SH' + symbol.replace('.SH', '')
    if symbol.endswith('.SS'):
        return 'SH' + symbol.replace('.SS', '')
    if symbol.endswith('.SZ'):
        return 'SZ' + symbol.replace('.SZ', '')
    if symbol.endswith('.BJ'):
        return 'BJ' + symbol.replace('.BJ', '')
    return symbol


def _get_qlib_ohlcv_advanced(ticker: str, period_days: int = 365 * 5, 
                            adjust_type: str = "none", 
                            base_price: float = None) -> pd.DataFrame | None:
    """
    从 qlib 加载 K 线数据，支持多种复权类型
    
    Args:
        ticker: 股票代码
        period_days: 数据周期天数
        adjust_type: 复权类型
            - "none": 不复权 (原始价格)
            - "forward": 前复权 (历史价格保持不变)
            - "backward": 后复权 (最新价格保持不变，qlib默认)
            - "normalized": qlib归一化数据 (首日=1)
        base_price: 基准价格 (仅用于custom模式)，如最新股价
    """
    from qlib.data import D
    from datetime import date, timedelta
    import pandas as pd
    from core.app_state import get_state
    from core.qlibhelper import _check_qlib_init
    from core.event_bus import get_event_bus

    # 确保 QLib 已初始化
    state = get_state()
    if not state.qlib_initialized:
        try:
            bus = get_event_bus()
            _check_qlib_init(bus)
        except Exception as e:
            print(f"[DEBUG] QLib 初始化失败: {e}")
            return None

    reg = state.reg
    ticker = ticker.upper().strip()

    # 根据股票代码后缀自动推断区域
    if ticker.endswith('.HK'):
        target_reg = 'hk'
    elif ticker.startswith('SH') or ticker.startswith('SZ') or ticker.startswith('BJ'):
        target_reg = 'cn'
    elif ticker.endswith('USDT'):
        target_reg = 'bt'
    else:
        target_reg = reg

    if target_reg != reg:
        print(f"[DEBUG] Stock code suggests region {target_reg}, reinitializing QLib...")
        state.reg = target_reg
        state.qlib_initialized = False
        try:
            bus = get_event_bus()
            _check_qlib_init(bus)
        except Exception as e:
            print(f"[DEBUG] QLib reinitialization failed: {e}")
            return None

    reg = target_reg

    if reg == "cn":
        ticker = _to_qlib_symbol(ticker)
    elif reg == "hk":
        if not ticker.endswith('.HK'):
            ticker = ticker + '.HK'
        parts = ticker.split('.')
        if len(parts) == 2 and parts[1] == 'HK':
            ticker = parts[0].zfill(4) + '.HK'

    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=period_days + 30)).isoformat()

    # 获取数据，包含因子
    fields = ["$open", "$high", "$low", "$close", "$volume", "$factor"]
    
    try:
        df = D.features([ticker], fields, start_time=start_date, end_time=end_date)
        if df is None or df.empty:
            print(f"[DEBUG] No data found for {ticker}")
            return None

        df = df.reset_index()
        
        if "$factor" not in df.columns or len(df) == 0:
            print(f"[WARNING] No factor column found for {ticker}")
            return None
        
        # 避免除零错误
        factor_series = df["$factor"].replace(0, 1.0)
        
        # ================================================================
        # 核心：处理不同复权类型
        # ================================================================
        if adjust_type == "none":
            # 不复权：还原为原始交易价格
            print(f"[DEBUG] Calculating non-adjusted prices (original trading prices)")
            
            for col in ["$open", "$high", "$low", "$close"]:
                if col in df.columns:
                    df[col] = df[col] / factor_series
            
            # 成交量通常不需要调整，保持原始成交量
            #if "$volume" in df.columns:
            #    # 如果因子不是1，可能需要调整成交量
            #    if (factor_series != 1.0).any():
            #        df["$volume"] = df["$volume"] * factor_series
        
        elif adjust_type == "forward":
            # 前复权：以历史价格为基准，调整后续价格
            print(f"[DEBUG] Calculating forward-adjusted prices")
            
            # 获取最新因子（用于计算调整比例）
            latest_factor = factor_series.iloc[-1]
            
            if latest_factor > 0:
                # 计算调整比例
                adjustment_ratio = factor_series / latest_factor
                
                for col in ["$open", "$high", "$low", "$close"]:
                    if col in df.columns:
                        df[col] = df[col] / adjustment_ratio
                
                # 前复权成交量调整
                if "$volume" in df.columns:
                    df["$volume"] = df["$volume"] * adjustment_ratio
        
        elif adjust_type == "backward":
            # 后复权：以最新价格为基准，调整历史价格
            # 这是qlib默认的存储方式
            print(f"[DEBUG] Using backward-adjusted prices (QLib default)")
            
            # qlib已经是后复权，但我们可以确保一致性
            # 获取基准价格（如果需要标准化到特定价格）
            if base_price is not None and len(df) > 0:
                latest_close = df["$close"].iloc[-1]
                if latest_close > 0:
                    adjustment_ratio = base_price / latest_close
                    for col in ["$open", "$high", "$low", "$close"]:
                        if col in df.columns:
                            df[col] = df[col] * adjustment_ratio
                    
                    if "$volume" in df.columns:
                        df["$volume"] = df["$volume"] / adjustment_ratio
        
        elif adjust_type == "normalized":
            # 使用qlib的归一化数据（首日=1）
            print(f"[DEBUG] Using QLib normalized prices (first day = 1)")
            # 无需额外处理，使用原始qlib数据
        
        else:
            print(f"[ERROR] Unknown adjust_type: {adjust_type}, using 'none'")
            # 默认返回不复权
            for col in ["$open", "$high", "$low", "$close"]:
                if col in df.columns:
                    df[col] = df[col] / factor_series
        
        # 记录调试信息
        if len(df) > 0:
            first_close = df["$close"].iloc[0] if "$close" in df.columns else None
            last_close = df["$close"].iloc[-1] if "$close" in df.columns else None
            print(f"[DEBUG] {adjust_type}: First close: {first_close:.4f}, Last close: {last_close:.4f}")
            print(f"[DEBUG] Factor range: {df['$factor'].min():.6f} ~ {df['$factor'].max():.6f}")
        
        # 重命名列
        rename_dict = {
            "datetime": "date",
            "$open": "open",
            "$high": "high", 
            "$low": "low",
            "$close": "close",
            "$volume": "volume",
        }
        
        # 只重命名存在的列
        df = df.rename(columns={k: v for k, v in rename_dict.items() if k in df.columns})
        
        # 删除不需要的列
        columns_to_drop = ["instrument", "symbol", "$factor"]
        for col in columns_to_drop:
            if col in df.columns:
                df = df.drop(columns=[col])
        
        # 格式化日期
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        
        # 数值类型转换
        numeric_cols = ["open", "high", "low", "close", "volume"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        
        # 处理异常值
        for col in ["open", "high", "low", "close"]:
            if col in df.columns:
                df.loc[df[col] > 1e300, col] = pd.NA
        
        # 删除无效行
        df = df.dropna(subset=["close", "open", "high", "low"], how="all")
        
        if df.empty:
            print(f"[DEBUG] All data filtered out for {ticker}")
            return None
        
        # 填充成交量NaN
        if "volume" in df.columns:
            df["volume"] = df["volume"].fillna(0)
        
        return df
        
    except Exception as e:
        from loguru import logger
        logger.error(f"[ChartPage] Error loading {ticker} with adjust_type={adjust_type}: {e}")
        return None


def get_stock_data_with_adjustment(ticker: str, period_days: int = 365, 
                                  adjust_type: str = "none") -> dict:
    """
    获取股票的三种复权数据，便于比较
    
    Args:
        ticker: 股票代码
        period_days: 数据周期天数
        adjust_type: 主要返回的数据类型
    
    Returns:
        dict: 包含不同复权类型的数据
    """
    result = {}
    
    # 获取指定类型的数据
    main_df = _get_qlib_ohlcv_advanced(ticker, period_days, adjust_type)
    
    if main_df is not None:
        result[adjust_type] = main_df
        
        # 获取其他类型用于比较
        for adj_type in ["none", "forward", "backward", "normalized"]:
            if adj_type != adjust_type:
                try:
                    df = _get_qlib_ohlcv_advanced(ticker, period_days, adj_type)
                    if df is not None:
                        result[adj_type] = df
                except Exception as e:
                    print(f"[DEBUG] Failed to get {adj_type} data: {e}")
    
    return result
class _DataLoaderWorker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(self, ticker: str, period_days: int = 365, use_adj: bool = False):
        super().__init__()
        self.ticker = ticker
        self.period_days = period_days
        self.use_adj = use_adj  # 是否使用后复权
        self._stopped = False

    def stop(self):
        """停止工作线程"""
        self._stopped = True

    def run(self):
        try:
            if self._stopped:
                return
            
            #df = _get_qlib_ohlcv(self.ticker, self.period_days, use_adj=self.use_adj)
            df = _get_qlib_ohlcv_advanced(self.ticker, self.period_days, adjust_type="backward" if self.use_adj else "none")
            
            
            if self._stopped:
                return
                
            if df is None or df.empty:
                self.error.emit(f"无法获取 {self.ticker} 的数据（qlib 无此标的）")
                return
            self.finished.emit(df)
        except Exception as e:
            if not self._stopped:
                self.error.emit(f"加载失败: {e}")


class ChartPage(QWidget):
    """
    股票图表页面
    使用 TradingViewAdvanceWidget 展示 K 线图
    数据来源：qlib D.features() 直接加载
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_ticker: str = ""
        self._last_ticker: str = ""
        self._interface_load_pending: bool = False
        self._state_file = Path.home() / ".quantbyqlib" / "last_chart_ticker.txt"
        self._visible_indicators: list = []  # 保存当前可见的指标列表
        self._use_adj: bool = False  # 是否使用后复权
        self._setup_ui()
        self._connect_events()
        self._load_last_ticker()

    def _get_state_file(self) -> Path:
        path = Path.home() / ".quantbyqlib"
        path.mkdir(parents=True, exist_ok=True)
        return path / "last_chart_ticker.txt"

    def _load_last_ticker(self) -> None:
        path = self._get_state_file()
        if path.exists():
            try:
                self._last_ticker = path.read_text().strip()
            except Exception:
                self._last_ticker = ""

    def _save_last_ticker(self, ticker: str) -> None:
        path = self._get_state_file()
        try:
            path.write_text(ticker)
            self._last_ticker = ticker
        except Exception:
            pass

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._chart:
            self._chart.updateGeometry()
        # 只有在非接口调用、且没有当前加载的股票、且有历史记录时才自动加载
        if not self._interface_load_pending and not self._current_ticker and self._last_ticker:
            self._symbol_input.setText(self._last_ticker)
            self._on_load_data()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        toolbar_widget = QWidget()
        toolbar_widget.setFixedHeight(40)
        toolbar_layout = QHBoxLayout(toolbar_widget)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(8)

        toolbar_layout.addWidget(QLabel("标的:"))

        self._symbol_input = QLineEdit()
        self._symbol_input.setPlaceholderText("输入股票代码，回车搜索...")
        self._symbol_input.setFixedWidth(150)
        self._symbol_input.setMinimumHeight(26)
        self._symbol_input.returnPressed.connect(self._on_load_data)
        toolbar_layout.addWidget(self._symbol_input)

        # 复权选项
        toolbar_layout.addWidget(QLabel("复权:"))
        
        from PyQt6.QtWidgets import QRadioButton
        
        self._adj_none_radio = QRadioButton("未复权")
        self._adj_none_radio.setChecked(True)
        self._adj_none_radio.toggled.connect(lambda checked: checked and self._on_adj_mode_changed(False))
        
        self._adj_back_radio = QRadioButton("后复权")
        self._adj_back_radio.toggled.connect(lambda checked: checked and self._on_adj_mode_changed(True))
        
        toolbar_layout.addWidget(self._adj_none_radio)
        toolbar_layout.addWidget(self._adj_back_radio)

        toolbar_layout.addStretch()

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 11px;")
        toolbar_layout.addWidget(self._status_label)

        main_layout.addWidget(toolbar_widget)

        self._chart = TradingViewAdvanceWidget()
        self._chart.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )
        main_layout.addWidget(self._chart, stretch=1)

    def _connect_events(self) -> None:
        from core.event_bus import get_event_bus
        bus = get_event_bus()
        bus.stock_chart_requested.connect(self._on_interface_ticker_request)

    def _on_interface_ticker_request(self, ticker: str) -> None:
        """接口调用：标记为接口加载，忽略本地状态"""
        self._interface_load_pending = True
        self.load_ticker(ticker)
        QTimer.singleShot(100, lambda: setattr(self, '_interface_load_pending', False))

    def load_ticker(self, ticker: str) -> None:
        """外部调用：加载指定股票"""
        ticker = ticker.upper().strip()
        self._current_ticker = ticker
        self._symbol_input.setText(ticker)
        self._status_label.setText(f"正在加载 {ticker}...")
        self._load_data_thread(ticker, from_interface=True)

    def _on_adj_mode_changed(self, use_adj: bool) -> None:
        """复权模式变化处理"""
        if self._use_adj == use_adj:
            return
        
        self._use_adj = use_adj
        
        # 如果当前有加载的股票，重新加载
        if self._current_ticker:
            self._status_label.setText(f"正在切换{'后复权' if use_adj else '未复权'}...")
            self._save_visible_indicators(lambda: self._load_data_thread(self._current_ticker, from_interface=False))

    def _on_load_data(self) -> None:
        """用户输入框回车调用"""
        ticker = self._symbol_input.text().strip()
        if not ticker:
            return
        self._current_ticker = ticker
        self._save_last_ticker(ticker)
        self._status_label.setText(f"正在加载 {ticker}...")
        # 保存当前可见的指标状态
        self._save_visible_indicators()
        self._load_data_thread(ticker, from_interface=False)

    def _load_data_thread(self, ticker: str, from_interface: bool = False) -> None:
        # 如果之前有线程正在运行，先停止它
        if hasattr(self, '_thread') and hasattr(self, '_worker'):
            try:
                if self._thread.isRunning():
                    self._worker.stop()
                    self._thread.quit()
                    self._thread.wait(3000)  # 等待最多3秒
            except RuntimeError:
                # QThread 对象可能已经被删除
                pass
        
        # 创建新的工作线程（传递复权参数）
        self._worker = _DataLoaderWorker(ticker, period_days=365 * 5, use_adj=self._use_adj)
        self._thread = QThread(parent=self)  # 设置父对象，自动管理生命周期
        self._worker.moveToThread(self._thread)
        
        # 连接信号
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_data_loaded)
        self._worker.error.connect(self._on_data_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        
        # 线程结束后清理 worker
        def cleanup_worker():
            self._worker.deleteLater()
            # 不删除 _thread，让父对象管理
        
        self._thread.finished.connect(cleanup_worker)
        self._thread.start()

    def closeEvent(self, event) -> None:
        """页面关闭时清理线程"""
        if hasattr(self, '_thread') and hasattr(self, '_worker'):
            try:
                self._worker.stop()
                if self._thread.isRunning():
                    self._thread.quit()
                    self._thread.wait(3000)
            except RuntimeError:
                # QThread 对象可能已经被删除
                pass
            except Exception as e:
                print(f"[DEBUG] Error in closeEvent: {e}")
        super().closeEvent(event)

    def _on_data_loaded(self, df) -> None:
        if df is None or df.empty:
            self._status_label.setText("数据为空")
            return

        try:
            required = ['open', 'high', 'low', 'close', 'volume']
            for col in required:
                if col not in df.columns:
                    self._status_label.setText(f"数据格式错误: 缺少 {col} 列")
                    return

            print(f"[DEBUG] _on_data_loaded: _visible_indicators = {self._visible_indicators}")
            self._chart.update_chart_data(df)
            self._status_label.setText(f"已加载 {len(df)} 条 K 线数据 ({self._current_ticker})")
            
            # 保存最后一次成功加载的股票代码
            if self._current_ticker:
                self._save_last_ticker(self._current_ticker)
            
            # 延迟加载默认指标（给JS组件更多初始化时间）
            QTimer.singleShot(1500, self._load_default_indicators)
        except Exception as e:
            from loguru import logger
            logger.error(f"[ChartPage] 更新图表失败: {e}")
            self._status_label.setText(f"更新图表失败: {e}")

    def _save_visible_indicators(self, callback=None) -> None:
        """保存当前可见的指标列表"""
        if not hasattr(self, '_chart') or not self._chart._ready:
            print("[DEBUG] Chart not ready, skipping save indicators")
            if callback:
                callback()
            return
        
        js_code = """
        (function() {
            var visible = [];
            
            // 获取普通指标
            if (window.indicatorEngine && window.indicatorEngine._visibleMap) {
                window.indicatorEngine._visibleMap.forEach((v, k) => {
                    if (v === true) visible.push(k);
                });
            }
            
            // 获取组合预设状态
            if (window.combinedPresets && window.combinedPresets._active) {
                for (var key in window.combinedPresets._active) {
                    if (window.combinedPresets._active[key]) {
                        visible.push('combo_' + key);
                    }
                }
            }
            
            return visible;
        })();
        """
        
        def on_result(res):
            self._visible_indicators = res if isinstance(res, list) else []
            print(f"[DEBUG] Saved visible indicators: {self._visible_indicators}")
            if callback:
                callback()
        
        self._chart.browser.page().runJavaScript(js_code, on_result)

    def _load_default_indicators(self) -> None:
        """加载默认指标（仅在首次加载时）"""
        if not self._chart._ready or not self._chart._bridge:
            print("[DEBUG] Chart not ready yet, retrying...")
            QTimer.singleShot(500, self._load_default_indicators)
            return
        
        # JavaScript 端的 timeframeController 会自动保存和恢复指标
        # Python 端只在首次加载（没有保存的指标）时加载默认指标
        if self._visible_indicators and len(self._visible_indicators) > 0:
            print(f"[DEBUG] Skipping default indicators load, JS will restore saved indicators")
            return
        
        print(f"[DEBUG] Loading default indicators (first load)")
        
        # 加载默认指标：主图 SMA组合，副图 ZeroLagMACD
        js_code = """
        (function() {
            var results = [];
            
            // 添加 SMA组合 (主图)
            if (window.combinedPresets && window.indicatorEngine) {
                try {
                    window.combinedPresets.toggle('ALL_MAS');
                    results.push('SMA组合已加载');
                } catch(e) {
                    results.push('SMA组合加载失败: ' + e.message);
                }
            }
            
            // 添加 ZeroLagMACD (副图)
            if (window.indicatorEngine) {
                try {
                    window.indicatorEngine.toggle('ZeroLagMACD');
                    results.push('ZeroLagMACD已加载');
                } catch(e) {
                    results.push('ZeroLagMACD加载失败: ' + e.message);
                }
            }
            
            return results.join(', ');
        })();
        """
        
        def on_result(result):
            print(f"[DEBUG] Default indicators loaded: {result}")
        
        self._chart.browser.page().runJavaScript(js_code, on_result)

    def _restore_visible_indicators(self) -> None:
        """恢复之前保存的可见指标"""
        if not self._visible_indicators:
            print("[DEBUG] No visible indicators to restore")
            return
        
        indicators = []
        combo_presets = []
        
        # 分离组合预设和普通指标
        for item in self._visible_indicators:
            if item.startswith('combo_'):
                combo_presets.append(item.replace('combo_', ''))
            else:
                indicators.append(item)
        
        print(f"[DEBUG] Restoring indicators: {indicators}, combos: {combo_presets}")
        
        # 构建恢复指标的JS代码
        js_parts = []
        
        # 先恢复组合预设（全部恢复）
        for preset in combo_presets:
            js_parts.append(f"""
                if (window.combinedPresets && window.indicatorEngine) {{
                    console.log('[RESTORE] Toggling combo preset: {preset}');
                    window.combinedPresets.toggle('{preset}');
                }} else {{
                    console.log('[RESTORE] Components not ready for combo: {preset}');
                }}
            """)
        
        # 恢复普通指标（全部恢复）
        for indicator_id in indicators:
            js_parts.append(f"""
                if (window.indicatorEngine) {{
                    console.log('[RESTORE] Toggling indicator: {indicator_id}');
                    window.indicatorEngine.toggle('{indicator_id}');
                }} else {{
                    console.log('[RESTORE] indicatorEngine not ready for: {indicator_id}');
                }}
            """)
        
        js_code = f"""
        (function() {{
            console.log('[RESTORE] Starting restore, indicators: {indicators}, combos: {combo_presets}');
            {''.join(js_parts)}
            return 'Restored ' + {len(indicators) + len(combo_presets)} + ' items';
        }})();
        """
        
        def on_result(result):
            print(f"[DEBUG] Indicators restored: {result}")
        
        self._chart.browser.page().runJavaScript(js_code, on_result)

    def _on_data_error(self, error_msg: str) -> None:
        self._status_label.setText(error_msg)
        QMessageBox.warning(self, "警告", error_msg)
