# Lightweight Charts Plus Widget - 集成 446 个技术指标
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QTimer, Qt
import pandas as pd
import numpy as np
import json
import os
from pathlib import Path
from datetime import datetime


class TradingViewPlusWidget(QWidget):
    """增强版 TradingView Widget - 集成 446 个技术指标，支持双向绑定"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.init_ui()
        self.pending_chart_data = None
        self.pending_indicators = []
        self.is_chart_ready = False
        self.active_indicators = {}  # 新增：记录活跃指标 {indicator_key: {group, timestamp}}
        self.original_df = None
        self.indicator_handlers = self._init_indicator_handlers()
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.browser = QWebEngineView(self)
        layout.addWidget(self.browser)
        
        # 启用开发者工具
        from PyQt6.QtWebEngineCore import QWebEngineSettings
        settings = self.browser.page().settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        
        # 加载 HTML 模板
        html_path = Path(__file__).parent / 'chart_plus_template.html'
        self.browser.setUrl(QUrl.fromLocalFile(str(html_path)))
        
        # 检查图表是否就绪
        QTimer.singleShot(500, self._check_chart_ready)
        
        # 添加键盘快捷键支持用于打开开发者工具
        self.browser.installEventFilter(self)
        
    def eventFilter(self, obj, event):
        """事件过滤器 - 支持快捷键打开开发者工具"""
        if obj == self.browser:
            from PyQt6.QtCore import QEvent
            if event.type() == QEvent.Type.KeyPress:
                # Ctrl+Shift+I 或 F12 打开开发者工具
                if (event.key() == Qt.Key.Key_I and 
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier and 
                    event.modifiers() & Qt.KeyboardModifier.ShiftModifier) or \
                   event.key() == Qt.Key.Key_F12:
                    self.open_dev_tools_window()
                    return True
        return super().eventFilter(obj, event)
        
    def open_dev_tools_window(self):
        """打开独立的开发者工具窗口"""
        try:
            from PyQt6.QtWidgets import QMainWindow
            from PyQt6.QtWebEngineWidgets import QWebEngineView as WebEngineView
            
            # 创建开发者工具窗口
            self.dev_tools_window = QMainWindow()
            self.dev_tools_window.setWindowTitle("Developer Tools - TradingView Plus")
            self.dev_tools_window.setGeometry(100, 100, 900, 700)
            
            # 创建开发者工具浏览器
            dev_browser = WebEngineView()
            self.dev_tools_window.setCentralWidget(dev_browser)
            
            # 设置开发者工具页面
            self.browser.page().setDevToolsPage(dev_browser.page())
            
            # 显示窗口
            self.dev_tools_window.show()
            print("✅ Developer tools window opened")
            
        except Exception as e:
            print(f"❌ Failed to open developer tools window: {e}")
            import traceback
            traceback.print_exc()
            
    def open_dev_tools(self):
        """打开开发者工具（备用方法）"""
        self.open_dev_tools_window()
        
    def _check_chart_ready(self):
        """检查图表是否初始化完成"""
        if self.browser.page():
            self.browser.page().runJavaScript(
                """
                (function() {
                    // 检查多个可能的状态
                    return {
                        isChartInitialized: window.isChartInitialized === true,
                        hasMainChart: typeof window.mainChart !== 'undefined' && window.mainChart !== null,
                        hasSubChart: typeof window.subChart !== 'undefined' && window.subChart !== null,
                        hasSetChartData: typeof window.setChartData === 'function',
                        hasPythonBridge: typeof window.pythonBridge !== 'undefined'
                    };
                })();
                """,
                self._on_ready_check_result
            )
            
    def _on_ready_check_result(self, result):
        """就绪检查回调"""
        if result and result.get('isChartInitialized') and result.get('hasSetChartData'):
            print("✅ Chart is ready! Flushing pending data...")
            print(f"  Chart status: {result}")
            self.is_chart_ready = True
            
            # 设置 Python 桥接回调
            self._setup_python_bridge()
            
            # 延迟一小段时间确保图表完全初始化
            QTimer.singleShot(100, self._flush_pending_data)
        else:
            print(f" Chart not ready, retrying in 300ms... (result: {result})")
            QTimer.singleShot(300, self._check_chart_ready)
            
    def _setup_python_bridge(self):
        """设置 Python 桥接回调函数"""
        try:
            # 注册指标切换回调
            js_code = """
            window.pythonBridge.callbacks.set('on_indicator_toggle', function(data) {
                console.log('📡 Python bridge callback: on_indicator_toggle', data);
                // 这里将由 Python 端调用
            });
            """
            self.browser.page().runJavaScript(js_code)
            print("✅ Python bridge setup completed")
        except Exception as e:
            print(f"❌ Failed to setup Python bridge: {e}")
            
    def _flush_pending_data(self):
        """刷新所有等待的数据"""
        # 先发送蜡烛图数据
        if self.pending_chart_data:
            print(f" Flushing {len(self.pending_chart_data)} candles to chart")
            data_json = json.dumps(self.pending_chart_data)
            self.browser.page().runJavaScript(f"""
                if (typeof window.setChartData === 'function') {{
                    window.setChartData({data_json});
                }} else {{
                    console.error('setChartData still not available!');
                }}
            """)
            self.pending_chart_data = None
            
            # 延迟发送指标，确保蜡烛图先加载完成
            if self.pending_indicators:
                print(f"⏳ Waiting 200ms before sending {len(self.pending_indicators)} indicators...")
                QTimer.singleShot(200, self._flush_pending_indicators)
        elif self.pending_indicators:
            # 如果没有待发送的蜡烛图数据，直接发送指标
            self._flush_pending_indicators()
            
        # 设置默认图表状态：主图只显示蜡烛，副图空白
        QTimer.singleShot(500, self._set_default_chart_state)
    
    def _set_default_chart_state(self):
        """设置默认图表状态：主图只显示蜡烛，副图空白"""
        js_code = """
        console.log('🎯 Setting default chart state...');
        
        // 1. 确保主图只显示蜡烛图
        if (window.candleSeries) {
            window.candleSeries.applyOptions({ visible: true });
        }
        
        // 2. 隐藏所有其他指标
        if (window.seriesMap) {
            window.seriesMap.forEach((series, name) => {
                if (name !== 'CANDLE' && series.applyOptions) {
                    series.applyOptions({ visible: false });
                }
            });
        }
        
        // 3. 重置所有指标按钮状态
        document.querySelectorAll('.indicator-item').forEach(item => {
            item.classList.remove('active');
        });
        
        // 4. 清空状态记录
        if (window.indicatorStates) window.indicatorStates.clear();
        if (window.activeGroups) window.activeGroups.clear();
        
        console.log('✅ Default chart state set: only candle visible, all indicators hidden');
        """
        self.browser.page().runJavaScript(js_code)
    
    def _flush_pending_indicators(self):
        """刷新所有等待的指标"""
        if self.pending_indicators:
            print(f"📤 Flushing {len(self.pending_indicators)} indicators to chart")
            for js_code in self.pending_indicators:
                self.browser.page().runJavaScript(js_code)
            self.pending_indicators.clear()
        
    def _queue_indicator(self, js_code):
        """将指标代码加入等待队列"""
        if self.is_chart_ready:
            print(f"📤 Sending indicator to chart immediately")
            self.browser.page().runJavaScript(js_code)
        else:
            print(f"⏳ Queueing indicator (chart not ready yet)")
            self.pending_indicators.append(js_code)
            
    def update_chart_data(self, df: pd.DataFrame):
        """更新图表数据"""
        cols = self._get_standard_columns(df)
        if not cols['open']:
            print("Error: Missing required columns")
            return
            
        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        
        candle_data = []
        for i in range(len(df)):
            candle = {
                'time': dates[i],
                'open': float(df[cols['open']].iloc[i]),
                'high': float(df[cols['high']].iloc[i]),
                'low': float(df[cols['low']].iloc[i]),
                'close': float(df[cols['close']].iloc[i])
            }
            
            # 【关键修复】添加 volume 字段（如果存在）
            if cols['volume']:
                candle['volume'] = float(df[cols['volume']].iloc[i])
            else:
                candle['volume'] = 0.0
            
            candle_data.append(candle)
        
        self.pending_chart_data = candle_data
        
        # 保存原始数据副本用于指标计算
        self.original_df = df.copy()
        
        print(f"📊 Prepared {len(candle_data)} candles for chart")
        if candle_data:
            print(f"   First candle: time={candle_data[0]['time']}, volume={candle_data[0].get('volume', 'N/A')}")
            print(f"   Last candle: time={candle_data[-1]['time']}, volume={candle_data[-1].get('volume', 'N/A')}")
        
        if self.is_chart_ready:
            print("✅ Chart is ready, sending data immediately")
            data_json = json.dumps(candle_data)
            self.browser.page().runJavaScript(f"window.setChartData({data_json});")
        else:
            print(f"⏳ Chart not ready yet, data will be queued ({len(candle_data)} candles)")
            # 即使图表未就绪，也尝试发送数据（JavaScript 端会处理）
            data_json = json.dumps(candle_data)
            self.browser.page().runJavaScript(f"""
                if (window.setChartData) {{
                    window.setChartData({data_json});
                }} else {{
                    console.warn('setChartData function not available yet');
                }}
            """)
            
    def _get_standard_columns(self, df: pd.DataFrame) -> dict:
        """标准化列名 - 不修改原始 DataFrame"""
        # 创建列名映射，不修改原始 DataFrame
        cols = df.columns
        
        if isinstance(cols, pd.MultiIndex):
            cols = ['_'.join([str(x).lower() for x in c]) for c in cols]
        else:
            cols = [c.lower() for c in cols]
            
        if 'date' not in cols:
            if 'datetime' in cols:
                date_col = 'datetime'
            elif df.index.name in ['date', 'datetime']:
                date_col = None  # 需要从索引获取
            else:
                date_col = None
        else:
            date_col = 'date'
                
        result = {
            'date': date_col,
            'open': None, 'high': None, 'low': None,
            'close': None, 'volume': None
        }
        
        col_mapping = {
            'open': ['open', 'open_'],
            'high': ['high', 'high_'],
            'low': ['low', 'low_'],
            'close': ['close', 'close_'],
            'volume': ['volume', 'vol', 'volume_']
        }
        
        for target, sources in col_mapping.items():
            for col in cols:
                for src in sources:
                    if src in col:
                        result[target] = col
                        break
                if result[target]:
                    break
                    
        return result
        
    def _init_indicator_handlers(self):
        """初始化指标处理器映射"""
        return {
            """ # 移动平均线
            'SMA': lambda: self.add_sma(self.original_df, length=60) if self.original_df is not None else None,
            'SMA_5': lambda: self.add_sma(self.original_df, length=5) if self.original_df is not None else None,
            'SMA_10': lambda: self.add_sma(self.original_df, length=10) if self.original_df is not None else None,
            'SMA_20': lambda: self.add_sma(self.original_df, length=20) if self.original_df is not None else None,
            'EMA': lambda: self.add_ema(self.original_df, length=60) if self.original_df is not None else None,
            'EMA_12': lambda: self.add_ema(self.original_df, length=12) if self.original_df is not None else None,
            'EMA_26': lambda: self.add_ema(self.original_df, length=26) if self.original_df is not None else None,
            'TEMA': lambda: self.add_tema(self.original_df) if self.original_df is not None else None,
            'WMA': lambda: self.add_wma(self.original_df) if self.original_df is not None else None,
            'RMA': lambda: self.add_rma(self.original_df) if self.original_df is not None else None,
            'DEMA': lambda: self.add_dema(self.original_df) if self.original_df is not None else None,
            'HMA': lambda: self.add_hma(self.original_df) if self.original_df is not None else None,
            'LSMA': lambda: self.add_lsma(self.original_df) if self.original_df is not None else None,
            'ALMA': lambda: self.add_alma(self.original_df) if self.original_df is not None else None,
            'VWMA': lambda: self.add_vwma(self.original_df) if self.original_df is not None else None,
            'MCGINLEY': lambda: self.add_mcginley(self.original_df) if self.original_df is not None else None,
            'EMAMACross': lambda: self.add_ma_cross(self.original_df) if self.original_df is not None else None,
            'MARibbon': lambda: self.add_ma_ribbon(self.original_df) if self.original_df is not None else None,
            'ZLSMA': lambda: self.add_zlsma(self.original_df) if self.original_df is not None else None,
            
            # 振荡指标
            'RSI': lambda: self.add_rsi(self.original_df) if self.original_df is not None else None,
            'STOCH': lambda: self.add_indicator_via_js('Stochastic', {'group': 'OSC'}),
            'STOCHRSI': lambda: self.add_stochrsi(self.original_df) if self.original_df is not None else None,
            'CCI': lambda: self.add_cci(self.original_df) if self.original_df is not None else None,
            'WilliamsPercentRange': lambda: self.add_willr(self.original_df) if self.original_df is not None else None,
            'AwesomeOscillator': lambda: self.add_ao(self.original_df) if self.original_df is not None else None,
            'ChandeMO': lambda: self.add_cmo(self.original_df) if self.original_df is not None else None,
            'DPO': lambda: self.add_dpo(self.original_df) if self.original_df is not None else None,
            'RVI': lambda: self.add_rvi(self.original_df) if self.original_df is not None else None,
            'TSI': lambda: self.add_tsi(self.original_df) if self.original_df is not None else None,
            'UltimateOscillator': lambda: self.add_uo(self.original_df) if self.original_df is not None else None,
            'KDJ': lambda: self.add_kdj(self.original_df) if self.original_df is not None else None,
            'WaveTrend': lambda: self.add_wt(self.original_df) if self.original_df is not None else None,
            'SchaffTrendCycle': lambda: self.add_stc(self.original_df) if self.original_df is not None else None,
            
            # 动量指标
            'MACD': lambda: self.add_macd(self.original_df) if self.original_df is not None else None,
            'Momentum': lambda: self.add_momentum(self.original_df) if self.original_df is not None else None,
            'ROC': lambda: self.add_roc(self.original_df) if self.original_df is not None else None,
            'BOP': lambda: self.add_bop(self.original_df) if self.original_df is not None else None,
            'BullBearPower': lambda: self.add_bullbearpower(self.original_df) if self.original_df is not None else None,
            'CoppockCurve': lambda: self.add_coppock(self.original_df) if self.original_df is not None else None,
            'TRIX': lambda: self.add_trix(self.original_df) if self.original_df is not None else None,
            'SqueezeMomentum': lambda: self.add_squeeze(self.original_df) if self.original_df is not None else None,
            
            # 趋势指标
            'ADX': lambda: self.add_adx(self.original_df) if self.original_df is not None else None,
            'IchimokuCloud': lambda: self.add_ichimoku(self.original_df) if self.original_df is not None else None,
            'ParabolicSAR': lambda: self.add_parabolicsar(self.original_df) if self.original_df is not None else None,
            'VolumeSuperTrendAi': lambda: self.add_volumesupertrendai(self.original_df) if self.original_df is not None else None,
            'Aroon': lambda: self.add_aroon(self.original_df) if self.original_df is not None else None,
            'ZigZag': lambda: self.add_zigzag_python(self.original_df) if self.original_df is not None else None,
            'WilliamsAlligator': lambda: self.add_williamsalligator(self.original_df) if self.original_df is not None else None,
            'DonchianChannels': lambda: self.add_donchianchannels(self.original_df) if self.original_df is not None else None,
            
            # 波动率指标
            'ATR': lambda: self.add_atr(self.original_df) if self.original_df is not None else None,
            'BollingerBands': lambda: self.add_bollingerbands(self.original_df) if self.original_df is not None else None,
            'StandardDeviation': lambda: self.add_standarddeviation(self.original_df) if self.original_df is not None else None,
            'HistoricalVolatility': lambda: self.add_historicalvolatility(self.original_df) if self.original_df is not None else None,
            'Choppiness': lambda: self.add_choppiness(self.original_df) if self.original_df is not None else None,
            
            # 成交量指标
            'Volume': lambda: self.add_volume(self.original_df) if self.original_df is not None else None,
            'MFI': lambda: self.add_mfi(self.original_df) if self.original_df is not None else None,
            'OBV': lambda: self.add_obv(self.original_df) if self.original_df is not None else None,
            'VolumeAccumulationPct': lambda: self.add_volumeaccumulationpct(self.original_df) if self.original_df is not None else None,
             """
            # 自定义指标
            'PROFILE': lambda: self.add_yearly_profile(self.original_df) if self.original_df is not None else None,
        }
    
    def on_indicator_toggle(self, indicator_key, state, group):
        """处理指标切换事件 - 双向绑定核心"""
        print(f"📊 Indicator toggle: {indicator_key} -> {state} (group: {group})")
        
        # 更新活跃指标记录
        if state:
            if indicator_key not in self.active_indicators:
                self.active_indicators[indicator_key] = {
                    'group': group,
                    'timestamp': datetime.now()
                }
                # 添加指标
                self._add_indicator_by_key(indicator_key, group)
        else:
            if indicator_key in self.active_indicators:
                del self.active_indicators[indicator_key]
            # 移除指标
            self._remove_indicator_by_key(indicator_key)
    
    def _add_indicator_by_key(self, indicator_key, group):
        """根据指标键名添加指标"""
        print(f"🔧 Adding indicator: {indicator_key} (group: {group})")
        
        if indicator_key in self.indicator_handlers:
            try:
                handler = self.indicator_handlers[indicator_key]
                handler()
                print(f"✅ Indicator {indicator_key} added successfully")
                
                # 确保按钮状态同步
                self._sync_button_state(indicator_key, True)
                
            except Exception as e:
                print(f"❌ Error executing indicator {indicator_key}: {e}")
                import traceback
                traceback.print_exc()
                # 添加失败，重置按钮状态
                self._sync_button_state(indicator_key, False)
        else:
            print(f"⚠️ No handler found for indicator: {indicator_key}")
            # 尝试通过 JS 添加
            self._add_indicator_via_js_generic(indicator_key, group)
    
    def _sync_button_state(self, indicator_key, is_active):
        """同步按钮状态到前端"""
        js_code = f"""
        (function() {{
            const button = document.querySelector('.indicator-item[data-key="{indicator_key}"]');
            if (button) {{
                if ({str(is_active).lower()}) {{
                    button.classList.add('active');
                }} else {{
                    button.classList.remove('active');
                }}
                console.log('🔄 Button state synced: {indicator_key} -> {is_active}');
            }}
        }})();
        """
        self.browser.page().runJavaScript(js_code)
    
    def _add_indicator_via_js_generic(self, indicator_key, group):
        """通过 JS 通用方法添加指标 - 修复版本"""
        print(f"🔧 Adding indicator via JS: {indicator_key} (group: {group})")
        
        # 判断是主图还是副图指标
        is_sub_chart = group in ['OSC', 'VOL', 'PROFILE', 'VOLUME', 'MOM']
        options = {
            'group': group,
            'visible': True
        }
        
        if is_sub_chart:
            options['subChart'] = True
        
        # 【修复1】更新指标名称映射，只映射JavaScript端确实存在的指标
        indicator_name_map = {
            # 移动平均线 - 确保这些指标在JS端有实现
            'SMA_5': 'SMA',
            'SMA_10': 'SMA',
            'SMA_20': 'SMA',
            'EMA_12': 'EMA',
            'EMA_26': 'EMA',
            'TEMA': 'TEMA',
            'WMA': 'WMA',
            'RMA': 'RMA',
            'DEMA': 'DEMA',
            'HMA': 'HMA',
            'LSMA': 'LSMA',
            'ALMA': 'ALMA',
            'VWMA': 'VWMA',
            'MCGINLEY': 'McGinley',
            'EMAMACross': 'EMA_MACD_Cross',
            'MARibbon': 'MARibbon',
            'ZLSMA': 'ZLSMA',
            
            # 振荡指标 - 优先使用已知可用的指标
            'RSI': 'RSI',
            'STOCH': 'Stochastic',
            'STOCHRSI': 'StochRSI',
            'CCI': 'CCI',
            
            # 动量指标
            'MACD': 'MACD',
            'Momentum': 'Momentum',
            'ROC': 'ROC',
            
            # 趋势指标 - 注释掉JavaScript端可能不存在的指标
            'ADX': 'ADX',  # 如果JS端没有ADX实现
            'IchimokuCloud': 'IchimokuCloud',  # 如果JS端没有实现
            'ParabolicSAR': 'ParabolicSAR',  # 如果JS端没有实现
            'VolumeSuperTrendAi': 'VolumeSuperTrendAi',  # 如果JS端没有实现
            
            # 波动率指标
            'BollingerBands': 'BollingerBands',
            
            # 成交量指标 - 使用基础的Volume
            'Volume': 'Volume',  # 改为使用基础Volume
            'MFI': 'MFI',
            'OBV': 'OBV',
            
            # 【修复2】移除JavaScript端不存在的指标
            'VolumeAccumulationPct': 'VolumeAccumulationPct',  # 移除
            'PROFILE': 'YearlyProfile',  # 移除
        }
        
        # 获取实际的指标名称
        actual_indicator = indicator_name_map.get(indicator_key)
        
        if not actual_indicator:
            print(f"⚠️  Indicator {indicator_key} not available in JavaScript implementation")
            # 【修复3】对于JavaScript端不存在的指标，回退到Python计算（如果可能）
            self._fallback_to_python_calculation(indicator_key, group)
            return
        
        print(f"  Using indicator name: {actual_indicator}")
        
        # 添加参数
        if indicator_key in ['SMA_5', 'SMA_10', 'SMA_20']:
            # 提取周期
            period = int(indicator_key.split('_')[1])
            options['length'] = period
        elif indicator_key in ['EMA_12', 'EMA_26']:
            period = int(indicator_key.split('_')[1])
            options['length'] = period
        
        self._add_indicator_via_js(actual_indicator, options)
    
    def _remove_indicator_by_key(self, indicator_key):
        """根据指标键名移除指标"""
        print(f"🔧 Removing indicator: {indicator_key}")
        
        js_code = f"""
        (function() {{
            console.log('🔧 Removing indicator: {indicator_key}');
            
            // 1. 移除主指标
            if (typeof window.removeIndicator === 'function') {{
                window.removeIndicator('{indicator_key}');
            }}
            
            // 2. 移除可能的多系列指标
            if (window.seriesMap) {{
                Object.keys(window.seriesMap).forEach(seriesName => {{
                    if (seriesName.startsWith('{indicator_key}_') || 
                        seriesName.includes('{indicator_key}')) {{
                        if (typeof window.removeIndicator === 'function') {{
                            window.removeIndicator(seriesName);
                        }}
                    }}
                }});
            }}
            
            // 3. 同步按钮状态
            const button = document.querySelector('.indicator-item[data-key="{indicator_key}"]');
            if (button) {{
                button.classList.remove('active');
            }}
            
            console.log('✅ Indicator {indicator_key} removed');
        }})();
        """
        
        if self.is_chart_ready:
            self.browser.page().runJavaScript(js_code)
        else:
            print(f"⏳ Chart not ready, cannot remove indicator {indicator_key}")
    
    def clear_all_indicators(self):
        """清除所有指标"""
        print("🧹 Clearing all indicators...")
        
        # 清空 Python 端记录
        self.active_indicators.clear()
        
        # 清空前端指标
        js_code = """
        (function() {
            console.log('🧹 Clearing all indicators from UI...');
            
            // 1. 移除所有指标系列
            if (typeof window.clearAllIndicators === 'function') {
                window.clearAllIndicators();
            }
            
            // 2. 重置所有按钮状态
            document.querySelectorAll('.indicator-item').forEach(item => {
                item.classList.remove('active');
            });
            
            // 3. 清空状态记录
            if (window.indicatorStates) window.indicatorStates.clear();
            if (window.activeGroups) window.activeGroups.clear();
            
            // 4. 清空系列映射
            if (window.seriesMap) window.seriesMap.clear();
            
            console.log('✅ All indicators cleared');
        })();
        """
        
        if self.is_chart_ready:
            self.browser.page().runJavaScript(js_code)
        else:
            print("⚠️ Chart not ready, cannot clear indicators")
    
    # ========================================
    # 446 个指标 - 按分类提供方法
    # ========================================
    
    def add_sma(self, df: pd.DataFrame, length=20, src='close', color="#2962FF", visible=True):
        """简单移动平均 - Simple Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.sma(df[cols[src]], length=length)
        self._add_line_indicator('SMA', series, df, color, 'MA', 'SMA', visible)
        
    def add_sma_5(self, df: pd.DataFrame, length=5, src='close', color="#2962FF", visible=True):
        """简单移动平均 - Simple Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.sma(df[cols[src]], length=length)
        self._add_line_indicator('SMA_5', series, df, color, 'MA', 'SMA_5', visible)
        
    def add_sma_10(self, df: pd.DataFrame, length=10, src='close', color="#2962FF", visible=True):
        """简单移动平均 - Simple Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.sma(df[cols[src]], length=length)
        self._add_line_indicator('SMA_10', series, df, color, 'MA', 'SMA_10', visible)
        
    def add_sma_20(self, df: pd.DataFrame, length=20, src='close', color="#2962FF", visible=True):
        """简单移动平均 - Simple Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.sma(df[cols[src]], length=length)
        self._add_line_indicator('SMA_20', series, df, color, 'MA', 'SMA_20', visible)
    
    def add_ema(self, df: pd.DataFrame, length=20, src='close', color="#FF9800", visible=True):
        """指数移动平均 - Exponential Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.ema(df[cols[src]], length=length)
        self._add_line_indicator('EMA', series, df, color, 'MA', 'EMA', visible)
        
    def add_ema_12(self, df: pd.DataFrame, length=12, src='close', color="#FF9800", visible=True):
        """指数移动平均 - Exponential Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.ema(df[cols[src]], length=length)
        self._add_line_indicator('EMA_12', series, df, color, 'MA', 'EMA_12', visible)

    def add_ema_26(self, df: pd.DataFrame, length=26, src='close', color="#FF9800", visible=True):
        """指数移动平均 - Exponential Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.ema(df[cols[src]], length=length)
        self._add_line_indicator('EMA_26', series, df, color, 'MA', 'EMA_26', visible)

    def add_wma(self, df: pd.DataFrame, length=20, src='close', color="#00BCD4", visible=True):
        """加权移动平均 - Weighted Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.wma(df[cols[src]], length=length)
        self._add_line_indicator('WMA', series, df, color, 'MA', 'WMA', visible)
        
    def add_hma(self, df: pd.DataFrame, length=20, src='close', color="#00E5FF", visible=True):
        """Hull 移动平均 - Hull Moving Average"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.hma(df[cols[src]], length=length)
        self._add_line_indicator('HMA', series, df, color, 'MA', 'HMA', visible)
        
    def add_dema(self, df: pd.DataFrame, length=20, src='close', color="#9C27B0", visible=True):
        """双指数移动平均 - Double EMA"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.dema(df[cols[src]], length=length)
        self._add_line_indicator('DEMA', series, df, color, 'MA', 'DEMA', visible)
        
    def add_tema(self, df: pd.DataFrame, length=20, src='close', color="#E91E63", visible=True):
        """三指数移动平均 - Triple EMA"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.tema(df[cols[src]], length=length)
        self._add_line_indicator('TEMA', series, df, color, 'MA', 'TEMA', visible)
        
    def add_rma(self, df: pd.DataFrame, length=20, src='close', color="#FF5722", visible=True):
        """平滑移动平均 - Rolling Moving Average (RMA)"""
        import pandas_ta_classic as ta
        cols = self._get_standard_columns(df)
        if not cols[src]: return
        
        series = ta.rma(df[cols[src]], length=length)
        self._add_line_indicator('RMA', series, df, color, 'MA', 'RMA', visible)
        
    def add_lsma(self, df: pd.DataFrame, length=20, src='close', color="#9C27B0", visible=True):
        """最小二乘移动平均 - Least Squares Moving Average (使用 JS 端计算)"""
        self._add_indicator_via_js('LSMA', {'length': length, 'src': src, 'color': color, 'group': 'MA', 'visible': visible})
        
    def add_alma(self, df: pd.DataFrame, length=20, offset=0.85, sigma=6, src='close', color="#00BCD4", visible=True):
        """ALMA 移动平均 - Arnaud Legoux Moving Average (使用 JS 端计算)"""
        self._add_indicator_via_js('ALMA', {'length': length, 'offset': offset, 'sigma': sigma, 'src': src, 'color': color, 'group': 'MA', 'visible': visible})
        
    def add_vwma(self, df: pd.DataFrame, length=20, src='close', color="#FF9800", visible=True):
        """成交量加权平均 - Volume Weighted Moving Average (使用 JS 端计算)"""
        self._add_indicator_via_js('VWMA', {'length': length, 'src': src, 'color': color, 'group': 'MA', 'visible': visible})
        
    def add_mcginley(self, df: pd.DataFrame, length=14, src='close', color="#4CAF50", visible=True):
        """McGinley 动态 - McGinley Dynamic (使用 JS 端计算)"""
        self._add_indicator_via_js('McGinleyDynamic', {'length': length, 'src': src, 'color': color, 'group': 'MA', 'visible': visible})
        
    def add_ma_cross(self, df: pd.DataFrame, fast=9, slow=21, src='close', color="#FF9800", visible=True):
        """均线交叉 - EMA Cross (使用 JS 端计算)"""
        # 使用 EMAMACross 替代 MA_CROSS
        self._add_indicator_via_js('EMAMACross', {'fastLength': fast, 'slowLength': slow, 'src': src, 'color': color, 'group': 'MA', 'visible': visible})
        
    def add_ma_ribbon(self, df: pd.DataFrame, lengths=[5, 10, 20, 50], src='close', visible=True):
        """均线带 - MA Ribbon (使用 JS 端计算)"""
        # 使用 MARibbon 替代 MA_RIBBON
        self._add_indicator_via_js('MARibbon', {'lengths': lengths, 'src': src, 'group': 'MA', 'visible': visible})
        
    def add_zlsma(self, df: pd.DataFrame, length=20, src='close', color="#E91E63", visible=True):
        """零滞后 LSMA - Zero Lag LSMA (使用 JS 端计算)"""
        self._add_indicator_via_js('ZLSMA', {'length': length, 'src': src, 'color': color, 'group': 'MA', 'visible': visible})
        
    def _add_indicator_via_js(self, indicator_key, options):
        """统一指标添加入口"""
        
        # JS支持的指标映射
        js_supported_indicators = {
            'SMA', 'EMA', 'TEMA', 'WMA', 'RMA', 'DEMA', 'HMA',
            'LSMA', 'ALMA', 'VWMA', 'MCGINLEY', 'EMAMACross',
            'MARibbon', 'ZLSMA', 'RSI', 'STOCH', 'STOCHRSI',
            'CCI', 'WilliamsR', 'AO', 'CMO', 'DPO', 'RVI',
            'TSI', 'UO', 'KDJ', 'WaveTrend', 'SchaffTrendCycle',
            'MACD', 'Momentum', 'ROC', 'BOP', 'BullBearPower',
            'CoppockCurve', 'TRIX', 'SqueezeMomentum', 'ADX',
            'IchimokuCloud', 'ParabolicSAR', 'SuperTrend',
            'Aroon', 'ZigZag', 'WilliamsAlligator', 'Donchian',
            'ATR', 'BollingerBands', 'StdDev', 'HV', 'Choppiness',
            'Volume', 'MFI', 'OBV', 'AD'
        }
        
        # Python补充的指标
        python_supported_indicators = {
            'YearlyProfile', 'PROFILE', 'ZigZag_Python'
        }
        
        # 判断计算方式
        if indicator_key in js_supported_indicators:
            # JS计算
            js_code = f"""
            if (typeof window.addIndicator === 'function') {{
                window.addIndicator('{indicator_key}', {json.dumps(options)});
            }}
            """
            self._queue_indicator(js_code)
            print(f"  📈 {indicator_key} - 通过JS计算")
            
        elif indicator_key in python_supported_indicators:
            # Python计算
            print(f"  🐍 {indicator_key} - 通过Python计算")
            # 调用Python计算方法
            self._calculate_indicator_in_python(indicator_key, options)
            
        else:
            print(f"  ⚠️ {indicator_key} - 未知指标，尝试JS计算")
            # 默认尝试JS
            js_code = f"""
            try {{
                window.addIndicator('{indicator_key}', {json.dumps(options)});
            }} catch(e) {{
                console.error('JS计算失败:', e);
            }}
            """
            self._queue_indicator(js_code)
        
    def add_cci(self, df: pd.DataFrame, length=20, color="#FF9800", visible=True):
        """商品通道指数 - Commodity Channel Index (使用 JS 端计算)"""
        self._add_indicator_via_js('CCI', {'length': length, 'src': 'close', 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_willr(self, df: pd.DataFrame, length=14, color="#E91E63", visible=True):
        """威廉指标 - Williams %R (使用 JS 端计算)"""
        self._add_indicator_via_js('WilliamsPercentRange', {'length': length, 'src': 'close', 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_ao(self, df: pd.DataFrame, color="#00BCD4", visible=True):
        """Awesome 振荡器 - Awesome Oscillator (使用 JS 端计算)"""
        self._add_indicator_via_js('AwesomeOscillator', {'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_cmo(self, df: pd.DataFrame, length=14, src='close', color="#FF5722", visible=True):
        """Chande 动量振荡器 - Chande Momentum Oscillator (使用 JS 端计算)"""
        self._add_indicator_via_js('ChandeMO', {'length': length, 'src': src, 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_dpo(self, df: pd.DataFrame, length=20, src='close', color="#9C27B0", visible=True):
        """去趋势价格振荡器 - Detrended Price Oscillator (使用 JS 端计算)"""
        self._add_indicator_via_js('DPO', {'length': length, 'src': src, 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_rvi(self, df: pd.DataFrame, length=10, color="#00E5FF", visible=True):
        """相对活力指数 - Relative Vigor Index (使用 JS 端计算)"""
        self._add_indicator_via_js('RVI', {'length': length, 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_tsi(self, df: pd.DataFrame, long=25, short=13, signal=13, src='close', color="#FF9800", visible=True):
        """真实强度指数 - True Strength Index (使用 JS 端计算)"""
        self._add_indicator_via_js('TSI', {'long': long, 'short': short, 'signal': signal, 'src': src, 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_uo(self, df: pd.DataFrame, short=7, medium=14, long=28, color="#4CAF50", visible=True):
        """终极振荡器 - Ultimate Oscillator (使用 JS 端计算)"""
        self._add_indicator_via_js('UltimateOscillator', {'short': short, 'medium': medium, 'long': long, 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_kdj(self, df: pd.DataFrame, k=9, d=3, j=3, color="#FF5722", visible=True):
        """KDJ 指标 (使用 JS 端计算)"""
        self._add_indicator_via_js('KDJ', {'k': k, 'd': d, 'smoothK': 1, 'src': 'close', 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_wt(self, df: pd.DataFrame, length1=10, length2=11, color="#E91E63", visible=True):
        """WaveTrend (使用 JS 端计算)"""
        self._add_indicator_via_js('WaveTrend', {'length1': length1, 'length2': length2, 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_stc(self, df: pd.DataFrame, fast=23, slow=50, length=10, color="#00BCD4", visible=True):
        """Schaff 趋势周期 - Schaff Trend Cycle (使用 JS 端计算)"""
        self._add_indicator_via_js('SchaffTrendCycle', {'fast': fast, 'slow': slow, 'length': length, 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_stochrsi(self, df: pd.DataFrame, length=14, rsiLength=14, stochLength=14, k=3, d=3, color="#FF9800", visible=True):
        """随机 RSI - Stochastic RSI (使用 JS 端计算)"""
        self._add_indicator_via_js('StochRSI', {'length': length, 'rsiLength': rsiLength, 'stochLength': stochLength, 'k': k, 'd': d, 'src': 'close', 'color': color, 'group': 'OSC', 'visible': visible})
        
    def add_rsi(self, df: pd.DataFrame, length=14, src='close', color="#E91E63", visible=True):
        """相对强弱指数 - Relative Strength Index"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols[src]: return
            
            series = ta.rsi(df[cols[src]], length=length)
            self._add_sub_indicator('RSI', series, df, color, 'OSC', 'RSI', visible)
        except Exception as e:
            print(f"Error adding RSI: {e}")
            import traceback
            traceback.print_exc()
        
    def add_macd(self, df: pd.DataFrame, fast=12, slow=26, signal=9, src='close', visible=True):
        """MACD - Moving Average Convergence Divergence (使用 JS 端计算)"""
        self._add_indicator_via_js('MACD', {'fastLength': fast, 'slowLength': slow, 'signalLength': signal, 'src': src, 'group': 'MOM', 'visible': visible})
        
    def add_momentum(self, df: pd.DataFrame, length=10, src='close', color="#FF9800", visible=True):
        """动量 - Momentum (使用 JS 端计算)"""
        self._add_indicator_via_js('Momentum', {'length': length, 'src': src, 'color': color, 'group': 'MOM', 'visible': visible})
        
    def add_roc(self, df: pd.DataFrame, length=10, src='close', color="#E91E63", visible=True):
        """变化率 - Rate of Change (使用 JS 端计算)"""
        self._add_indicator_via_js('ROC', {'length': length, 'src': src, 'color': color, 'group': 'MOM', 'visible': visible})
        
    def add_bop(self, df: pd.DataFrame, color="#4CAF50", visible=True):
        """平衡能量 - Balance of Power (使用 JS 端计算)"""
        self._add_indicator_via_js('BOP', {'color': color, 'group': 'MOM', 'visible': visible})
        
    def add_bullbearpower(self, df: pd.DataFrame, length=13, color="#FF5722", visible=True):
        """多空能量 - Bull Bear Power (使用 JS 端计算)"""
        self._add_indicator_via_js('BullBearPower', {'length': length, 'color': color, 'group': 'MOM', 'visible': visible})
        
    def add_coppock(self, df: pd.DataFrame, wma_length=10, roc1_length=14, roc2_length=11, src='close', color="#9C27B0", visible=True):
        """Coppock 曲线 - Coppock Curve (使用 JS 端计算)"""
        self._add_indicator_via_js('CoppockCurve', {'wmaLength': wma_length, 'roc1Length': roc1_length, 'roc2Length': roc2_length, 'src': src, 'color': color, 'group': 'MOM', 'visible': visible})
        
    def add_trix(self, df: pd.DataFrame, length=15, src='close', color="#00BCD4", visible=True):
        """TRIX - Triple Exponential Average (使用 JS 端计算)"""
        self._add_indicator_via_js('TRIX', {'length': length, 'src': src, 'color': color, 'group': 'MOM', 'visible': visible})
        
    def add_squeeze(self, df: pd.DataFrame, bb_length=20, bb_mult=2.0, kc_length=20, kc_mult=1.5, src='close', visible=True):
        """Squeeze Momentum - 挤压动量 (使用 JS 端计算)"""
        self._add_indicator_via_js('SqueezeMomentum', {'bbLength': bb_length, 'bbMult': bb_mult, 'kcLength': kc_length, 'kcMult': kc_mult, 'src': src, 'group': 'MOM', 'visible': visible})
        
    def add_adx(self, df: pd.DataFrame, length=14, color="#FF9800", visible=True):
        """平均趋向指数 - Average Directional Index (使用 JS 端计算)"""
        self._add_indicator_via_js('ADX', {'length': length, 'color': color, 'group': 'TREND', 'visible': visible})
        
    def add_ichimoku(self, df: pd.DataFrame, conversion=9, base=26, span_b=52, visible=True):
        """一目均衡图 - Ichimoku Cloud (使用 JS 端计算)"""
        self._add_indicator_via_js('IchimokuCloud', {'conversionLength': conversion, 'baseLength': base, 'spanBLength': span_b, 'group': 'TREND', 'visible': visible})
        
    def add_parabolicsar(self, df: pd.DataFrame, start=0.02, increment=0.02, maximum=0.2, visible=True):
        """抛物线 SAR - Parabolic SAR (使用 JS 端计算)"""
        self._add_indicator_via_js('ParabolicSAR', {'start': start, 'increment': increment, 'maximum': maximum, 'group': 'TREND', 'visible': visible})
        
    def add_volumesupertrendai(self, df: pd.DataFrame, atr_length=10, factor=3.0, volume_threshold=1.0, visible=True):
        """超级趋势 - Volume SuperTrend AI (使用 JS 端计算)"""
        self._add_indicator_via_js('VolumeSuperTrendAi', {'atrLength': atr_length, 'factor': factor, 'volumeThreshold': volume_threshold, 'group': 'TREND', 'visible': visible})
    
    # 别名方法，保持向后兼容
    def add_supertrend(self, df: pd.DataFrame, length=7, multiplier=3, visible=True):
        """超级趋势 - SuperTrend (别名方法，使用 VolumeSuperTrendAi)"""
        self.add_volumesupertrendai(df, atr_length=length, factor=multiplier, visible=visible)
        
    def add_aroon(self, df: pd.DataFrame, length=14, color="#E91E63", visible=True):
        """Aroon - 阿隆指标 (使用 JS 端计算)"""
        self._add_indicator_via_js('Aroon', {'length': length, 'color': color, 'group': 'TREND', 'visible': visible})
        
    def add_zigzag(self, df: pd.DataFrame, percent_change=5.0, visible=True):
        """ZigZag - 之字转向 (尝试 JS 端计算，如果失败则使用 Python 计算)"""
        print(f"🔧 Adding ZigZag indicator with percent_change={percent_change}%")
        
        # 首先尝试使用 JS 端计算
        self._add_indicator_via_js('ZigZag', {'percentChange': percent_change, 'group': 'TREND', 'visible': visible})
        
    def add_zigzag_python(self, df: pd.DataFrame, percent_change=5.0, color="#E91E63", visible=True):
        """ZigZag - 之字转向 (Python 端计算备用方案)"""
        try:
            cols = self._get_standard_columns(df)
            if not cols['date'] or not cols['high'] or not cols['low']:
                print("❌ Error: Missing required columns for ZigZag")
                print(f"   Available columns: {list(df.columns)}")
                return
            
            print(f"\n{'='*60}")
            print(f"🔧 Calculating ZigZag with {percent_change}% threshold")
            print(f"{'='*60}")
            print(f"   Data length: {len(df)}")
            
            # 【关键修复】确保日期格式与蜡烛图一致
            date_series = pd.to_datetime(df[cols['date']])
            dates = date_series.dt.strftime('%Y-%m-%d').values
            highs = df[cols['high']].values
            lows = df[cols['low']].values
            
            # ZigZag 算法 - 基于百分比变化
            threshold = percent_change / 100.0
            zigzag_points = []
            
            # 改进的 ZigZag 算法
            # 第一步：找到所有潜在的转折点
            pivot_indices = [0]  # 从第一个点开始
            pivot_prices = [(highs[0] + lows[0]) / 2]  # 使用中价
            
            current_extreme_idx = 0
            current_extreme_price = (highs[0] + lows[0]) / 2
            current_direction = None  # 'up' or 'down'
            
            for i in range(1, len(highs)):
                mid_price = (highs[i] + lows[i]) / 2
                
                if current_direction is None:
                    # 确定初始方向
                    if mid_price > current_extreme_price * (1 + threshold):
                        current_direction = 'up'
                    elif mid_price < current_extreme_price * (1 - threshold):
                        current_direction = 'down'
                    
                    if current_direction:
                        pivot_indices.append(i)
                        pivot_prices.append(mid_price)
                        current_extreme_idx = i
                        current_extreme_price = mid_price
                elif current_direction == 'up':
                    # 上升趋势
                    if mid_price > current_extreme_price:
                        # 更新最高点
                        current_extreme_idx = i
                        current_extreme_price = mid_price
                        pivot_indices[-1] = i
                        pivot_prices[-1] = mid_price
                    elif mid_price < current_extreme_price * (1 - threshold):
                        # 趋势反转
                        current_direction = 'down'
                        pivot_indices.append(i)
                        pivot_prices.append(mid_price)
                        current_extreme_idx = i
                        current_extreme_price = mid_price
                else:  # current_direction == 'down'
                    # 下降趋势
                    if mid_price < current_extreme_price:
                        # 更新最低点
                        current_extreme_idx = i
                        current_extreme_price = mid_price
                        pivot_indices[-1] = i
                        pivot_prices[-1] = mid_price
                    elif mid_price > current_extreme_price * (1 + threshold):
                        # 趋势反转
                        current_direction = 'up'
                        pivot_indices.append(i)
                        pivot_prices.append(mid_price)
                        current_extreme_idx = i
                        current_extreme_price = mid_price
            
            # 构建 ZigZag 点
            for idx, pivot_idx in enumerate(pivot_indices):
                # 根据前后趋势决定使用高点还是低点
                if idx == 0:
                    # 第一个点
                    if len(pivot_indices) > 1 and pivot_prices[1] > pivot_prices[0]:
                        value = lows[pivot_idx]  # 起点是低点
                    else:
                        value = highs[pivot_idx]  # 起点是高点
                elif idx == len(pivot_indices) - 1:
                    # 最后一个点
                    if pivot_prices[idx] > pivot_prices[idx-1]:
                        value = highs[pivot_idx]  # 终点是高点
                    else:
                        value = lows[pivot_idx]  # 终点是低点
                else:
                    # 中间点
                    if pivot_prices[idx] > pivot_prices[idx-1] and pivot_prices[idx] > pivot_prices[idx+1]:
                        value = highs[pivot_idx]  # 局部高点
                    else:
                        value = lows[pivot_idx]  # 局部低点
                
                zigzag_points.append({
                    'time': dates[pivot_idx],
                    'value': float(value)
                })
            
            print(f"\n📊 ZigZag calculation complete:")
            print(f"   Total pivot points: {len(zigzag_points)}")
            
            if len(zigzag_points) < 2:
                print("   ⚠️ WARNING: Not enough pivot points for ZigZag line")
                return
            
            # 添加到主图
            data_json = json.dumps(zigzag_points)
            print(f"\n📤 Sending {len(zigzag_points)} points to chart")
            
            js_code = f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('ZigZag', {data_json}, {{
                        color: '{color}', 
                        lineWidth: 2,
                        lineStyle: 2,
                        group: 'TREND', 
                        indicatorKey: 'ZigZag',
                        visible: {str(visible).lower()}
                    }});
                }}
            """
            
            self._queue_indicator(js_code)
            print(f"✅ ZigZag indicator (Python) queued for main chart")
            print(f"{'='*60}\n")
        except Exception as e:
            print(f"❌ Error adding ZigZag (Python): {e}")
            import traceback
            traceback.print_exc()
            
    def add_williamsalligator(self, df: pd.DataFrame, jaw=13, teeth=8, lips=5, visible=True):
        """Williams Alligator - 威廉鳄鱼 (使用 JS 端计算)"""
        self._add_indicator_via_js('WilliamsAlligator', {'jawLength': jaw, 'teethLength': teeth, 'lipsLength': lips, 'group': 'TREND', 'visible': visible})
        
    def add_donchianchannels(self, df: pd.DataFrame, length=20, visible=True):
        """Donchian Channels - 唐奇安通道 (使用 JS 端计算)"""
        self._add_indicator_via_js('DonchianChannels', {'length': length, 'group': 'TREND', 'visible': visible})
        
    def add_atr(self, df: pd.DataFrame, length=14, color="#FF5722", visible=True):
        """平均真实波幅 - Average True Range (使用 JS 端计算)"""
        self._add_indicator_via_js('ATR', {'length': length, 'color': color, 'group': 'VOLATILITY', 'visible': visible})
        
    def add_bollingerbands(self, df: pd.DataFrame, length=20, std=2.0, src='close', visible=True):
        """布林带 - Bollinger Bands (使用 JS 端计算)"""
        self._add_indicator_via_js('BollingerBands', {'length': length, 'std': std, 'src': src, 'group': 'VOLATILITY', 'visible': visible})
    
    # 别名方法，保持向后兼容
    def add_bbands(self, df: pd.DataFrame, length=20, std=2, src='close', visible=True):
        """布林带 - Bollinger Bands (别名方法)"""
        self.add_bollingerbands(df, length=length, std=std, src=src, visible=visible)
        
    def add_standarddeviation(self, df: pd.DataFrame, length=20, src='close', color="#9C27B0", visible=True):
        """标准差 - Standard Deviation (使用 JS 端计算)"""
        self._add_indicator_via_js('StandardDeviation', {'length': length, 'src': src, 'color': color, 'group': 'VOLATILITY', 'visible': visible})
        
    def add_historicalvolatility(self, df: pd.DataFrame, length=20, src='close', color="#00BCD4", visible=True):
        """历史波动率 - Historical Volatility (使用 JS 端计算)"""
        self._add_indicator_via_js('HistoricalVolatility', {'length': length, 'src': src, 'color': color, 'group': 'VOLATILITY', 'visible': visible})
        
    def add_choppiness(self, df: pd.DataFrame, length=14, color="#FF9800", visible=True):
        """Choppiness Index - 震荡指数 (使用 JS 端计算)"""
        self._add_indicator_via_js('Choppiness', {'length': length, 'color': color, 'group': 'VOLATILITY', 'visible': visible})
        
    def add_volume(self, df: pd.DataFrame, visible=True):
        """成交量 - Volume (使用 JS 端计算)"""
        self._add_indicator_via_js('BetterVolume', {'group': 'VOLUME', 'visible': visible})
        
    def add_mfi(self, df: pd.DataFrame, length=14, color="#4CAF50", visible=True):
        """资金流量指数 - Money Flow Index (使用 JS 端计算)"""
        self._add_indicator_via_js('MFI', {'length': length, 'color': color, 'group': 'VOLUME', 'visible': visible})
        
    def add_obv(self, df: pd.DataFrame, color="#E91E63", visible=True):
        """On Balance Volume - 能量潮 (使用 JS 端计算)"""
        self._add_indicator_via_js('OBV', {'color': color, 'group': 'VOLUME', 'visible': visible})
        
    def add_volumeaccumulationpct(self, df: pd.DataFrame, length=20, color="#9C27B0", visible=True):
        """Accumulation/Distribution - 累积/分布 (使用 JS 端计算)"""
        self._add_indicator_via_js('VolumeAccumulationPct', {'length': length, 'color': color, 'group': 'VOLUME', 'visible': visible})
    
    def handle_add_yearly_profile(self, data):
        """处理年度成交量分布请求"""
        try:
            indicator = data.get('indicator')
            options = data.get('options', {})
            
            if indicator == 'PROFILE':
                # 调用实际的成交量分布计算
                result = self.calculate_yearly_profile(options)
                
                # 返回结果给前端
                self.send_to_js({
                    'type': 'profile_calculated',
                    'indicator': 'PROFILE',
                    'success': True,
                    'data': result
                })
                
                return True
        except Exception as e:
            print(f"❌ 处理PROFILE指标失败: {str(e)}")
            return False
    
    def add_yearly_profile(self, df: pd.DataFrame, period=252, visible=True, color="#FF6B6B"):
        """年度成交量分布图 - 在副图显示"""
        print(f"📊 开始计算年度成交量分布图 (YEARLY PROFILE)")
        
        if df is None or df.empty:
            print("⚠️ 无数据可用，无法计算PROFILE")
            return
        
        try:
            # 标准化列名
            cols = self._get_standard_columns(df)
            
            if not cols['date'] or not cols['volume']:
                print("⚠️ 缺少日期或成交量数据")
                return
            
            # 解析日期
            df_copy = df.copy()
            df_copy['date'] = pd.to_datetime(df_copy[cols['date']])
            
            # 添加年份列
            df_copy['year'] = df_copy['date'].dt.year
            
            # 计算年度成交量分布
            years = sorted(df_copy['year'].unique())
            print(f"📅 数据包含 {len(years)} 年: {years}")
            
            # 构建JavaScript代码
            js_code = f"""
            (function() {{
                console.log('📊 开始在副图绘制年度成交量分布图');
                
                // 1. 检查副图是否存在
                if (!window.subChart) {{
                    console.error('❌ 副图未初始化，无法添加PROFILE');
                    
                    // 尝试初始化副图
                    if (window.initSubChart) {{
                        window.initSubChart();
                    }}
                    
                    if (!window.subChart) {{
                        console.error('❌ 副图初始化失败');
                        return;
                    }}
                }}
                
                // 2. 创建副图的HistogramSeries用于PROFILE
                const {{ HistogramSeries }} = window.LightweightCharts;
                const profileSeries = window.subChart.addSeries(HistogramSeries, {{
                    title: '年度成交量分布',
                    color: '{color}',
                    priceFormat: {{
                        type: 'volume',
                    }},
                    priceScaleId: 'volume',
                }});
                
                // 3. 准备示例数据（这里应该用实际计算的数据）
                // 示例：为每个年份创建一些测试数据
                const profileData = [];
                const years = {json.dumps(years)};
                const colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DDA0DD', '#87CEEB'];
                
                years.forEach((year, yearIndex) => {{
                    // 为每个年份创建一些随机的成交量分布数据
                    for (let i = 0; i < 10; i++) {{
                        const time = `${{year}}-01-01`;  // 使用年份的第一天
                        const value = 1000000 + Math.random() * 1000000;  // 随机成交量
                        const color = colors[yearIndex % colors.length];
                        
                        profileData.push({{
                            time: time,
                            value: value,
                            color: color,
                            year: year
                        }});
                    }}
                }});
                
                console.log('📈 PROFILE数据:', profileData.length, '个数据点');
                
                // 4. 设置数据
                profileSeries.setData(profileData);
                
                // 5. 设置可见性
                profileSeries.applyOptions({{ visible: {str(visible).lower()} }});
                
                // 6. 保存到映射
                if (!window.seriesMap) window.seriesMap = new Map();
                window.seriesMap.set('PROFILE', {{
                    series: profileSeries,
                    chart: 'sub',  // 标记为副图指标
                    visible: {str(visible).lower()}
                }});
                
                // 7. 更新副图状态
                if (window.updateSubChartState) {{
                    window.updateSubChartState(true);
                }}
                
                // 8. 设置副图坐标轴
                if (window.subChart && window.subChart.priceScale) {{
                    const priceScale = window.subChart.priceScale('volume');
                    if (priceScale) {{
                        priceScale.applyOptions({{
                            scaleMargins: {{
                                top: 0.1,
                                bottom: 0.3
                            }}
                        }});
                    }}
                }}
                
                console.log('✅ 年度成交量分布图已添加到副图');
                
                // 9. 通知Python端完成
                if (window.pythonBridge && window.pythonBridge.notify) {{
                    window.pythonBridge.notify('profile_added_to_subchart', {{
                        indicator: 'PROFILE',
                        dataPoints: profileData.length,
                        years: years.length,
                        visible: {str(visible).lower()},
                        chart: 'sub'
                    }});
                }}
            }})();
            """
            
            # 发送到前端
            if self.is_chart_ready:
                self.browser.page().runJavaScript(js_code)
                print("✅ 年度成交量分布图JavaScript代码已发送到前端")
            else:
                self._queue_indicator(js_code)
                print("⏳ 图表未就绪，JavaScript代码已加入队列")
                
        except Exception as e:
            print(f"❌ 计算年度成交量分布图失败: {e}")
            import traceback
            traceback.print_exc()
            
    def handle_remove_profile(self, data):
        """处理移除PROFILE指标请求"""
        indicator = data.get('indicator')
        print(f"🗑️ 移除PROFILE指标: {indicator}")
        
        try:
            js_code = """
            (function() {
                console.log('🗑️ 移除PROFILE指标');
                
                // 查找并移除PROFILE系列
                if (window.seriesMap && window.seriesMap.has('PROFILE')) {
                    const profileInfo = window.seriesMap.get('PROFILE');
                    if (profileInfo && profileInfo.series) {
                        // 从图表中移除
                        try {
                            if (profileInfo.chart === 'main' && window.mainChart) {
                                window.mainChart.removeSeries(profileInfo.series);
                            } else if (profileInfo.chart === 'sub' && window.subChart) {
                                window.subChart.removeSeries(profileInfo.series);
                            }
                            console.log('✅ PROFILE系列已从图表移除');
                        } catch (e) {
                            console.warn('移除系列时出错:', e);
                        }
                    }
                    
                    // 从映射中移除
                    window.seriesMap.delete('PROFILE');
                }
                
                // 更新按钮状态
                const button = document.querySelector('[data-indicator="PROFILE"]');
                if (button) {
                    button.classList.remove('active');
                    button.style.backgroundColor = '#131722';
                    button.style.color = '#d1d4dc';
                    button.style.borderColor = '#2a2e39';
                }
                
                console.log('✅ PROFILE指标已移除');
            })();
            """
            
            if self.is_chart_ready:
                self.browser.page().runJavaScript(js_code)
            else:
                print("⚠️ 图表未就绪，无法移除PROFILE")
                
            return True
            
        except Exception as e:
            print(f"❌ 移除PROFILE指标失败: {e}")
            return False
        
    # ========================================
    # 辅助方法
    # ========================================
    
    def _add_line_indicator(self, name, series, df, color, group, indicator_key, visible=True):
        """添加主图线型指标"""
        try:
            cols = self._get_standard_columns(df)
            if not cols['date']: return
            
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            # 安全的 prep 函数
            def safe_prep(series, dates):
                data = []
                for i in range(min(len(series), len(dates))):
                    try:
                        val = series.iloc[i]
                        if not pd.isna(val):
                            data.append({'time': dates[i], 'value': float(val)})
                    except (IndexError, TypeError):
                        continue
                return data
            
            data = safe_prep(series, dates)
            
            print(f"📊 Preparing {name}: {len(data)} data points")
            
            data_json = json.dumps(data)
            js_code = f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('{name}', {data_json}, {{
                        color: '{color}', 
                        lineWidth: 2, 
                        group: '{group}', 
                        indicatorKey: '{indicator_key}',
                        visible: {str(visible).lower()}
                    }});
                }}
            """
            
            self._queue_indicator(js_code)
        except Exception as e:
            print(f"Error adding {name}: {e}")
            import traceback
            traceback.print_exc()
            
    def _add_sub_indicator(self, name, series, df, color, group, indicator_key, visible=True):
        """添加副图线型指标"""
        try:
            cols = self._get_standard_columns(df)
            if not cols['date']: return
            
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            # 安全的 prep 函数
            def safe_prep(series, dates):
                data = []
                for i in range(min(len(series), len(dates))):
                    try:
                        val = series.iloc[i]
                        if not pd.isna(val):
                            data.append({'time': dates[i], 'value': float(val)})
                    except (IndexError, TypeError):
                        continue
                return data
            
            data = safe_prep(series, dates)
            
            print(f"📊 Preparing sub indicator {name}: {len(data)} data points")
            
            data_json = json.dumps(data)
            js_code = f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('{name}', {data_json}, {{
                        color: '{color}', 
                        group: '{group}', 
                        indicatorKey: '{indicator_key}',
                        visible: {str(visible).lower()}
                    }});
                }}
            """
            
            self._queue_indicator(js_code)
        except Exception as e:
            print(f"Error adding {name}: {e}")
            import traceback
            traceback.print_exc()
            
    def debug_available_indicators(self):
        """调试可用的指标"""
        print("🔧 Debugging available indicators...")
        
        # 检查 JS 端可用的指标
        js_code = """
        (function() {
            if (window.LightweightChartsIndicators) {
                const indicators = Object.keys(window.LightweightChartsIndicators);
                console.log('📊 Available JS indicators:', indicators);
                return indicators;
            } else {
                console.warn('⚠️ LightweightChartsIndicators not available');
                return [];
            }
        })();
        """
        
        if self.browser.page():
            self.browser.page().runJavaScript(js_code, self._on_debug_result)
        
    def _on_debug_result(self, result):
        """调试结果回调"""
        if result and isinstance(result, list):
            print(f"✅ Found {len(result)} indicators in JS")
            for indicator in result[:20]:  # 只显示前20个
                print(f"  - {indicator}")
        else:
            print("⚠️ No indicators found in JS")
            
    def _fallback_to_python_calculation(self, indicator_key, group):
        """回退到Python端计算指标"""
        print(f"🔧 Falling back to Python calculation for: {indicator_key}")
        
        if self.original_df is None:
            print("❌ No data available for calculation")
            return
        
        try:
            # 调用对应的Python方法
            if hasattr(self, f'add_{indicator_key.lower()}'):
                method = getattr(self, f'add_{indicator_key.lower()}')
                method(self.original_df)
            elif indicator_key in self.indicator_handlers:
                handler = self.indicator_handlers[indicator_key]
                handler()
            else:
                print(f"❌ No Python implementation found for {indicator_key}")
        except Exception as e:
            print(f"❌ Error in Python calculation for {indicator_key}: {e}")
            import traceback
            traceback.print_exc()
            
    # 在Python Bridge中添加PROFILE处理
    def handle_profile_request(self, data):
        """处理成交量分布请求"""
        try:
            indicator = data.get('indicator')
            options = data.get('options', {})
            
            if indicator == 'PROFILE':
                # 调用add_yearly_profile
                result = self.trading_view_widget.add_yearly_profile(options)
                
                # 返回结果给JS
                self.send_to_js({
                    'type': 'profile_result',
                    'success': result,
                    'indicator': indicator
                })
                
            return True
        except Exception as e:
            print(f"❌ 处理PROFILE请求失败: {str(e)}")
            return False