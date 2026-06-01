import os
import json
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QTimer, pyqtSlot
import pandas as pd
import yfinance as yf

class TradingViewWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        self.browser = QWebEngineView(self)
        self.layout.addWidget(self.browser)
        
        html_path = os.path.join(os.path.dirname(__file__), 'chart_template.html')
        self.browser.setUrl(QUrl.fromLocalFile(html_path))
        
        self.browser.loadFinished.connect(self._inject_js_library)
        
        # 【新增】延迟队列：存储等待发送的数据
        self.pending_chart_data = None
        self.pending_indicators = []
        self.is_chart_ready = False
        
        # 【新增】启动轮询检查 JS 是否就绪
        self.ready_check_timer = QTimer(self)
        self.ready_check_timer.timeout.connect(self._check_chart_ready)
        self.ready_check_timer.start(300)  # 每 300ms 检查一次

    def _check_chart_ready(self):
        """检查 JS 端图表是否已初始化完成"""
        self.browser.page().runJavaScript("""
            (function() {
                return window.isChartInitialized === true;
            })();
        """, self._on_ready_check_result)

    def _on_ready_check_result(self, result):
        """处理就绪检查结果"""
        if result is True and not self.is_chart_ready:
            self.is_chart_ready = True
            self.ready_check_timer.stop()
            print("✅ Chart is ready! Flushing pending data...")
            self._flush_pending_data()

    def _flush_pending_data(self):
        """发送所有暂存的数据"""
        if self.pending_chart_data:
            data_json = json.dumps(self.pending_chart_data)
            self.browser.page().runJavaScript(f"""
                if (typeof window.setChartData === 'function') {{
                    window.setChartData({data_json});
                }}
            """)
            self.pending_chart_data = None
            
        for indicator_js in self.pending_indicators:
            self.browser.page().runJavaScript(indicator_js)
        self.pending_indicators.clear()
        
        # 【新增】在所有数据处理完毕后，触发一次全局缩放刷新
        self.browser.page().runJavaScript("if (typeof window.refreshZoom === 'function') window.refreshZoom();")

    def _inject_js_library(self, ok):
        if not ok:
            print("Failed to load HTML page.")
            return

        js_file_path = os.path.join(os.path.dirname(__file__), 'lightweight-charts5.2.0/dist/lightweight-charts.standalone.production.js')
         
        if os.path.exists(js_file_path):
            with open(js_file_path, 'r', encoding='utf-8') as f:
                js_content = f.read()
                self.browser.page().runJavaScript(js_content)
                print("Local TradingView JS library injected.")
        else:
            print(f"Warning: Local JS not found at {js_file_path}")

    def update_chart_data(self, df: pd.DataFrame):
        """更新图表数据"""
        if df.empty:
            return
            
        chart_data = self._prepare_chart_data(df)
        if not chart_data:
            print("Error: No valid chart data prepared for candles.")
            return

        if len(chart_data) > 0:
            print(f"Debug Candle Data: {chart_data[0]}")

        # 【关键修复】如果图表未就绪，存入队列；否则直接发送
        if not self.is_chart_ready:
            print("⏳ Chart not ready, queuing candle data...")
            self.pending_chart_data = chart_data
        else:
            data_json = json.dumps(chart_data)
            self.browser.page().runJavaScript(f"""
                console.log("Received {len(chart_data)} candle points.");
                if (typeof window.setChartData === 'function') {{
                    window.setChartData({data_json});
                }}
            """)

    def _queue_indicator(self, js_code):
        """将指标调用加入队列"""
        if not self.is_chart_ready:
            self.pending_indicators.append(js_code)
        else:
            self.browser.page().runJavaScript(js_code)

    def add_ma_indicator(self, df: pd.DataFrame, period=20, color="#FFEB3B"):
        """添加均线指标"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            ma_series = ta.sma(df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(ma_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(ma_series.iloc[i])]
            
            data_json = json.dumps(data)
            js_code = f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('SMA{period}', '{data_json}', {{
                        color: '{color}', 
                        group: 'MA',
                        indicatorKey: 'SMA',
                        visible: true
                    }});
                }}
            """
            self._queue_indicator(js_code)
        except Exception as e:
            print(f"Error adding MA: {e}")

    def add_ema_indicator(self, df: pd.DataFrame, period=20, color="#E040FB"):
        """添加 EMA 指数移动平均线 (主图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            ema_series = ta.ema(df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(ema_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(ema_series.iloc[i])]
            
            data_json = json.dumps(data)
            js_code = f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('EMA{period}', '{data_json}', {{
                        color: '{color}', 
                        lineWidth: 2, 
                        group: 'EMA', 
                        indicatorKey: 'EMA',
                        visible: false
                    }});
                }}
            """
            self._queue_indicator(js_code)
        except Exception as e:
            print(f"Error adding EMA: {e}")

    def add_bbands_indicator(self, df: pd.DataFrame):
        """添加布林带"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            bb = ta.bbands(df[cols['close']], length=20, std=2)
            lower_col, middle_col, upper_col = bb.columns[0], bb.columns[1], bb.columns[2]

            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            def prep(series):
                return [{'time': dates[i], 'value': float(series.iloc[i])} 
                        for i in range(len(df)) if not pd.isna(series.iloc[i])]

            self._queue_indicator(f"window.addMainIndicator('BB_U', '{json.dumps(prep(bb[upper_col]))}', {{color: '#2962FF', lineWidth: 1, group: 'BOLL', indicatorKey: 'BOLL', visible: false}});")
            self._queue_indicator(f"window.addMainIndicator('BB_M', '{json.dumps(prep(bb[middle_col]))}', {{color: '#FF9800', lineWidth: 1, lineStyle: 2, group: 'BOLL', indicatorKey: 'BOLL', visible: false}});")
            self._queue_indicator(f"window.addMainIndicator('BB_L', '{json.dumps(prep(bb[lower_col]))}', {{color: '#2962FF', lineWidth: 1, group: 'BOLL', indicatorKey: 'BOLL', visible: false}});")
        except Exception as e:
            print(f"Error adding BBands: {e}")

    def add_sar_indicator(self, df: pd.DataFrame, acceleration=0.02, maximum=0.2, color="#00BCD4"):
        """添加 SAR 抛物线转向指标 (主图 - 点状虚线)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            sar_df = ta.psar(df[cols['high']], df[cols['low']], df[cols['close']], 
                            acceleration=acceleration, maximum=maximum)
            
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = []
            for i in range(len(df)):
                sar_value = None
                for col in sar_df.columns:
                    val = sar_df[col].iloc[i]
                    if not pd.isna(val):
                        sar_value = float(val)
                        break
                
                if sar_value is not None:
                    data.append({'time': dates[i], 'value': sar_value})
            
            data_json = json.dumps(data)
            js_code = f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('SAR', '{data_json}', {{
                        color: '{color}', 
                        lineWidth: 1, 
                        lineStyle: 2,
                        group: 'TREND', 
                        indicatorKey: 'SAR',
                        visible: false
                    }});
                }}
            """
            self._queue_indicator(js_code)
        except Exception as e:
            print(f"Error adding SAR: {e}")

    def add_supertrend_indicator(self, df: pd.DataFrame, period=10, multiplier=3, color="#4CAF50"):
        """添加 SuperTrend 超级趋势指标 (主图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            st_df = ta.supertrend(df[cols['high']], df[cols['low']], df[cols['close']], 
                                 length=period, multiplier=multiplier)
            
            trend_line = st_df.iloc[:, 0]
            direction = st_df.iloc[:, 1]
            
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data_up = []
            data_down = []
            
            for i in range(len(df)):
                if not pd.isna(trend_line.iloc[i]):
                    point = {'time': dates[i], 'value': float(trend_line.iloc[i])}
                    if direction.iloc[i] == 1:
                        data_up.append(point)
                    else:
                        data_down.append(point)
            
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('ST_Up', '{json.dumps(data_up)}', {{
                        color: '#0ecb81', 
                        lineWidth: 2, 
                        group: 'TREND', 
                        indicatorKey: 'SUPER',
                        visible: false
                    }});
                }}
            """)
            
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('ST_Down', '{json.dumps(data_down)}', {{
                        color: '#f6465d', 
                        lineWidth: 2, 
                        group: 'TREND', 
                        indicatorKey: 'SUPER',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding SuperTrend: {e}")

    def add_atr_indicator(self, df: pd.DataFrame, period=14, color="#FF5722"):
        """添加 ATR 平均真实波幅 (主图叠加显示相对值)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            atr_series = ta.atr(df[cols['high']], df[cols['low']], df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            # 将 ATR 叠加到价格上：以收盘价为基准，上下偏移 ATR 值
            data_upper = [{'time': dates[i], 'value': float(df[cols['close']].iloc[i]) + float(atr_series.iloc[i])} 
                         for i in range(len(df)) if not pd.isna(atr_series.iloc[i])]
            
            data_lower = [{'time': dates[i], 'value': float(df[cols['close']].iloc[i]) - float(atr_series.iloc[i])} 
                         for i in range(len(df)) if not pd.isna(atr_series.iloc[i])]
            
            # 上轨
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('ATR_Upper', '{json.dumps(data_upper)}', {{
                        color: '{color}', 
                        lineWidth: 1, 
                        lineStyle: 3, 
                        group: 'VOLATILITY', 
                        indicatorKey: 'ATR',
                        visible: false
                    }});
                }}
            """)
            
            # 下轨
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('ATR_Lower', '{json.dumps(data_lower)}', {{
                        color: '{color}', 
                        lineWidth: 1, 
                        lineStyle: 3, 
                        group: 'VOLATILITY', 
                        indicatorKey: 'ATR',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding ATR: {e}")
            import traceback
            traceback.print_exc()

    def add_vol_indicator(self, df: pd.DataFrame):
        """添加成交量 (副图)"""
        cols = self._get_standard_columns(df)
        if not cols['volume'] or not cols['close'] or not cols['open']: 
            print("Error: Missing columns for VOL indicator")
            return

        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        data = []
        
        for i in range(len(df)):
            c = float(df[cols['close']].iloc[i])
            o = float(df[cols['open']].iloc[i])
            v = float(df[cols['volume']].iloc[i])
            color = '#0ecb81' if c >= o else '#f6465d'
            data.append({'time': dates[i], 'value': v, 'color': color})
        
        self._queue_indicator(
            f"window.addSubIndicator('VOL', '{json.dumps(data)}', "
            f"{{priceScaleId: 'vol_scale', scaleMargins: {{top: 0.8, bottom: 0}}, group: 'VOL', indicatorKey: 'VOL', visible: false}});"
        )

    def add_macd_indicator(self, df: pd.DataFrame):
        """添加 MACD (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            macd_df = ta.macd(df[cols['close']], fast=12, slow=26, signal=9)
            macd_line, signal_line, hist = macd_df.iloc[:, 0], macd_df.iloc[:, 1], macd_df.iloc[:, 2]

            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            def prep(series):
                return [{'time': dates[i], 'value': float(series.iloc[i])} 
                        for i in range(len(df)) if not pd.isna(series.iloc[i])]

            data_h = []
            for i in range(len(df)):
                if not pd.isna(hist.iloc[i]):
                    val = float(hist.iloc[i])
                    data_h.append({'time': dates[i], 'value': val, 'color': '#0ecb81' if val >= 0 else '#f6465d'})

            self._queue_indicator(f"window.addSubIndicator('MACD_Hist', '{json.dumps(data_h)}', {{group: 'MACD', indicatorKey: 'MACD', visible: false}});")
            self._queue_indicator(f"window.addSubIndicator('MACD_Line', '{json.dumps(prep(macd_line))}', {{color: '#FF9800', group: 'MACD', indicatorKey: 'MACD', visible: false}});")
            self._queue_indicator(f"window.addSubIndicator('Signal_Line', '{json.dumps(prep(signal_line))}', {{color: '#2962FF', group: 'MACD', indicatorKey: 'MACD', visible: false}});")
        except Exception as e:
            print(f"Error adding MACD: {e}")

    def add_rsi_indicator(self, df: pd.DataFrame, period=14):
        """添加 RSI (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            rsi_series = ta.rsi(df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(rsi_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(rsi_series.iloc[i])]
            
            self._queue_indicator(f"window.addSubIndicator('RSI', '{json.dumps(data)}', {{color: '#E91E63', priceScaleId: 'rsi_scale', scaleMargins: {{top: 0.4, bottom: 0}}, group: 'RSI', indicatorKey: 'RSI', visible: false}});")
        except Exception as e:
            print(f"Error adding RSI: {e}")

    def add_yearly_profile_indicator(self, df: pd.DataFrame, period=252):
        """添加年度价格剖面指标 (副图 - 相对位置百分比)"""
        try:
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            high_252 = df[cols['high']].rolling(window=period, min_periods=1).max()
            low_252 = df[cols['low']].rolling(window=period, min_periods=1).min()
            
            denominator = high_252 - low_252
            denominator = denominator.replace(0, float('nan'))
            position_pct = (df[cols['close']] - low_252) / denominator * 100
            
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(position_pct.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(position_pct.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('YearlyPos%', '{json.dumps(data)}', {{
                        color: '#9C27B0', 
                        lineWidth: 2, 
                        priceScaleId: 'yearly_scale', 
                        scaleMargins: {{top: 0.1, bottom: 0.1}}, 
                        group: 'PROFILE', 
                        indicatorKey: 'PROFILE',
                        visible: false
                    }});
                }}
            """)
            
            mid_line_data = [{'time': dates[i], 'value': 50.0} for i in range(len(df))]
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('YearlyMid', '{json.dumps(mid_line_data)}', {{
                        color: '#787b86', 
                        lineWidth: 1, 
                        lineStyle: 2, 
                        priceScaleId: 'yearly_scale', 
                        scaleMargins: {{top: 0.1, bottom: 0.1}}, 
                        group: 'PROFILE', 
                        indicatorKey: 'PROFILE',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding Yearly Profile: {e}")

    def add_wma_indicator(self, df: pd.DataFrame, period=20, color="#9C27B0"):
        """添加 WMA 加权移动平均 (主图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            wma_series = ta.wma(df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(wma_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(wma_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('WMA{period}', '{json.dumps(data)}', {{
                        color: '{color}', 
                        lineWidth: 1, 
                        group: 'MA', 
                        indicatorKey: 'WMA',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding WMA: {e}")

    def add_hma_indicator(self, df: pd.DataFrame, period=20, color="#00E5FF"):
        """添加 HMA Hull 移动平均 (主图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            hma_series = ta.hma(df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(hma_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(hma_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('HMA{period}', '{json.dumps(data)}', {{
                        color: '{color}', 
                        lineWidth: 2, 
                        group: 'MA', 
                        indicatorKey: 'HMA',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding HMA: {e}")

    def add_kdj_indicator(self, df: pd.DataFrame, period=9, smoothK=3, smoothD=3, colorK="#FFEB3B", colorD="#2962FF", colorJ="#E91E63"):
        """添加 KDJ 随机指标 (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            kdj_df = ta.stoch(df[cols['high']], df[cols['low']], df[cols['close']], 
                             k=period, d=smoothK, smooth_k=smoothK)
            
            k_line = kdj_df.iloc[:, 0]  # %K
            d_line = kdj_df.iloc[:, 1]  # %D
            j_line = 3 * k_line - 2 * d_line  # %J = 3K - 2D
            
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            def prep(series):
                return [{'time': dates[i], 'value': float(series.iloc[i])} 
                        for i in range(len(df)) if not pd.isna(series.iloc[i])]

            self._queue_indicator(f"window.addSubIndicator('KDJ_K', '{json.dumps(prep(k_line))}', {{color: '{colorK}', group: 'RSI', indicatorKey: 'KDJ', visible: false}});")
            self._queue_indicator(f"window.addSubIndicator('KDJ_D', '{json.dumps(prep(d_line))}', {{color: '{colorD}', group: 'RSI', indicatorKey: 'KDJ', visible: false}});")
            self._queue_indicator(f"window.addSubIndicator('KDJ_J', '{json.dumps(prep(j_line))}', {{color: '{colorJ}', group: 'RSI', indicatorKey: 'KDJ', visible: false}});")
        except Exception as e:
            print(f"Error adding KDJ: {e}")

    def add_cci_indicator(self, df: pd.DataFrame, period=20, color="#FF9800"):
        """添加 CCI 商品通道指数 (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            cci_series = ta.cci(df[cols['high']], df[cols['low']], df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(cci_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(cci_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('CCI', '{json.dumps(data)}', {{
                        color: '{color}', 
                        group: 'RSI', 
                        indicatorKey: 'CCI',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding CCI: {e}")

    def add_williams_indicator(self, df: pd.DataFrame, period=14, color="#4CAF50"):
        """添加 Williams %R 威廉指标 (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            willr_series = ta.willr(df[cols['high']], df[cols['low']], df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(willr_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(willr_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('Williams%R', '{json.dumps(data)}', {{
                        color: '{color}', 
                        group: 'RSI', 
                        indicatorKey: 'WILLIAMS',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding Williams %R: {e}")

    def add_momentum_indicator(self, df: pd.DataFrame, period=10, color="#00BCD4"):
        """添加 Momentum 动量指标 (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            mom_series = ta.mom(df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(mom_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(mom_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('Momentum', '{json.dumps(data)}', {{
                        color: '{color}', 
                        group: 'MACD', 
                        indicatorKey: 'MOMENTUM',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding Momentum: {e}")

    def add_roc_indicator(self, df: pd.DataFrame, period=10, color="#FF5722"):
        """添加 ROC 变化率指标 (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            roc_series = ta.roc(df[cols['close']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(roc_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(roc_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('ROC', '{json.dumps(data)}', {{
                        color: '{color}', 
                        group: 'MACD', 
                        indicatorKey: 'ROC',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding ROC: {e}")

    def add_vwma_indicator(self, df: pd.DataFrame, period=20, color="#9C27B0"):
        """添加 VWMA 成交量加权移动平均 (主图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['volume']: return

            vwma_series = ta.vwma(df[cols['close']], df[cols['volume']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(vwma_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(vwma_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('VWMA{period}', '{json.dumps(data)}', {{
                        color: '{color}', 
                        lineWidth: 1, 
                        group: 'VOL', 
                        indicatorKey: 'VWMA',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding VWMA: {e}")

    def add_mfi_indicator(self, df: pd.DataFrame, period=14, color="#E91E63"):
        """添加 MFI 资金流量指数 (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low'] or not cols['volume']: return

            mfi_series = ta.mfi(df[cols['high']], df[cols['low']], df[cols['close']], 
                               df[cols['volume']], length=period)
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(mfi_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(mfi_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('MFI', '{json.dumps(data)}', {{
                        color: '{color}', 
                        group: 'VOL', 
                        indicatorKey: 'MFI',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding MFI: {e}")

    def add_adx_indicator(self, df: pd.DataFrame, period=14, color="#FF9800"):
        """添加 ADX 平均趋向指数 (副图)"""
        try:
            import pandas_ta_classic as ta
            cols = self._get_standard_columns(df)
            if not cols['close'] or not cols['high'] or not cols['low']: return

            adx_df = ta.adx(df[cols['high']], df[cols['low']], df[cols['close']], length=period)
            adx_line = adx_df.iloc[:, 2]  # ADX 是第三列
            
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(adx_line.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(adx_line.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addSubIndicator === 'function') {{
                    window.addSubIndicator('ADX', '{json.dumps(data)}', {{
                        color: '{color}', 
                        group: 'TREND', 
                        indicatorKey: 'ADX',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding ADX: {e}")

    def add_stddev_indicator(self, df: pd.DataFrame, period=20, color="#FF5722"):
        """添加 Standard Deviation 标准差 (主图)"""
        try:
            cols = self._get_standard_columns(df)
            if not cols['close']: return

            stddev_series = df[cols['close']].rolling(window=period).std()
            dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
            
            data = [{'time': dates[i], 'value': float(stddev_series.iloc[i])} 
                    for i in range(len(df)) if not pd.isna(stddev_series.iloc[i])]
            
            self._queue_indicator(f"""
                if (typeof window.addMainIndicator === 'function') {{
                    window.addMainIndicator('StdDev', '{json.dumps(data)}', {{
                        color: '{color}', 
                        lineWidth: 1, 
                        lineStyle: 2,
                        group: 'VOLATILITY', 
                        indicatorKey: 'STDDEV',
                        visible: false
                    }});
                }}
            """)
        except Exception as e:
            print(f"Error adding StdDev: {e}")

    def _get_standard_columns(self, df):
        """辅助函数：获取标准化的列名"""
        cols = {
            'open': 'open', 'high': 'high', 'low': 'low', 
            'close': 'close', 'volume': 'volume', 'date': 'date'
        }
        
        for key, val in cols.items():
            if val not in df.columns:
                for col in df.columns:
                    if key in str(col).lower():
                        cols[key] = col
                        break
                else:
                    cols[key] = None
        return cols

    def _prepare_chart_data(self, df: pd.DataFrame) -> list:
        """准备符合 Lightweight Charts v5 格式的数据"""
        cols = self._get_standard_columns(df)
        if not all([cols['open'], cols['close'], cols['high'], cols['low']]):
            print(f"Error: Missing OHLC columns. Found: {list(df.columns)}")
            return []

        dates = pd.to_datetime(df[cols['date']]).dt.strftime('%Y-%m-%d').values
        
        chart_data = []
        for i in range(len(df)):
            try:
                o = float(df[cols['open']].iloc[i])
                h = float(df[cols['high']].iloc[i])
                l = float(df[cols['low']].iloc[i])
                c = float(df[cols['close']].iloc[i])
                
                if h < l: h, l = l, h
                if h < o: h = max(h, o)
                if h < c: h = max(h, c)
                if l > o: l = min(l, o)
                if l > c: l = min(l, c)

                chart_data.append({
                    'time': dates[i],
                    'open': o, 'high': h, 'low': l, 'close': c
                })
            except Exception:
                continue
        return chart_data