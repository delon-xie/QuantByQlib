"""测试成交量显示修复"""
import sys
sys.path.insert(0, '.')

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from ui.components.tradingview_advance_widget.widget import TradingViewAdvanceWidget
from qlib.data import D
from qlib.config import REG_CN
import qlib
import pandas as pd
from datetime import date, timedelta

# 初始化 qlib
qlib.init(provider_uri="/Users/admin/.qlib/qlib_data/cn_data", region=REG_CN)

def test_chart_volume():
    print("Testing chart volume fix...")
    
    # 获取测试数据
    ticker = 'SH600208'
    end_date = date.today().isoformat()
    start_date = (date.today() - timedelta(days=30)).isoformat()
    
    df = D.features([ticker], ['$open', '$high', '$low', '$close', '$volume'], 
                   start_time=start_date, end_time=end_date)
    
    df = df.reset_index()
    df = df.rename(columns={
        "datetime": "date",
        "$open": "open",
        "$high": "high",
        "$low": "low",
        "$close": "close",
        "$volume": "volume",
    })
    
    print(f"\n=== {ticker} ===")
    print(f"Shape: {df.shape}")
    print(f"Volume stats: min={df['volume'].min()}, max={df['volume'].max()}, mean={df['volume'].mean():.2f}")
    print(f"First 3 rows:")
    print(df.head(3))
    
    # 创建应用和窗口
    app = QApplication(sys.argv)
    window = QMainWindow()
    central = QWidget()
    layout = QVBoxLayout(central)
    window.setCentralWidget(central)
    
    # 创建图表组件
    chart = TradingViewAdvanceWidget()
    layout.addWidget(chart)
    
    # 设置窗口大小
    window.resize(800, 600)
    
    # 延迟加载数据（等待组件初始化）
    def load_data():
        print("\nLoading data to chart...")
        chart.update_chart_data(df)
        print("Data sent to chart")
        
        # 检查 JavaScript 状态
        chart.browser.page().runJavaScript("""
            console.log('Testing volume series...');
            console.log('volumeSeries exists:', !!window.chartManager?.volumeSeries);
            console.log('candleSeries exists:', !!window.chartManager?.candleSeries);
            if (window.chartManager?.candleSeries?.data) {
                var data = window.chartManager.candleSeries.data();
                console.log('Candle data points:', data.length);
                if (data.length > 0) {
                    console.log('First candle:', JSON.stringify(data[0]));
                    console.log('Has volume:', 'volume' in data[0]);
                }
            }
            if (window.chartManager?.volumeSeries?.data) {
                var volData = window.chartManager.volumeSeries.data();
                console.log('Volume data points:', volData.length);
                if (volData.length > 0) {
                    console.log('First volume:', JSON.stringify(volData[0]));
                }
            }
        """, lambda result: print("JS execution completed"))
    
    # 延迟执行
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(3000, load_data)
    
    # 延迟退出
    QTimer.singleShot(5000, app.quit)
    
    print("Starting app...")
    app.exec()
    print("Test completed")

if __name__ == '__main__':
    test_chart_volume()
