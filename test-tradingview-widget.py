import sys
import pandas as pd
import yfinance as yf
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from ui.components.tradingview_widget import TradingViewWidget

class ChartTestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TradingView Widget Test - 0700.HK")
        self.setGeometry(100, 100, 1000, 700)
        
        # 创建主部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # 实例化 TradingView Widget
        self.tv_widget = TradingViewWidget(self)
        layout.addWidget(self.tv_widget)
        
        # 加载数据
        self.load_stock_data()

    def load_stock_data(self):
        symbol = "0700.HK"
        print(f"正在下载 {symbol} 数据...")
        df = yf.download(symbol, period="1y", progress=False)
        
        if df.empty:
            print("未获取到数据")
            return

        # 标准化列名处理
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = ['_'.join([str(x).lower() for x in c]) for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]
        
        # 映射标准列名
        col_mapping = {}
        standard_cols = ['open', 'high', 'low', 'close', 'volume', 'adj close']
        for col in df.columns:
            for std_col in standard_cols:
                if std_col in col:
                    target_name = std_col.replace(' ', '_')
                    col_mapping[col] = target_name
                    break
        
        df.rename(columns=col_mapping, inplace=True)
        df.reset_index(inplace=True)
        if 'date' not in df.columns and 'datetime' in df.columns:
            df.rename(columns={'datetime': 'date'}, inplace=True)
            
        print(f"处理后列名: {list(df.columns)}")
        
        # 更新图表
        self.tv_widget.update_chart_data(df)
        
        # 添加指标 (增加延迟确保图表已初始化)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1000, lambda: self.add_indicators(df))

    def add_indicators(self, df):
        """在图表初始化后添加指标"""
        # ===== 主图指标 =====
        
        # 经典 MA 组合：5, 10, 20, 60
        self.tv_widget.add_ma_indicator(df, period=5, color="#FFFFFF")   # 白线 - 超短线
        self.tv_widget.add_ma_indicator(df, period=10, color="#FFFF00")  # 黄线 - 短线
        self.tv_widget.add_ma_indicator(df, period=20, color="#FF00FF")  # 紫线 - 月线
        self.tv_widget.add_ma_indicator(df, period=60, color="#00FFFF")  # 青线 - 季线
        
        # EMA 组合：12, 26, 50
        self.tv_widget.add_ema_indicator(df, period=12, color="#E040FB")  # 粉线 - 快速EMA
        self.tv_widget.add_ema_indicator(df, period=26, color="#2962FF")  # 蓝线 - 慢速EMA
        self.tv_widget.add_ema_indicator(df, period=50, color="#FF9800")  # 橙线 - 中期EMA
        
        # 【新增】WMA 和 HMA
        self.tv_widget.add_wma_indicator(df, period=20, color="#9C27B0")
        self.tv_widget.add_hma_indicator(df, period=20, color="#00E5FF")
        
        # 布林带
        self.tv_widget.add_bbands_indicator(df)
        
        # 标准差
        self.tv_widget.add_stddev_indicator(df, period=20, color="#FF5722")
        
        # 趋势指标
        self.tv_widget.add_sar_indicator(df, color="#00BCD4")
        self.tv_widget.add_atr_indicator(df, period=14, color="#FF5722")
        self.tv_widget.add_supertrend_indicator(df, period=10, multiplier=3)
        self.tv_widget.add_adx_indicator(df, period=14, color="#FF9800")
        
        # ===== 副图指标 =====
        
        # 成交量
        self.tv_widget.add_vol_indicator(df)
        self.tv_widget.add_vwma_indicator(df, period=20, color="#9C27B0")
        self.tv_widget.add_mfi_indicator(df, period=14, color="#E91E63")
        
        # MACD 和动量
        self.tv_widget.add_macd_indicator(df)
        self.tv_widget.add_momentum_indicator(df, period=10, color="#00BCD4")
        self.tv_widget.add_roc_indicator(df, period=10, color="#FF5722")
        
        # 振荡指标
        self.tv_widget.add_rsi_indicator(df)
        self.tv_widget.add_kdj_indicator(df, period=9, smoothK=3, smoothD=3)
        self.tv_widget.add_cci_indicator(df, period=20, color="#FF9800")
        self.tv_widget.add_williams_indicator(df, period=14, color="#4CAF50")
        
        # 自定义指标
        self.tv_widget.add_yearly_profile_indicator(df, period=252)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = ChartTestWindow()
    window.show()
    sys.exit(app.exec())