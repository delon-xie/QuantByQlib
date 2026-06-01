"""TradingView Advance Widget 独立演示应用。
使用 yfinance 加载数据，展示组件功能。

新增: 双引擎控制 + 调试按钮
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget,
    QPushButton, QHBoxLayout, QFileDialog, QMessageBox,
    QLabel, QComboBox
)

from widget import TradingViewAdvanceWidget


class DemoWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TradingView Advance Widget Demo")
        self.resize(1400, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(8, 4, 8, 4)

        self.symbol_input = QComboBox()
        self.symbol_input.setEditable(True)
        self.symbol_input.addItems([
            '0700.HK', 'SPX', 'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA',
            'BTC-USD', 'ETH-USD', '^GSPC', 'GC=F', 'EURUSD=X'
        ])
        self.symbol_input.setCurrentText('AAPL')
        self.symbol_input.setFixedWidth(120)

        load_btn = QPushButton("加载数据")
        load_btn.clicked.connect(self._load_data)

        clear_btn = QPushButton("清空指标")
        clear_btn.clicked.connect(self._clear_indicators)

        save_btn = QPushButton("保存状态")
        save_btn.clicked.connect(self._save_state)

        load_state_btn = QPushButton("恢复状态")
        load_state_btn.clicked.connect(self._load_state)

        # 双引擎控制
        self.source_combo = QComboBox()
        self.source_combo.addItems(['auto (JS→Python)', 'js only', 'python only'])
        self.source_combo.setCurrentText('auto (JS→Python)')
        self.source_combo.currentTextChanged.connect(self._on_source_changed)

        # 调试按钮
        debug_btn = QPushButton("引擎自检")
        debug_btn.clicked.connect(self._debug_engine)

        # JS 诊断按钮
        jsdiag_btn = QPushButton("JS诊断")
        jsdiag_btn.clicked.connect(self._js_diagnose)

        # 打开 DevTools
        devtools_btn = QPushButton("DevTools")
        devtools_btn.clicked.connect(self._open_devtools)

        toolbar.addWidget(QLabel("标的:"))
        toolbar.addWidget(self.symbol_input)
        toolbar.addWidget(load_btn)
        toolbar.addSpacing(16)
        toolbar.addWidget(clear_btn)
        toolbar.addWidget(save_btn)
        toolbar.addWidget(load_state_btn)
        toolbar.addSpacing(16)
        toolbar.addWidget(QLabel("引擎:"))
        toolbar.addWidget(self.source_combo)
        toolbar.addWidget(debug_btn)
        toolbar.addStretch()

        layout.addLayout(toolbar)

        self.chart = TradingViewAdvanceWidget()
        layout.addWidget(self.chart)

    def _load_data(self):
        symbol = self.symbol_input.currentText().strip()
        if not symbol:
            return
        try:
            # SPX 从本地 CSV 加载全部数据
            if symbol == 'SPX':
                # 尝试多个路径（取决于入口位置）
                from pathlib import Path
                candidates = [
                    Path(__file__).parent.parent.parent / 'SPX.csv',
                    Path(__file__).parent.parent / 'SPX.csv',
                    Path(__file__).parent / 'SPX.csv',
                    Path.cwd() / 'SPX.csv',
                ]
                for csv_path in candidates:
                    if csv_path.exists():
                        import pandas as pd
                        df = pd.read_csv(csv_path)
                        df['date'] = pd.to_datetime(df['date'], utc=True).dt.strftime('%Y-%m-%d')
                        self.chart.update_chart_data(df)
                        self.setWindowTitle(f"TradingView Advance Widget - {symbol} ({len(df)} bars)")
                    return
            import yfinance as yf
            ticker = yf.Ticker(symbol)
            df = ticker.history(period='5y')
            if df.empty:
                QMessageBox.warning(self, "警告", f"未获取到 {symbol} 的数据")
                return
            df.reset_index(inplace=True)
            self.chart.update_chart_data(df)
            self.setWindowTitle(f"TradingView Advance Widget - {symbol}")
        except ImportError:
            QMessageBox.critical(
                self, "错误",
                "请安装 yfinance: pip install yfinance"
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载失败: {e}")

    def _clear_indicators(self):
        self.chart.clear_all()

    def _save_state(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "保存状态", "", "JSON Files (*.json)"
        )
        if path:
            self.chart.save_state(path)

    def _load_state(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "加载状态", "", "JSON Files (*.json)"
        )
        if path:
            self.chart.load_state(path)

    def _on_source_changed(self, text):
        """双引擎切换"""
        mapping = {
            'auto (JS→Python)': 'auto',
            'js only': 'js',
            'python only': 'python',
        }
        source = mapping.get(text, 'auto')
        self.chart.set_compute_source(source)
        print(f"🔧 计算源切换: {text} → {source}")

    def _debug_engine(self):
        """引擎自检"""
        self.chart.debug_engine()

    def _js_diagnose(self):
        """JS 全面诊断"""
        self.chart.run_js_diagnose()

    def _open_devtools(self):
        """打开浏览器开发者工具"""
        self.chart.open_dev_tools_window()


def main():
    app = QApplication(sys.argv)
    window = DemoWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
