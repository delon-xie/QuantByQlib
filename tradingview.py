"""
TradingView 完整可运行版
修复数据格式和图表绘制问题
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QTextEdit, QPushButton,
                            QLabel, QComboBox, QTableWidget, QTableWidgetItem, 
                            QTabWidget, QMessageBox, QSizePolicy)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
import mplfinance as mpf


class StockData:
    """股票数据管理"""
    
    def __init__(self):
        self.data = None
        self.indicators = {}
        
    def fetch_data(self, symbol, period='1y', interval='1d'):
        """生成测试数据"""
        print(f"\n{'='*60}")
        print(f"开始生成 {symbol} 的数据，周期: {period}")
        
        # 根据period决定数据量
        periods_map = {
            '1mo': 30,
            '3mo': 90,
            '6mo': 180,
            '1y': 252,
            '2y': 504,
            '5y': 1260
        }
        
        periods = periods_map.get(period, 252)
        
        # 生成日期范围（工作日）
        end_date = datetime.now()
        start_date = end_date - timedelta(days=int(periods * 1.5))  # 多生成一些
        date_range = pd.bdate_range(start=start_date, end=end_date)
        date_range = date_range[:periods]  # 只取需要的天数
        
        print(f"生成 {periods} 个交易日的数据")
        print(f"日期范围: {date_range[0].date()} 到 {date_range[-1].date()}")
        
        # 基础价格
        base_prices = {
            '0700.HK': 300,   # 腾讯
            '0005.HK': 60,    # 汇丰
            '0939.HK': 5,     # 建行
            '0883.HK': 10,    # 中海油
            '0941.HK': 50,    # 中移动
            'AAPL': 170,      # 苹果
            'TSLA': 180       # 特斯拉
        }
        
        base_price = base_prices.get(symbol, 100)
        print(f"基础价格: {base_price}")
        
        # 设置随机种子
        seed = abs(hash(symbol)) % 10000
        np.random.seed(seed)
        
        # 生成随机价格序列
        returns = np.random.randn(len(date_range)) * 0.02
        
        # 添加趋势
        if '0700' in symbol:  # 腾讯 - 上涨趋势
            trend = np.linspace(0, 0.4, len(date_range))
        elif '0939' in symbol:  # 建行 - 震荡
            trend = np.linspace(0, 0.1, len(date_range))
        elif 'AAPL' in symbol:  # 苹果 - 强势上涨
            trend = np.linspace(0, 0.5, len(date_range))
        else:  # 其他
            trend = np.linspace(0, 0.2, len(date_range))
        
        # 生成价格序列
        cum_returns = np.cumsum(returns)
        price = base_price * np.exp(cum_returns + trend)
        
        # 创建DataFrame
        data = pd.DataFrame(index=date_range)
        data['Close'] = price
        
        # 生成OHLC
        daily_range = np.random.rand(len(date_range)) * 0.04 + 0.01  # 1%-5%的日波动
        
        data['High'] = data['Close'] * (1 + daily_range * 0.6)
        data['Low'] = data['Close'] * (1 - daily_range * 0.4)
        
        # 开盘价：基于前日收盘
        data['Open'] = data['Close'].shift(1) * (1 + np.random.randn(len(date_range)) * 0.01)
        data['Open'].iloc[0] = data['Close'].iloc[0] * 0.99
        
        # 交易量
        data['Volume'] = np.random.randint(1000000, 10000000, len(date_range)) * (1 + trend)
        
        # 确保价格合理性
        data['High'] = data[['High', 'Open', 'Close']].max(axis=1)
        data['Low'] = data[['Low', 'Open', 'Close']].min(axis=1)
        
        # 确保 High >= Low
        mask = data['High'] < data['Low']
        if mask.any():
            print(f"修正 {mask.sum()} 条 High < Low 的记录")
            temp = data.loc[mask, 'High'].copy()
            data.loc[mask, 'High'] = data.loc[mask, 'Low']
            data.loc[mask, 'Low'] = temp
        
        self.data = data
        
        # 打印统计信息
        print(f"\n数据生成完成:")
        print(f"  数据形状: {data.shape}")
        print(f"  最新收盘价: {data['Close'].iloc[-1]:.2f}")
        print(f"  最高价: {data['High'].max():.2f}")
        print(f"  最低价: {data['Low'].min():.2f}")
        print(f"  平均成交量: {data['Volume'].mean():,.0f}")
        
        return data
    
    def calculate_252_day_profile(self):
        """计算252日价格剖面指标"""
        if self.data is None:
            print("错误: 没有数据")
            return None
            
        data_length = len(self.data)
        print(f"\n计算252日指标，数据长度: {data_length}")
        
        if data_length < 252:
            print(f"警告: 数据不足，只有 {data_length} 条，需要至少252条")
            return None
            
        data = self.data.copy()
        
        # 1. 252日最高最低
        data['252_high'] = data['High'].rolling(window=252, min_periods=1).max()
        data['252_low'] = data['Low'].rolling(window=252, min_periods=1).min()
        
        # 2. 相对位置百分比
        denominator = data['252_high'] - data['252_low']
        # 避免除零
        denominator = denominator.replace(0, np.nan)
        data['position_pct'] = (data['Close'] - data['252_low']) / denominator * 100
        
        # 3. 距离高点的跌幅
        data['drawdown_from_high'] = (data['252_high'] - data['Close']) / data['252_high'] * 100
        
        # 4. 距离高点的天数
        def days_since_high(series):
            days = []
            current_high = None
            
            for i, price in enumerate(series):
                if pd.isna(price):
                    days.append(np.nan)
                    continue
                    
                if i == 0 or current_high is None or price > current_high:
                    current_high = price
                    days.append(0)
                else:
                    days.append(days[-1] + 1)
            
            return pd.Series(days, index=series.index)
        
        data['days_since_high'] = days_since_high(data['High'])
        
        self.indicators['252_profile'] = data[['position_pct', 'drawdown_from_high', 'days_since_high']]
        
        # 打印最新指标
        latest = self.indicators['252_profile'].iloc[-1]
        print("\n252日指标计算结果:")
        print(f"  相对位置百分比: {latest['position_pct']:.1f}%")
        print(f"  距高点跌幅: {latest['drawdown_from_high']:.1f}%")
        print(f"  未创新高天数: {int(latest['days_since_high'])}天")
        
        return self.indicators['252_profile']
    
    def get_signal_summary(self):
        """获取信号摘要"""
        if '252_profile' not in self.indicators:
            return [("无信号", "请先计算252日指标", "gray")]
            
        profile = self.indicators['252_profile'].iloc[-1]
        
        signals = []
        
        # 超买超卖信号
        if profile['position_pct'] > 80:
            signals.append(("超买警告", f"位置: {profile['position_pct']:.1f}%", "red"))
        elif profile['position_pct'] < 20:
            signals.append(("超卖机会", f"位置: {profile['position_pct']:.1f}%", "green"))
        else:
            signals.append(("中性", f"位置: {profile['position_pct']:.1f}%", "gray"))
        
        # 高点背离信号
        if profile['position_pct'] > 90 and profile['days_since_high'] > 60:
            signals.append(("顶背离风险", f"{profile['days_since_high']}天未创新高", "red"))
        
        # 底部夯实信号
        if profile['position_pct'] < 30 and profile['days_since_high'] > 100:
            signals.append(("底部夯实", f"低位震荡{profile['days_since_high']}天", "green"))
        
        return signals


class PineScriptEngine:
    """简化的 Pine Script 引擎"""
    
    def __init__(self):
        self.variables = {}
        self.plots = []
        
    def sma(self, series, period):
        """简单移动平均"""
        return series.rolling(window=period, min_periods=1).mean()
    
    def ema(self, series, period):
        """指数移动平均"""
        return series.ewm(span=period, adjust=False).mean()
    
    def rsi(self, series, period=14):
        """相对强弱指数"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def execute(self, code, data):
        """执行 Pine Script 代码"""
        self.plots = []
        
        try:
            # 预定义变量
            self.variables = {
                'close': data['Close'],
                'open': data['Open'],
                'high': data['High'],
                'low': data['Low'],
                'volume': data['Volume']
            }
            
            lines = code.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or line.startswith('//'):
                    continue
                
                # 处理 plot 语句
                if line.startswith('plot('):
                    try:
                        # 提取参数
                        params = line[5:-2].split(',')
                        if len(params) >= 2:
                            series_name = params[0].strip()
                            title = params[1].strip().strip('"')
                            color = params[2].strip().strip('"') if len(params) > 2 else 'blue'
                            
                            # 获取数据序列
                            series = None
                            if series_name in self.variables:
                                series = self.variables[series_name]
                            elif series_name.upper() in ['CLOSE', 'OPEN', 'HIGH', 'LOW', 'VOLUME']:
                                col_name = series_name.capitalize()
                                if col_name in data.columns:
                                    series = data[col_name]
                            
                            if series is not None:
                                self.plots.append({
                                    'data': series,
                                    'title': title,
                                    'color': color
                                })
                                print(f"添加绘图: {title}")
                    except Exception as e:
                        print(f"解析plot语句错误: {e}")
                
                # 处理指标计算
                elif '=' in line and not line.startswith('plot'):
                    try:
                        var, expr = line.split('=', 1)
                        var = var.strip()
                        expr = expr.strip().rstrip(';')
                        
                        # 处理 SMA
                        if 'sma(' in expr.lower():
                            # 提取参数
                            start = expr.lower().find('sma(') + 4
                            end = expr.find(')', start)
                            args_str = expr[start:end]
                            args = [arg.strip() for arg in args_str.split(',')]
                            
                            if len(args) >= 2:
                                series_name = args[0]
                                period = int(args[1])
                                
                                # 获取序列
                                series = None
                                if series_name in self.variables:
                                    series = self.variables[series_name]
                                elif series_name.upper() in ['CLOSE', 'OPEN', 'HIGH', 'LOW']:
                                    col_name = series_name.capitalize()
                                    if col_name in data.columns:
                                        series = data[col_name]
                                
                                if series is not None:
                                    result = self.sma(series, period)
                                    self.variables[var] = result
                                    print(f"计算指标: {var} = SMA({series_name}, {period})")
                    except Exception as e:
                        print(f"解析指标语句错误: {e}")
            
            print(f"脚本执行完成，生成 {len(self.plots)} 个图表")
            return self.plots
            
        except Exception as e:
            print(f"脚本执行错误: {e}")
            return []


class MplCanvas(FigureCanvas):
    """Matplotlib画布"""
    
    def __init__(self, parent=None, width=8, height=6, dpi=100):
        self.fig = Figure(figsize=(width, height), dpi=dpi, facecolor='#2b2b2b')
        self.axes = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)


class StockChart(MplCanvas):
    """股票图表"""
    
    def __init__(self):
        super().__init__()
        self.data = None
        self.ax = self.axes
        self.ax2 = None
        self.setup_axes()
        
    def setup_axes(self):
        """设置坐标轴"""
        self.ax.clear()
        self.ax.set_facecolor('#1e1e1e')
        
        # 设置坐标轴颜色
        self.ax.tick_params(colors='white', which='both')
        self.ax.spines['bottom'].set_color('white')
        self.ax.spines['top'].set_color('white')
        self.ax.spines['left'].set_color('white')
        self.ax.spines['right'].set_color('white')
        
        # 设置标签颜色
        self.ax.xaxis.label.set_color('white')
        self.ax.yaxis.label.set_color('white')
        
        # 设置标题颜色
        self.ax.title.set_color('white')
        
        # 创建第二个Y轴
        self.ax2 = self.ax.twinx()
        self.ax2.tick_params(colors='white', which='both')
        self.ax2.spines['right'].set_color('white')
        
    def plot_candlestick(self, data):
        """绘制K线图"""
        print(f"\n开始绘制K线图，数据形状: {data.shape}")
        
        if data is None or len(data) == 0:
            self.ax.text(0.5, 0.5, '无数据', transform=self.ax.transAxes,
                        ha='center', va='center', fontsize=12, color='white')
            self.draw()
            return
            
        self.data = data
        
        # 重新设置坐标轴
        self.setup_axes()
        
        try:
            # 使用mplfinance绘制K线
            mc = mpf.make_marketcolors(
                up='#00ff00',  # 上涨绿色
                down='#ff0000',  # 下跌红色
                edge='inherit',
                wick='inherit',
                volume='inherit'
            )
            
            s = mpf.make_mpf_style(
                marketcolors=mc,
                gridstyle=':',  # 虚线网格
                gridcolor='gray',
                facecolor='#1e1e1e',
                edgecolor='white',
                figcolor='#1e1e1e',
                rc={'axes.grid': True, 'grid.alpha': 0.3}
            )
            
            # 绘制K线
            mpf.plot(data,
                    type='candle',
                    style=s,
                    ax=self.ax,
                    volume=False,
                    show_nontrading=False,
                    datetime_format='%Y-%m-%d',
                    xrotation=45)
            
            self.ax.set_title('K线图', fontsize=14, fontweight='bold', color='white', pad=20)
            self.ax.set_xlabel('日期', fontsize=10, color='white')
            self.ax.set_ylabel('价格', fontsize=10, color='white')
            
            # 设置网格
            self.ax.grid(True, alpha=0.3, linestyle=':')
            
            # 自动调整布局
            self.fig.tight_layout()
            
            # 绘制
            self.draw()
            
            print("K线图绘制成功")
            print(f"价格范围: {data['Low'].min():.2f} - {data['High'].max():.2f}")
            
        except Exception as e:
            print(f"绘制K线图时出错: {e}")
            import traceback
            traceback.print_exc()
            
            # 备用方案：绘制折线图
            self.ax.clear()
            self.ax.plot(data.index, data['Close'], 'w-', linewidth=2)
            self.ax.set_title('收盘价折线图', fontsize=14, fontweight='bold', color='white')
            self.ax.set_xlabel('日期', fontsize=10, color='white')
            self.ax.set_ylabel('价格', fontsize=10, color='white')
            self.ax.grid(True, alpha=0.3)
            self.ax.tick_params(colors='white')
            self.fig.tight_layout()
            self.draw()
    
    def add_indicator(self, data, title, color='cyan'):
        """添加技术指标"""
        if self.data is None or data is None:
            print(f"无法添加指标 {title}: 没有数据")
            return
            
        try:
            print(f"添加指标: {title}, 数据长度: {len(data)}")
            
            # 确保数据索引对齐
            if not data.index.equals(self.data.index):
                print(f"警告: 指标数据索引不匹配，尝试对齐")
                data = data.reindex(self.data.index)
            
            # 在第二个Y轴绘制
            self.ax2.plot(data.index, data.values, color=color, linewidth=2, label=title, alpha=0.8)
            self.ax2.set_ylabel(title, color=color, fontsize=9)
            self.ax2.tick_params(axis='y', labelcolor=color)
            
            # 更新图例
            lines1, labels1 = self.ax.get_legend_handles_labels()
            lines2, labels2 = self.ax2.get_legend_handles_labels()
            all_lines = lines1 + lines2
            all_labels = labels1 + labels2
            
            if all_lines:
                self.ax.legend(all_lines, all_labels, loc='upper left', 
                              facecolor='#2b2b2b', edgecolor='white',
                              labelcolor='white', fontsize=8)
            
            self.draw()
            print(f"指标 {title} 添加成功")
            
        except Exception as e:
            print(f"添加指标 {title} 时出错: {e}")


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.stock_data = StockData()
        self.pine_engine = PineScriptEngine()
        self.chart = None
        self.toolbar = None
        self.init_ui()
        
    def init_ui(self):
        self.setWindowTitle("TradingView 专业版")
        self.setGeometry(100, 100, 1400, 800)
        
        # 中心部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # 顶部控制栏
        control_layout = QHBoxLayout()
        
        # 股票选择
        control_layout.addWidget(QLabel("股票代码:", self))
        self.symbol_combo = QComboBox(self)
        self.symbol_combo.addItems(["0700.HK", "0005.HK", "0939.HK", 
                                   "0883.HK", "0941.HK", "AAPL", "TSLA"])
        self.symbol_combo.setMinimumWidth(100)
        control_layout.addWidget(self.symbol_combo)
        
        # 时间周期
        control_layout.addWidget(QLabel("周期:", self))
        self.period_combo = QComboBox(self)
        self.period_combo.addItems(["1mo", "3mo", "6mo", "1y", "2y", "5y"])
        self.period_combo.setCurrentText("1y")
        self.period_combo.setMinimumWidth(80)
        control_layout.addWidget(self.period_combo)
        
        # 加载按钮
        self.load_btn = QPushButton("📈 加载数据", self)
        self.load_btn.clicked.connect(self.load_data)
        self.load_btn.setMinimumHeight(30)
        control_layout.addWidget(self.load_btn)
        
        # 计算252日指标按钮
        self.calc_btn = QPushButton("📊 计算252日剖面", self)
        self.calc_btn.clicked.connect(self.calculate_profile)
        self.calc_btn.setMinimumHeight(30)
        control_layout.addWidget(self.calc_btn)
        
        control_layout.addStretch()
        main_layout.addLayout(control_layout)
        
        # 图表区域
        self.init_chart_area()
        main_layout.addWidget(self.chart_widget, 3)
        
        # 底部区域
        bottom_widget = QTabWidget(self)
        
        # 脚本编辑器标签
        script_widget = QWidget()
        script_layout = QVBoxLayout(script_widget)
        
        self.script_editor = QTextEdit()
        self.script_editor.setFont(QFont("Consolas", 10))
        
        # 设置示例代码
        example_code = """// 252日价格剖面策略
// 基于位置百分比的交易信号

// 计算移动平均线
sma20 = sma(close, 20)
sma50 = sma(close, 50)

// 计算RSI
rsi14 = rsi(close, 14)

// 绘图
plot(sma20, "SMA20", "orange")
plot(sma50, "SMA50", "purple")
plot(rsi14, "RSI14", "cyan")"""
        
        self.script_editor.setPlainText(example_code)
        script_layout.addWidget(self.script_editor)
        
        # 执行按钮
        exec_layout = QHBoxLayout()
        self.execute_btn = QPushButton("▶ 执行脚本", self)
        self.execute_btn.clicked.connect(self.execute_script)
        self.execute_btn.setMinimumHeight(30)
        exec_layout.addWidget(self.execute_btn)
        exec_layout.addStretch()
        script_layout.addLayout(exec_layout)
        
        bottom_widget.addTab(script_widget, "脚本编辑器")
        
        # 信号标签
        signal_widget = QWidget()
        signal_layout = QVBoxLayout(signal_widget)
        
        self.signal_table = QTableWidget()
        self.signal_table.setColumnCount(3)
        self.signal_table.setHorizontalHeaderLabels(["信号类型", "描述", "强度"])
        self.signal_table.horizontalHeader().setStretchLastSection(True)
        signal_layout.addWidget(self.signal_table)
        
        bottom_widget.addTab(signal_widget, "交易信号")
        
        # 指标标签
        indicator_widget = QWidget()
        indicator_layout = QVBoxLayout(indicator_widget)
        
        self.indicator_table = QTableWidget()
        self.indicator_table.setColumnCount(3)
        self.indicator_table.setHorizontalHeaderLabels(["指标", "数值", "解读"])
        self.indicator_table.horizontalHeader().setStretchLastSection(True)
        indicator_layout.addWidget(self.indicator_table)
        
        bottom_widget.addTab(indicator_widget, "252日指标")
        
        main_layout.addWidget(bottom_widget, 1)
        
        # 状态栏
        self.statusBar().showMessage("就绪 - 请选择股票代码并加载数据")
        
    def init_chart_area(self):
        """初始化图表区域"""
        self.chart_widget = QWidget()
        chart_layout = QVBoxLayout(self.chart_widget)
        
        # 创建图表
        self.chart = StockChart()
        chart_layout.addWidget(self.chart)
        
        # 添加Matplotlib工具栏
        self.toolbar = NavigationToolbar(self.chart, self)
        chart_layout.addWidget(self.toolbar)
    
    def load_data(self):
        """加载股票数据"""
        symbol = self.symbol_combo.currentText()
        period = self.period_combo.currentText()
        
        self.statusBar().showMessage(f"正在加载 {symbol} 数据...")
        QApplication.processEvents()
        
        data = self.stock_data.fetch_data(symbol, period)
        if data is not None and not data.empty:
            # 清除旧图表
            if self.chart:
                self.chart.figure.clf()
                
            # 重新初始化图表
            self.chart_widget.layout().removeWidget(self.chart)
            self.chart.deleteLater()
            self.chart = StockChart()
            self.chart_widget.layout().insertWidget(0, self.chart)
            
            # 绘制新图表
            self.chart.plot_candlestick(data)
            
            # 更新工具栏
            if self.toolbar:
                self.chart_widget.layout().removeWidget(self.toolbar)
                self.toolbar.deleteLater()
                self.toolbar = NavigationToolbar(self.chart, self)
                self.chart_widget.layout().addWidget(self.toolbar)
            
            self.statusBar().showMessage(f"{symbol} 数据加载完成，共{len(data)}条记录")
        else:
            QMessageBox.warning(self, "错误", "数据加载失败")
            self.statusBar().showMessage("数据加载失败")
    
    def calculate_profile(self):
        """计算252日价格剖面指标"""
        if self.stock_data.data is None:
            QMessageBox.warning(self, "错误", "请先加载数据")
            return
            
        profile = self.stock_data.calculate_252_day_profile()
        if profile is not None:
            # 更新信号表格
            signals = self.stock_data.get_signal_summary()
            if signals:
                self.signal_table.setRowCount(len(signals))
                for i, (signal_type, description, strength) in enumerate(signals):
                    self.signal_table.setItem(i, 0, QTableWidgetItem(signal_type))
                    self.signal_table.setItem(i, 1, QTableWidgetItem(description))
                    
                    item = QTableWidgetItem()
                    if strength == "red":
                        item.setText("高风险")
                        item.setForeground(QColor(255, 100, 100))
                    elif strength == "green":
                        item.setText("机会")
                        item.setForeground(QColor(100, 255, 100))
                    elif strength == "gray":
                        item.setText("中性")
                        item.setForeground(QColor(200, 200, 200))
                    else:
                        item.setText("观察")
                        item.setForeground(QColor(255, 255, 100))
                    
                    self.signal_table.setItem(i, 2, item)
            
            # 更新指标表格
            latest = profile.iloc[-1]
            self.indicator_table.setRowCount(4)
            
            indicators = [
                ("相对位置%", f"{latest['position_pct']:.1f}%", 
                 "超买" if latest['position_pct'] > 80 else "超卖" if latest['position_pct'] < 20 else "正常"),
                ("距高点跌幅", f"{latest['drawdown_from_high']:.1f}%", 
                 "深度调整" if latest['drawdown_from_high'] > 20 else "小幅调整"),
                ("未创新高天数", f"{int(latest['days_since_high'])}天", 
                 "长期盘整" if latest['days_since_high'] > 100 else "近期新高"),
                ("当前价格", f"{self.stock_data.data['Close'].iloc[-1]:.2f}", 
                 "最新收盘价")
            ]
            
            for i, (name, value, interpretation) in enumerate(indicators):
                self.indicator_table.setItem(i, 0, QTableWidgetItem(name))
                self.indicator_table.setItem(i, 1, QTableWidgetItem(value))
                self.indicator_table.setItem(i, 2, QTableWidgetItem(interpretation))
            
            # 在图表上添加水平参考线
            if self.chart and self.stock_data.data is not None:
                data = self.stock_data.data
                
                # 计算80%和20%位置的价格
                high_252 = data['High'].rolling(window=252, min_periods=1).max().iloc[-1]
                low_252 = data['Low'].rolling(window=252, min_periods=1).min().iloc[-1]
                
                price_80 = low_252 + (high_252 - low_252) * 0.8
                price_20 = low_252 + (high_252 - low_252) * 0.2
                
                # 添加水平线
                self.chart.ax.axhline(y=price_80, color='red', linestyle='--', alpha=0.7, linewidth=1, label='80%线')
                self.chart.ax.axhline(y=price_20, color='green', linestyle='--', alpha=0.7, linewidth=1, label='20%线')
                
                # 更新图例
                lines, labels = self.chart.ax.get_legend_handles_labels()
                if lines:
                    self.chart.ax.legend(lines, labels, loc='upper left', 
                                        facecolor='#2b2b2b', edgecolor='white',
                                        labelcolor='white', fontsize=8)
                
                self.chart.draw()
            
            self.statusBar().showMessage("252日价格剖面计算完成")
        else:
            self.statusBar().showMessage("252日指标计算失败，数据不足")
    
    def execute_script(self):
        """执行Pine Script脚本"""
        if self.stock_data.data is None or self.chart is None:
            QMessageBox.warning(self, "错误", "请先加载数据")
            return
            
        script = self.script_editor.toPlainText()
        plots = self.pine_engine.execute(script, self.stock_data.data)
        
        if plots:
            for plot in plots:
                self.chart.add_indicator(plot['data'], plot['title'], plot.get('color', 'cyan'))
            
            self.statusBar().showMessage(f"脚本执行完成，添加了{len(plots)}个指标")
        else:
            self.statusBar().showMessage("脚本执行完成，但未生成任何图表")


def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    app.setStyle("Fusion")
    
    # 设置暗色主题
    app.setStyleSheet("""
        QMainWindow {
            background-color: #2b2b2b;
        }
        QLabel {
            color: white;
            font-weight: bold;
        }
        QPushButton {
            background-color: #4CAF50;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
            font-weight: bold;
            min-height: 30px;
        }
        QPushButton:hover {
            background-color: #45a049;
        }
        QPushButton:pressed {
            background-color: #3d8b40;
        }
        QComboBox {
            background-color: #3d3d3d;
            color: white;
            border: 1px solid #555;
            padding: 6px;
            border-radius: 4px;
            min-height: 30px;
        }
        QComboBox:hover {
            border: 1px solid #777;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #3d3d3d;
            color: white;
            selection-background-color: #4CAF50;
        }
        QTextEdit, QTableWidget {
            background-color: #1e1e1e;
            color: white;
            border: 1px solid #3d3d3d;
            border-radius: 4px;
            font-family: Consolas, Monaco, 'Courier New', monospace;
        }
        QTabWidget::pane {
            border: 1px solid #3d3d3d;
            background-color: #2b2b2b;
            border-radius: 4px;
        }
        QTabBar::tab {
            background-color: #3d3d3d;
            color: #aaa;
            padding: 8px 16px;
            border: 1px solid #3d3d3d;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            font-weight: bold;
        }
        QTabBar::tab:selected {
            background-color: #4CAF50;
            color: white;
        }
        QTabBar::tab:hover {
            background-color: #555;
        }
        QHeaderView::section {
            background-color: #2b2b2b;
            color: white;
            padding: 8px;
            border: 1px solid #3d3d3d;
            font-weight: bold;
        }
        QTableWidget::item {
            padding: 6px;
        }
        QStatusBar {
            background-color: #1e1e1e;
            color: white;
        }
    """)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == "__main__":
    print("="*60)
    print("TradingView 专业版 - 启动中...")
    print("="*60)
    
    # 检查依赖
    try:
        import matplotlib
        import mplfinance
        print("✓ 依赖检查通过")
    except ImportError as e:
        print(f"✗ 缺少依赖: {e}")
        print("请运行: pip install matplotlib mplfinance")
        sys.exit(1)
    
    main()